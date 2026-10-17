"""The eval judge (LLM_JUDGE): one call per answer checks each sentence against the full text of
the sources it cites. Faithfulness and citation precision come from its verdicts, and count only
once `make calibrate` shows it agrees with a human (Cohen's kappa 0.7 or more).

The prompt and schema are frozen with the calibration: a change needs a new calibration.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from filinglens_llm.validate import split_sentences

MAX_TOKENS = 2048  # the JSON plus gpt-oss's short reasoning
CITE = re.compile(r"\[(\d+)\]")
SYSTEM = """\
You check answers written from SEC filings against the sources they cite. Use only the sources
a sentence cites, never outside knowledge. For each numbered sentence give:
- supported: "yes" if its cited sources state everything the sentence claims, "partly" if they
  state some of it, "no" if they state none of it. A rounded figure ($416.2 billion for
  416,161,000,000 USD) counts as stated; a figure the sources do not state, such as a growth
  rate computed from them, does not.
- citations: one entry per source the sentence cites, with supports true if that source states
  at least part of what the sentence claims, false otherwise.
Each source shows the quote the answer gave for it, then its full text; judge against the full
text. Reply with JSON only."""
SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "integer"},
                    "supported": {"type": "string", "enum": ["yes", "partly", "no"]},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "integer"},
                                "supports": {"type": "boolean"},
                            },
                            "required": ["source", "supports"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["sentence", "supported", "citations"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


class JudgeError(ValueError):
    """The judge's reply skipped, repeated or invented a sentence or a citation, or the answer
    cites a number with no source, so no reply could rate it."""


@dataclass(frozen=True)
class Cited:
    heading: str  # company and filing item, or the fact's concept and period
    quote: str  # the span the answer gave; a fact's value line
    text: str  # the whole chunk; a fact's value line


@dataclass(frozen=True)
class Verdict:
    supported: list[str]  # per sentence: yes, partly or no
    supports: list[bool]  # per citation of each sentence, in order


def sentences(answer: str) -> list[tuple[str, list[int]]]:
    """The answer's sentences, each with the citation numbers it carries, in order."""
    return [
        (sentence, list(dict.fromkeys(int(n) for n in CITE.findall(sentence))))
        for sentence in split_sentences(answer)
    ]


def user_prompt(question: str, answer: str, sources: Mapping[int, Cited]) -> str:
    """The judge's prompt; JudgeError before any call when a sentence cites a number with no
    source, which the judge may otherwise rate unseen (live replay, 2026-10-18)."""
    lines = [f"Question: {question}", "", "Sentences:"]
    for n, (sentence, cites) in enumerate(sentences(answer), 1):
        if any(cite not in sources for cite in cites):
            given = sorted(cite for cite in cites if cite in sources)
            raise JudgeError(f"sentence {n}: given sources {given}, cited {cites}")
        lines.append(f"{n}. {sentence} (cites {', '.join(map(str, cites))})")
    lines += ["", "Sources:"]
    for number, source in sorted(sources.items()):
        lines += [f"[{number}] {source.heading}", f'Quote given: "{source.quote}"', source.text, ""]
    return "\n".join(lines).rstrip()


def parse(reply: str, answer: str) -> Verdict:
    """The verdict per sentence and citation, in the answer's order."""
    try:
        rows = {row["sentence"]: row for row in json.loads(reply)["sentences"]}
    except (ValueError, KeyError, TypeError) as exc:
        raise JudgeError(f"unreadable reply: {exc}") from exc
    expected = sentences(answer)
    if sorted(rows) != list(range(1, len(expected) + 1)):
        raise JudgeError(f"judged sentences {sorted(rows)}, expected 1 to {len(expected)}")
    supported: list[str] = []
    supports: list[bool] = []
    for n, (_, cites) in enumerate(expected, 1):
        given = {item["source"]: item["supports"] for item in rows[n]["citations"]}
        if sorted(given) != sorted(cites):
            raise JudgeError(f"sentence {n}: judged sources {sorted(given)}, cited {cites}")
        supported.append(rows[n]["supported"])
        supports += [given[source] for source in cites]
    return Verdict(supported, supports)
