"""Export contracts/openapi.json, or check generated files: `python -m filinglens_api.contracts`.

`make codegen` runs the export (`strawberry export-schema` writes contracts/schema.graphql), then
the client generators. `make contracts-check` runs codegen and then `--check`.
"""

import argparse
import json
import subprocess
from pathlib import Path

GENERATED = ("contracts", "clients")
OPENAPI = Path("contracts/openapi.json")


def export() -> None:
    from filinglens_api.main import app  # deferred: --check needs no app

    OPENAPI.parent.mkdir(exist_ok=True)
    spec = json.dumps(app.openapi(), indent=2) + "\n"
    OPENAPI.write_text(spec, encoding="utf-8", newline="\n")


def check() -> None:
    """Fail if codegen changed a tracked file or added one. Staged changes count as reviewed."""
    status = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *GENERATED],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    stale = [line for line in status if line[1] != " "]  # unstaged change or untracked file
    if stale:
        raise SystemExit(
            "Generated contracts or clients are stale. Review and commit what `make codegen`"
            " wrote:\n" + "\n".join(stale)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if git sees changes under contracts/ or clients/"
    )
    if parser.parse_args().check:
        check()
    else:
        export()


if __name__ == "__main__":
    main()
