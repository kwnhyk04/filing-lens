"""Writes web/demo/snapshot.json for the public demo (`make demo-export`).

The answers are 8 recorded records of the golden v1 test run, so no model is called. Coverage
(every page) and the cited sources come through the API's own GraphQL, in process, from the dev
Postgres, with the same operations the web sends. Rebuild the web after an export.
"""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from filinglens_api.limits import rate_limit
from filinglens_api.main import app
from filinglens_api.schemas import Answer
from filinglens_core.settings import ApiSettings, load_settings

ROOT = Path(__file__).resolve().parents[1]
REPORT = "evals/reports/2026-10-17.json"
OUT = ROOT / "web" / "demo" / "snapshot.json"
PICKS = ("n01", "c02", "c12", "x02", "x04", "x12", "o02", "t01")
SOURCE = (
    "Answers recorded in the golden set v1 test run of 2026-10-17 (Gemini 3.5 Flash-Lite, free"
    " tier), with sources and coverage from the dev database."
)
MAX_IDS = 20  # per kind in one Sources query
# Chunks the parser files under the item heading before a separate financial section (README,
# Known Limitations): a demo citation there would show the wrong item.
MISLABELED = {
    ("0001628280-26-008131", "15"),  # JPM: MD&A, market risk and the statements
    ("0000093410-26-000078", "14"),  # CVX: the same
    ("0001045810-26-000021", "15"),  # NVDA: its Item 8 content
    ("0001193125-26-051453", "16"),  # PLD: its Item 8 content
}


def records() -> dict[str, dict[str, Any]]:
    report = json.loads((ROOT / REPORT).read_text("utf-8"))
    return {record["id"]: record for record in report["records"]["answer"]}


def answer_of(record: dict[str, Any]) -> dict[str, Any]:
    """The record as the API's Answer; the run used free tiers only, so nothing was billed."""
    answer = Answer(
        answer=record["answer"],
        citations=record["citations"],
        degraded=record["degraded"],
        usage={  # pyright: ignore[reportArgumentType]  # pydantic validates the dict
            "input_tokens": record["input_tokens"],
            "output_tokens": record["output_tokens"],
            "cost_usd": 0.0,
        },
        refused=record["outcome"] == "refused",
        warnings=record["warnings"],
    )
    if answer.refused and answer.citations:
        raise SystemExit(f"{record['id']} is refused but cites sources")
    return answer.model_dump(mode="json")


def check_labels(answers: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
    """Stops on a cited chunk inside a mislabeled section, naming the record to swap."""
    bad = {
        c["id"]
        for c in chunks
        if (c["filing"]["accessionNumber"], c["section"]["item"]) in MISLABELED
    }
    for item in answers:
        for citation in item["answer"]["citations"]:
            if citation["chunk_id"] in bad:
                raise SystemExit(
                    f"{item['id']} cites chunk {citation['chunk_id']} in a mislabeled section"
                )


def write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    """Sorted JSON with LF line endings on every platform, as `.gitattributes` keeps it."""
    text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, "utf-8", newline="\n")


def main() -> None:
    answers_by_id = records()
    questions = {
        q["id"]: q["question"]
        for q in map(
            json.loads, (ROOT / "evals/golden/v1/questions.jsonl").read_text("utf-8").splitlines()
        )
    }
    answers = [
        {
            "id": pick,
            "category": answers_by_id[pick]["category"],
            "question": questions[pick],
            "answer": answer_of(answers_by_id[pick]),
        }
        for pick in PICKS
    ]
    cited = [c for item in answers for c in item["answer"]["citations"]]
    chunk_ids = sorted({c["chunk_id"] for c in cited if c["chunk_id"]})
    fact_ids = sorted({c["fact_id"] for c in cited if c["fact_id"]})

    document = (ROOT / "clients/operations.graphql").read_text("utf-8")
    key = load_settings(ApiSettings).api_key.get_secret_value()
    app.dependency_overrides[rate_limit] = lambda: None  # an operator tool: no Redis needed
    with TestClient(app, headers={"X-API-Key": key}) as client:

        def run(operation: str, variables: dict[str, Any]) -> dict[str, Any]:
            body = {"query": document, "operationName": operation, "variables": variables}
            reply = client.post("/graphql", json=body).json()
            if reply.get("errors") or not reply.get("data"):
                raise SystemExit(f"{operation} failed: {reply.get('errors')}")
            return reply["data"]

        companies: list[dict[str, Any]] = []
        after = None
        while True:
            page = run("Coverage", {"first": 20, "after": after})["companies"]
            companies += [edge["node"] for edge in page["edges"]]
            if not page["pageInfo"]["hasNextPage"]:
                break
            after = page["pageInfo"]["endCursor"]
        sources: dict[str, list[dict[str, Any]]] = {"chunks": [], "facts": []}
        for i in range(0, max(len(chunk_ids), len(fact_ids)), MAX_IDS):
            ids = {"chunkIds": chunk_ids[i : i + MAX_IDS], "factIds": fact_ids[i : i + MAX_IDS]}
            found = run("Sources", ids)
            sources["chunks"] += found["chunks"]
            sources["facts"] += found["facts"]

    missing = set(chunk_ids) - {c["id"] for c in sources["chunks"]}
    missing |= set(fact_ids) - {f["id"] for f in sources["facts"]}
    if missing:
        raise SystemExit(f"Cannot resolve citations {sorted(missing)}")
    check_labels(answers, sources["chunks"])

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    snapshot = {
        "answers": answers,
        "commit": commit.stdout.strip(),
        "companies": companies,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "report": REPORT,
        "source": SOURCE,
        "sources": sources,
    }
    write_snapshot(snapshot, OUT)

    chunks = {c["id"]: c for c in sources["chunks"]}
    facts = {f["id"]: f for f in sources["facts"]}
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(answers)} answers, {len(companies)} companies.")
    for item in answers:
        for n, citation in enumerate(item["answer"]["citations"], 1):
            if citation["chunk_id"]:
                c = chunks[citation["chunk_id"]]
                f = c["filing"]
                filing = f"{f['company']['ticker']} {f['formType']} FY{f['fiscalYear']}"
                where = f"{filing}, Item {c['section']['item']}"
            else:
                fact = facts[citation["fact_id"]]
                period = f"FY{fact['fiscalYear']} {fact['fiscalPeriod']}"
                where = f"{fact['company']['ticker']} fact {period}, {fact['label']}"
            print(f"  {item['id']} [{n}] {where}")


if __name__ == "__main__":
    main()
