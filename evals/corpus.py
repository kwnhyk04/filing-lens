"""Golden v1's corpus for CI (step 7): the dev database as a pg_dump that holds rows of the public
SEC tables only, published as the release asset corpus-v1.

    make corpus-dump      # dev stack (make dev): .cache/corpus/corpus-v1.dump, its tables, sha256
    make corpus-restore   # an empty Postgres (CI): fetch the asset if missing, check it, restore it

Every table's schema goes in, so a restore stands at the dev revision (0008) with empty job,
dead-letter and eval-run tables. Rows go in only for PUBLIC. The dump fails when its table of
contents lists rows of any other table, or when the value of any secret-named variable in the
environment (the .env that make passes) or the SEC contact appears anywhere in its SQL.
"""

import argparse
import hashlib
import os
import re
import subprocess
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import IO, cast

REPO = Path(__file__).parents[1]
# Filings, sections, chunks (with their vectors) and XBRL facts from SEC EDGAR, the companies,
# and the revision marker. Nothing else leaves the PC.
PUBLIC = ("alembic_version", "companies", "filings", "sections", "chunks", "financial_facts")
NAME = "corpus-v1.dump"
DUMP = REPO / ".cache" / "corpus" / NAME
URL = f"https://github.com/kwnhyk04/filing-lens/releases/download/corpus-v1/{NAME}"
SHA256 = "50faa04aa39bc16b622235ebc33f223d86a9dba870d38365870bf057bc6a52c0"  # made 2026-10-17
COMPOSE = ("docker", "compose", "--env-file", ".env", "-f", "infra/docker-compose.yml")
IN_CONTAINER = "/tmp/corpus.dump"  # noqa: S108 - inside the postgres container
SECRET_NAMES = re.compile(r"KEY|PASSWORD|SECRET|TOKEN")
MIN_SECRET = 8  # shorter values would match ordinary filing text
TIMEOUT_S = 1800  # each docker step: the restore rebuilds the indexes
FETCH_TIMEOUT_S = 60  # per read while downloading the asset


def compose(*args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [*COMPOSE, *args], cwd=REPO, check=True, capture_output=True, text=True, timeout=TIMEOUT_S
    )
    return done.stdout


def data_entries(toc: str) -> set[str]:
    """The tables and sequences whose rows or values a dump holds, from `pg_restore --list`."""
    pattern = r"^\d+; \d+ \d+ (?:TABLE DATA|SEQUENCE SET) \S+ (\S+)"
    return set(re.findall(pattern, toc, flags=re.MULTILINE))


def secrets() -> dict[str, list[bytes]]:
    """Values the dump must never hold, by variable name: secret-named variables and the SEC
    contact (SEC_USER_AGENT and its email)."""
    found: dict[str, list[bytes]] = {}
    for name, value in os.environ.items():
        if SECRET_NAMES.search(name) and len(value) >= MIN_SECRET:
            found[name] = [value.encode()]
    if agent := os.environ.get("SEC_USER_AGENT"):
        found["SEC_USER_AGENT"] = [w.encode() for w in [agent, *agent.split()] if "@" in w]
    return found


def leaks(stream: IO[bytes], needles: Sequence[bytes]) -> set[int]:
    """The indexes of the needles found in the stream, read in blocks that overlap."""
    found: set[int] = set()
    keep = max(map(len, needles), default=1) - 1
    tail = b""
    while block := stream.read(1 << 20):
        window = tail + block
        found |= {i for i, needle in enumerate(needles) if needle in window}
        tail = window[-keep:] if keep else b""
    return found


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def check(path: Path, expected: str) -> None:
    if (actual := sha256(path)) != expected:
        raise SystemExit(f"{path}: sha256 {actual}, expected {expected or 'none (SHA256 unset)'}.")


def dump() -> None:
    tables = compose(
        "exec", "-T", "postgres", "psql", "-At", "-c",
        "select tablename from pg_tables where schemaname = 'public' order by 1",
    ).split()  # fmt: skip
    owned = compose(  # each id sequence and its table
        "exec", "-T", "postgres", "psql", "-At", "-c",
        "select s.relname || '|' || t.relname from pg_class s join pg_depend d"
        " on d.classid = 'pg_class'::regclass and d.objid = s.oid and d.deptype in ('a', 'i')"
        " join pg_class t on t.oid = d.refobjid where s.relkind = 'S'",
    ).split()  # fmt: skip
    sequences = dict(line.split("|") for line in owned)
    private = [table for table in tables if table not in PUBLIC]
    counters = sorted(s for s, table in sequences.items() if table not in PUBLIC)
    compose(
        "exec", "-T", "postgres", "pg_dump", "--format=custom", "--compress=zstd", "--no-owner",
        "--no-privileges", f"--file={IN_CONTAINER}",
        *(f"--exclude-table-data=public.{name}" for name in private + counters), "postgresql:///",
    )  # fmt: skip
    try:
        held = data_entries(compose("exec", "-T", "postgres", "pg_restore", "--list", IN_CONTAINER))
        allowed = set(PUBLIC) | {s for s, table in sequences.items() if table in PUBLIC}
        if extra := held - allowed:
            raise SystemExit(f"The dump holds data of {sorted(extra)}; nothing was saved.")
        named = secrets()
        needles = [needle for values in named.values() for needle in values]
        owners = [name for name, values in named.items() for _ in values]
        sql = subprocess.Popen(  # noqa: S603 - the dump as SQL, streamed, never kept on disk
            [*COMPOSE, "exec", "-T", "postgres", "pg_restore", "--file=-", IN_CONTAINER],
            cwd=REPO, stdout=subprocess.PIPE,
        )  # fmt: skip
        found = leaks(cast(IO[bytes], sql.stdout), needles)
        if sql.wait(timeout=TIMEOUT_S):
            raise SystemExit("pg_restore could not read the dump back as SQL.")
        if found:
            hits = sorted({owners[i] for i in found})
            raise SystemExit(f"The dump's SQL holds the value of {hits}; nothing was saved.")
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        compose("cp", f"postgres:{IN_CONTAINER}", str(DUMP))
        print(f"Data: {', '.join(sorted(held))}. Schema only: {', '.join(private + counters)}.")
        for table in PUBLIC:
            count = f"select count(*) from {table}"  # noqa: S608 - names from PUBLIC
            print(
                f"  {table}: {int(compose('exec', '-T', 'postgres', 'psql', '-At', '-c', count)):,}"
            )
        print(f"No value of {', '.join(sorted(named))} in the SQL.")
        print(f"{DUMP}: {DUMP.stat().st_size / 1e6:.1f} MB, sha256 {sha256(DUMP)}")
    finally:
        compose("exec", "-T", "postgres", "rm", "-f", IN_CONTAINER)


def restore() -> None:
    if not DUMP.exists():
        DUMP.parent.mkdir(parents=True, exist_ok=True)
        part = DUMP.with_suffix(".part")
        with (
            urllib.request.urlopen(URL, timeout=FETCH_TIMEOUT_S) as response,
            part.open("wb") as out,
        ):
            while block := response.read(1 << 20):
                out.write(block)
        part.replace(DUMP)
    check(DUMP, SHA256)
    compose("cp", str(DUMP), f"postgres:{IN_CONTAINER}")
    try:
        compose(
            "exec", "-T", "postgres", "pg_restore", "--exit-on-error", "--single-transaction",
            "--no-owner", "--no-privileges", "--dbname=postgresql:///", IN_CONTAINER,
        )  # fmt: skip
    finally:
        compose("exec", "-T", "postgres", "rm", "-f", IN_CONTAINER)
    print(f"Restored {NAME} ({', '.join(PUBLIC)}).")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m evals.corpus", description=__doc__)
    parser.add_argument("command", choices=("dump", "restore"))
    {"dump": dump, "restore": restore}[parser.parse_args().command]()


if __name__ == "__main__":
    main()
