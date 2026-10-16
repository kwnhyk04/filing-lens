"""Judge calibration (`make calibrate`): a human labels 30 cited sentences blind, and Cohen's kappa
against the judge decides whether citation precision and faithfulness count (0.7 or more).

The sample is drawn once, with a fixed seed, from the latest gate-off dev answer report and kept
in evals/calibration/v1/sample.jsonl (user decision, 2026-10-16): 21 natural sentences, those that
fail the validator (first drafts and regenerations, up to 10) and the rest from final answers
that pass it, plus 9 constructed negatives: a final-answer sentence that cites one passage, with
that citation pointed at another passage retrieved for the same answer that the answer never
cited, quoted from that passage. At most 2 per question, all shuffled together. Each screen shows
the question, the sentence and the full text of each source it cites, with the quote given: what
the judge sees. Nothing shows which sentences are constructed, nor the judge's verdict or the
validator's outcome. Keys: y the cited sources state everything the sentence claims, n they do
not, b back, q quit (Ctrl+C too); each key is saved at once, so a later run resumes. Once every
sentence is labeled, the judge scores those it has not seen (one LLM_JUDGE call each, cached),
and the agreement goes to result.json, which the harness reads.

A labeler outside this tool (user decision, 2026-10-16: Claude, in another chat) works from
`make calibrate ARGS=export` (sample_for_labeling.jsonl: id, question, sentence, and each cited
passage in full with the quote given; no verdict, no stratum), and `make calibrate ARGS=import`
scores the judge against its labels (claude_labels.jsonl); result.json names the labeler.

The follow-up check (user decision, 2026-10-16) is a second sample in evals/calibration/
v1-followup/, run with a first argument `followup` (`make calibrate ARGS="followup export"`, then
`ARGS="followup import"`): about 10 natural sentences that fail the validator, from decision 4's
fallback runs, nemotron's first (4b, another family than the judge), topped up from gpt-oss-20b's
(4a), never from gpt-oss-120b's (4c, the judge's own model). v1's files stay frozen, and only v1's
result.json decides whether the judge metrics count. Six sentences are too few for kappa, so its
result is a spot check: how many of the sentences labeled not supported the judge failed too.
"""

import asyncio
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from evals import judge
from evals.calls import Cache, Call, Recorded, Stop, patiently
from evals.golden import ROOT as GOLDEN
from evals.golden import VERSION, read_jsonl, write_jsonl
from evals.harness import CACHE, CALIBRATION, REPORTS, EvalSettings, load_sources
from evals.label import BOLD, RESET, enable_ansi, key_or_quit, show
from evals.metrics import bootstrap, cohen_kappa
from filinglens_core.settings import PROVIDER_KEYS, load_settings
from filinglens_db import make_engine
from filinglens_llm import answer as drafting
from filinglens_llm.providers import TIMEOUT, provider
from filinglens_llm.validate import check_sentence, cited, split_sentences
from filinglens_telemetry import configure_logging

ROOT = CALIBRATION.parent
FOLLOWUP_ROOT = ROOT.parent / f"{VERSION}-followup"  # the second sample; v1's stays frozen
SAMPLE, LABELS = "sample.jsonl", "labels.jsonl"
TOTAL, CONSTRUCTED, FAILING, PER_QUESTION = 30, 9, 10, 2  # user decisions, 2026-10-16
FOLLOWUP = 10
# Decision 4's candidates, drawn in this order; never gpt-oss-120b, the judge's own model.
FOLLOWUP_MODELS = ("nvidia:nvidia/nemotron-3-super-120b-a12b", "nvidia:openai/gpt-oss-20b")
QUOTE_WORDS = 12  # a constructed citation's quote: a span of the swapped passage, seeded position
EXPORT = "sample_for_labeling.jsonl"  # for a labeler outside this tool
IMPORT = "claude_labels.jsonl"  # its labels: {"id", "label", "labeler", "why"}
STRATA = ("passing", "failing", "constructed")
ABBREVIATION = re.compile(r"\b(?:[A-Z]\.){2,}$")  # "U.S." ends a split that is no sentence end
GUIDE = f"""{BOLD}Calibrating the judge{RESET}

Each screen shows a question, one sentence of an answer, and the full text of every source the
sentence cites, with the quote the answer gave for it. Read the sources in full: a quote alone
may not carry the claim.

Press {BOLD}y{RESET} when the cited sources state everything the sentence claims (a rounded
figure, such as $416.2 billion for 416,161,000,000 USD, counts as stated), {BOLD}n{RESET} when
any part of it is missing, different or only implied. {BOLD}b{RESET} goes back, {BOLD}q{RESET}
quits; every key is saved.

Press any key to start, q to quit."""
PROMPT = "Do the cited sources state everything this sentence claims?  y yes  n no  b back  q quit"


def gate_off_report() -> dict[str, Any]:
    """The newest dev answer report with the refusal gate off: the one the sweep read."""
    for path in sorted((REPORTS / "runs").glob("*-dev-full.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        if "answer" in report["records"] and report["config"]["min_relevance"] <= -100:
            return report | {"path": path.name}
    raise SystemExit("No gate-off dev answer report: make eval SUITE=answer SPLIT=dev first.")


def latest_report(primary: str) -> dict[str, Any]:
    """The newest dev answer report whose primary model is `primary` (a decision 4 run)."""
    for path in sorted((REPORTS / "runs").glob("*-answer-dev-*.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["config"]["primary"] == primary:
            return report | {"path": path.name}
    raise SystemExit(f"No dev answer report with primary {primary}: run decision 4 first.")


def first_quote(reply: drafting.Reply, alias: str) -> str:
    return (reply.quotes.get(alias) or [""])[0]


async def candidates(report: dict[str, Any], cache: Cache) -> dict[str, list[dict[str, Any]]]:
    """Every cited sentence of the report's answers that the judge can check, by stratum."""
    questions = {q["id"]: q["question"] for q in read_jsonl(GOLDEN / "questions.jsonl")}
    found: dict[str, list[dict[str, Any]]] = {stratum: [] for stratum in STRATA}
    engine = make_engine(load_settings(EvalSettings))
    for record in report["records"]["answer"]:
        sources = await load_sources(engine, record["sources"])
        by_id = {source.chunk_id or source.fact_id: source for source in sources.values()}
        base = {"id": record["id"], "question": questions[record["id"]]}
        base["aliases"] = record["sources"]
        verdicts = (record.get("judge") or {}).get("supported")
        # An answer that lost a sentence to validation can hold an orphan fragment: the splitter
        # cuts after "U.S.", the uncited first half is dropped and the rest stays (x16, 2026-10-16).
        trimmed = any(warning.startswith("Removed") for warning in record["warnings"])
        if record["outcome"] == "answered" and verdicts and not trimmed:
            given = {
                number: by_id[citation["chunk_id"] or citation["fact_id"]]
                for number, citation in enumerate(record["citations"], 1)
            }
            cited_ids = {source.chunk_id for source in given.values() if source.chunk_id}
            others = sorted(
                (s for s in sources.values() if s.chunk_id and s.chunk_id not in cited_ids),
                key=lambda source: source.chunk_id or "",
            )
            final = judge.sentences(record["answer"])
            for index, (sentence, cites) in enumerate(final):
                if index and ABBREVIATION.search(final[index - 1][0]):
                    continue  # a fragment the splitter cut after "U.S."
                shown = [
                    [n, given[n].heading, record["citations"][n - 1]["quote"], given[n].text]
                    for n in cites
                ]
                item = base | {"stratum": "passing", "reply": "final", "index": index}
                found["passing"].append(item | {"sentence": sentence, "sources": shown})
                found["passing"][-1]["verdict"] = verdicts[index]
                if len(cites) != 1 or given[cites[0]].chunk_id is None or not others:
                    continue
                rng = random.Random(f"{VERSION}:swap:{record['id']}:{index}")  # noqa: S311
                swap = rng.choice(others)
                words = swap.text.split()
                start = rng.randrange(max(1, len(words) - QUOTE_WORDS + 1))
                quote = " ".join(words[start : start + QUOTE_WORDS])
                cites_given = {
                    n: judge.Cited(s.heading, record["citations"][n - 1]["quote"], s.text)
                    for n, s in given.items()
                }
                cites_given[cites[0]] = judge.Cited(swap.heading, quote, swap.text)
                prompt = judge.user_prompt(base["question"], record["answer"], cites_given)
                item = base | {"stratum": "constructed", "reply": "final", "index": index}
                found["constructed"].append(
                    item
                    | {
                        "sentence": sentence,
                        "sources": [[cites[0], swap.heading, quote, swap.text]],
                        "swap": [given[cites[0]].chunk_id, swap.chunk_id],
                        "judge_prompt": prompt,
                        "judge_answer": record["answer"],
                    }
                )
        replies = [call for call in record["calls"] if call["role"] == "primary"]
        for kind, call in zip(("draft", "regeneration"), replies, strict=False):
            completion = cache.get(call["cache_id"])
            if completion is None:
                continue
            reply = drafting.read_reply(completion.text)
            if reply.insufficient:
                continue
            order: dict[str, int] = {}
            numbered = drafting.numbered(reply.text, order)
            pairs = zip(split_sentences(reply.text), split_sentences(numbered), strict=True)
            pairs = list(pairs)
            for index, (raw, sentence) in enumerate(pairs):
                if index and ABBREVIATION.search(pairs[index - 1][0]):
                    continue  # a fragment the splitter cut after "U.S."
                aliases = cited(raw)
                if not aliases or any(alias not in sources for alias in aliases):
                    continue  # nothing the judge could check it against
                if check_sentence(raw, reply.quotes, sources) is None:
                    continue
                shown = [
                    [order[a], sources[a].heading, first_quote(reply, a), sources[a].text]
                    for a in aliases
                ]
                item = base | {"stratum": "failing", "reply": kind, "cache_id": call["cache_id"]}
                found["failing"].append(
                    item | {"index": index, "sentence": sentence, "sources": shown}
                )
    await engine.dispose()
    return found


def draw(found: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Failing sentences (up to FAILING), CONSTRUCTED negatives, then passing sentences until
    TOTAL, under a fixed seed: at most PER_QUESTION per question, each sentence once (a
    sentence that a draft and its regeneration share counts once), shown in shuffled order."""
    rng = random.Random(f"{VERSION}:calibration")  # noqa: S311 - a sample, not security
    taken: Counter[str] = Counter()
    used: set[tuple[str, Any]] = set()
    sample: list[dict[str, Any]] = []
    for stratum in ("failing", "constructed", "passing"):
        want = {"failing": FAILING, "constructed": CONSTRUCTED}.get(stratum, TOTAL - len(sample))
        pool = sorted(found[stratum], key=lambda item: (item["id"], item["reply"], item["index"]))
        rng.shuffle(pool)
        picked = 0
        for item in pool:
            keys = {(item["id"], (item["reply"], item["index"])), (item["id"], item["sentence"])}
            if picked < want and taken[item["id"]] < PER_QUESTION and not keys & used:
                taken[item["id"]] += 1
                used |= keys
                sample.append(item)
                picked += 1
    rng.shuffle(sample)
    return sample


def draw_followup(pools: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Up to FOLLOWUP failing sentences under a fixed seed, each pool drawn before the next: at
    most PER_QUESTION per question, each sentence once, shown in shuffled order."""
    rng = random.Random(f"{VERSION}:followup")  # noqa: S311 - a sample, not security
    taken: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    sample: list[dict[str, Any]] = []
    for pool in pools:
        ordered = sorted(pool, key=lambda item: (item["id"], item["reply"], item["index"]))
        rng.shuffle(ordered)
        for item in ordered:
            key = (item["id"], item["sentence"])
            if len(sample) < FOLLOWUP and taken[item["id"]] < PER_QUESTION and key not in seen:
                taken[item["id"]] += 1
                seen.add(key)
                sample.append(item)
    rng.shuffle(sample)
    return sample


def label(sample: list[dict[str, Any]], root: Path) -> bool:
    """A blind yes or no for each sentence without one; True once none is left."""
    labels = root / LABELS
    done = {row["item"] for row in read_jsonl(labels)}
    pending = [n for n in range(len(sample)) if n not in done]
    history: list[int] = []
    while pending:
        n = pending[0]
        item = sample[n]
        blocks = [f"{BOLD}{item['sentence']}{RESET}"]
        for number, heading, quote, text in item["sources"]:
            blocks.append(f'[{number}] {heading}\nQuote given: "{quote}"\n{text}')
        header = f"Sentence {n + 1} of {len(sample)} · {len(pending)} left"
        show(header, item["question"], item["id"], "\n\n".join(blocks), PROMPT)
        key = key_or_quit()
        if key in ("y", "n"):
            row = {"item": n, "id": item["id"], "supported": key == "y"}
            row["at"] = datetime.now(UTC).isoformat(timespec="seconds")
            with labels.open("a", encoding="utf-8", newline="\n") as file:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
            history.append(pending.pop(0))
        elif key == "b" and history:
            pending.insert(0, history.pop())
        elif key == "q":
            return False
    return True


async def new_verdicts(sample: list[dict[str, Any]], cache: Cache) -> dict[int, str | None]:
    """The judge's verdict on each sampled sentence it has not seen yet: a failing draft
    sentence (its whole reply, as for a final answer) or a constructed one (its whole answer,
    with the swapped source)."""
    settings = load_settings(EvalSettings)
    engine = make_engine(settings)
    verdicts: dict[int, str | None] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        model = provider(settings.llm_judge, settings, http)
        for n, item in enumerate(sample):
            if item["stratum"] == "passing":
                continue
            if item["stratum"] == "constructed":
                prompt, answer = item["judge_prompt"], item["judge_answer"]
            else:
                completion = cache.get(item["cache_id"])
                if completion is None:
                    raise SystemExit(f"Reply {item['cache_id'][:12]} is not in the eval cache.")
                reply = drafting.read_reply(completion.text)
                sources = await load_sources(engine, item["aliases"])
                order: dict[str, int] = {}
                answer = drafting.numbered(reply.text, order)
                cites = {
                    number: judge.Cited(sources[a].heading, first_quote(reply, a), sources[a].text)
                    for a, number in order.items()
                    if a in sources
                }
                prompt = judge.user_prompt(item["question"], answer, cites)
            calls: list[Call] = []
            recorded = Recorded(model, "judge", cache, {"question": item["id"]}, calls)

            async def ask(recorded: Recorded = recorded, prompt: str = prompt) -> Any:
                return await recorded.complete(
                    judge.SYSTEM, prompt, max_tokens=judge.MAX_TOKENS, schema=judge.SCHEMA
                )

            reply_text = (await patiently(ask)).text
            try:
                verdicts[n] = judge.parse(reply_text, answer).supported[item["index"]]
            except (judge.JudgeError, IndexError) as exc:
                print(f"{item['id']}: the judge's reply does not parse ({exc})", flush=True)
                verdicts[n] = None
    await engine.dispose()
    return verdicts


def sentence_id(n: int) -> str:
    """A sampled sentence's id in the export and the imported labels: s01 to s30."""
    return f"s{n + 1:02d}"


def export(sample: list[dict[str, Any]], root: Path) -> None:
    """The sample for a labeler outside this tool: per sentence its id, the question, the
    sentence, and each cited passage in full with the quote given. No verdict, no stratum."""
    rows = [
        {
            "id": sentence_id(n),
            "question": item["question"],
            "sentence": item["sentence"],
            "passages": [
                {"number": number, "heading": heading, "quote": quote, "text": text}
                for number, heading, quote, text in item["sources"]
            ],
        }
        for n, item in enumerate(sample)
    ]
    write_jsonl(root / EXPORT, rows)
    print(f"{len(rows)} sentences written to {root / EXPORT}; labels go in {root / IMPORT}.")


def imported(
    sample: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> tuple[dict[int, bool], str]:
    """Labels by sample position from rows {"id", "label": "y" or "n", "labeler", "why"}, and
    the labeler; every sentence needs exactly one."""
    ids = [sentence_id(n) for n in range(len(sample))]
    given = Counter(row.get("id") for row in rows)
    problems = [f"{i}: {given[i]} labels" for i in ids if given[i] != 1]
    problems += [f"unknown id {i}" for i in given if i not in ids]
    problems += [
        f"{row.get('id')}: label {row.get('label')!r}"
        for row in rows
        if row.get("label") not in ("y", "n")
    ]
    labelers = {row.get("labeler") for row in rows}
    if len(labelers) != 1 or not all(labelers):
        problems.append(f"one labeler expected, got {sorted(map(str, labelers))}")
    if problems:
        raise SystemExit(f"{IMPORT} does not fit the sample:\n  " + "\n  ".join(problems))
    labels = {ids.index(row["id"]): row["label"] == "y" for row in rows}
    return labels, str(labelers.pop())


def agreement(
    sample: list[dict[str, Any]], verdicts: dict[int, str | None], labels: dict[int, bool]
) -> dict[str, Any]:
    """The labels against the judge, where only "yes" counts as supported, with kappa."""
    scored: list[tuple[str, bool, bool]] = []
    for n, item in enumerate(sample):
        verdict = item["verdict"] if item["stratum"] == "passing" else verdicts.get(n)
        if verdict is not None:
            scored.append((item["stratum"], labels[n], verdict == "yes"))
    pairs = [(h, j) for _, h, j in scored]
    low, high = bootstrap(pairs, cohen_kappa)
    by_stratum = {stratum: [h == j for s, h, j in scored if s == stratum] for stratum in STRATA}
    natural = [(h, j) for s, h, j in scored if s != "constructed"]  # few negatives: wide CI
    natural_low, natural_high = bootstrap(natural, cohen_kappa)
    return {
        "n": len(pairs),
        "unscored": len(sample) - len(pairs),
        "agreement": sum(h == j for h, j in pairs) / len(pairs),
        "kappa": cohen_kappa(pairs),
        "kappa_ci": [low, high],
        "natural": {
            "n": len(natural),
            "labeler_no": sum(not h for h, _ in natural),
            "judge_no": sum(not j for _, j in natural),
            "agreement": sum(h == j for h, j in natural) / len(natural),
            "kappa": cohen_kappa(natural),
            "kappa_ci": [natural_low, natural_high],
        },
        "per_stratum": {
            s: {"n": len(v), "agreement": sum(v) / len(v) if v else None}
            for s, v in by_stratum.items()
        },
        "confusion": {
            f"labeler {'yes' if h else 'no'}, judge {'yes' if j else 'no'}": number
            for (h, j), number in sorted(Counter(pairs).items())
        },
        "items": [
            {"id": sentence_id(n), "stratum": item["stratum"], "label": labels[n]}
            | {"verdict": item["verdict"] if item["stratum"] == "passing" else verdicts.get(n)}
            for n, item in enumerate(sample)
        ],
        "sample": (
            f"{TOTAL - CONSTRUCTED} natural sentences and {CONSTRUCTED} constructed negatives,"
            " shuffled; constructed negatives may be easier to catch than natural errors"
        ),
    }


def spot_check(
    sample: list[dict[str, Any]], verdicts: dict[int, str | None], labels: dict[int, bool]
) -> dict[str, Any]:
    """The follow-up check, too small for kappa (user decision): how many sentences the labels
    call not supported the judge failed too (anything but "yes"), and how many supported ones
    it passed."""
    items = [
        {"id": sentence_id(n), "model": item["model"], "label": labels[n]}
        | {"verdict": verdicts.get(n)}
        for n, item in enumerate(sample)
    ]
    unsupported = [item for item in items if not item["label"]]
    supported = [item for item in items if item["label"]]
    return {
        "n": len(items),
        "unscored": sum(item["verdict"] is None for item in items),
        "unsupported": len(unsupported),
        "caught": sum(item["verdict"] not in (None, "yes") for item in unsupported),
        "supported": len(supported),
        "supported_yes": sum(item["verdict"] == "yes" for item in supported),
        "items": items,
    }


def prepare(root: Path) -> list[dict[str, Any]]:
    """The frozen sample, drawn on the first run."""
    root.mkdir(parents=True, exist_ok=True)
    if not (root / SAMPLE).exists():
        cache = Cache(CACHE / "calls.jsonl")
        if root == FOLLOWUP_ROOT:
            pools: list[list[dict[str, Any]]] = []
            for model in FOLLOWUP_MODELS:
                report = latest_report(model)
                found = asyncio.run(candidates(report, cache))
                origin = {"model": model, "report": report["path"]}
                pools.append([item | origin for item in found["failing"]])
            sample = draw_followup(pools)
            counts = Counter(item["model"] for item in sample)
            print(f"Follow-up sample: {dict(counts)} out of {[len(pool) for pool in pools]}.")
        else:
            report = gate_off_report()
            found = asyncio.run(candidates(report, cache))
            sample = draw(found)
            for item in sample:
                item["report"] = report["path"]
            counts = Counter(item["stratum"] for item in sample)
            pools_by = {stratum: len(items) for stratum, items in found.items()}
            print(f"Sample drawn from {report['path']}: {dict(counts)} out of {pools_by}.")
        write_jsonl(root / SAMPLE, sample)
    return read_jsonl(root / SAMPLE)


def main() -> None:
    """No argument: label on screen. `export`: write the sample for an outside labeler.
    `import`: score the judge against that labeler's labels (claude_labels.jsonl). A first
    argument `followup` works on the second sample instead of v1's."""
    words = sys.argv[1:]
    followup = words[:1] == ["followup"]
    words = words[1:] if followup else words
    command = words[0] if words else ""
    if command not in ("", "export", "import") or len(words) > 1:
        raise SystemExit("usage: python -m evals.calibrate [followup] [export|import]")
    root = FOLLOWUP_ROOT if followup else ROOT
    enable_ansi()
    settings = load_settings(EvalSettings)
    configure_logging("calibrate", "WARNING")
    field = PROVIDER_KEYS[settings.llm_judge.partition(":")[0]]
    secret = getattr(settings, field) if field else None
    if field and not (secret and secret.get_secret_value()):
        raise SystemExit(f"LLM_JUDGE needs {field.upper()}.")
    sample = prepare(root)
    if command == "export":
        export(sample, root)
        return
    if command == "import":
        labels, labeler = imported(sample, read_jsonl(root / IMPORT))
    else:
        print(GUIDE, flush=True)
        if key_or_quit() == "q" or not label(sample, root):
            print("\nStopped; make calibrate resumes where you stopped.")
            return
        labels = {row["item"]: row["supported"] for row in read_jsonl(root / LABELS)}
        labeler = "human"
    try:
        verdicts = asyncio.run(new_verdicts(sample, Cache(CACHE / "calls.jsonl")))
    except Stop as stop:
        raise SystemExit(f"{stop} The labels are saved; rerun to finish.") from None
    score = spot_check if followup else agreement
    result: dict[str, Any] = {**score(sample, verdicts, labels), "labeler": labeler}
    result["judge"] = settings.llm_judge
    body = json.dumps(result, indent=1) + "\n"  # v1's is CALIBRATION, which the harness reads
    (root / "result.json").write_text(body, encoding="utf-8", newline="\n")
    if followup:
        print(
            f"\nSpot check: the judge failed {result['caught']} of the {result['unsupported']}"
            f" sentences {labeler} labeled not supported, and passed {result['supported_yes']} of"
            f" the {result['supported']} labeled supported ({result['unscored']} unscored)."
        )
        return
    low, high = result["kappa_ci"]
    counts = "count" if result["kappa"] >= 0.7 else "do not count"
    print(
        f"\nThe judge against {labeler}'s labels: {result['n']} sentences, agreement"
        f" {result['agreement']:.1%}, Cohen's kappa {result['kappa']:.2f} (95% CI {low:.2f}"
        f" to {high:.2f}). Citation precision and faithfulness {counts}."
    )


if __name__ == "__main__":
    main()
