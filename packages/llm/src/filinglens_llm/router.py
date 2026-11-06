"""Question router: one structured call to the small model (LLM_ROUTER) picks the answer path.

The router sees the companies FilingLens tracks, and its tickers must come from them: the schema
holds them as an enum, and `problems` checks each reply in code for providers that do not enforce
one. The Answerer asks once more on a problem, then refuses a ticker that is still unknown.

A question worded as one about FilingLens itself (`about_wording`) also gets the about routes, for
the app and for its collection. Any other question sends the prompt and schema it always did.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from filinglens_core.errors import UpstreamError

# XBRL concepts that answer each metric, best first, and the unit to read them in.
METRICS: dict[str, tuple[str, tuple[str, ...]]] = {
    "revenue": (
        "USD",
        (
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:RevenuesNetOfInterestExpense",
            "us-gaap:SalesRevenueNet",
        ),
    ),
    "net_income": ("USD", ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss")),
    "eps_diluted": ("USD/shares", ("us-gaap:EarningsPerShareDiluted",)),
    "eps_basic": ("USD/shares", ("us-gaap:EarningsPerShareBasic",)),
    "operating_income": ("USD", ("us-gaap:OperatingIncomeLoss",)),
    "gross_profit": ("USD", ("us-gaap:GrossProfit",)),
    "total_assets": ("USD", ("us-gaap:Assets",)),
    "total_liabilities": ("USD", ("us-gaap:Liabilities",)),
    "stockholders_equity": (
        "USD",
        (
            "us-gaap:StockholdersEquity",
            "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
    ),
    "cash": (
        "USD",
        (
            "us-gaap:CashAndCashEquivalentsAtCarryingValue",
            "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ),
    ),
    "long_term_debt": ("USD", ("us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt")),
    "operating_cash_flow": ("USD", ("us-gaap:NetCashProvidedByUsedInOperatingActivities",)),
    "capital_expenditures": ("USD", ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",)),
    "research_and_development": ("USD", ("us-gaap:ResearchAndDevelopmentExpense",)),
    "dividends_per_share": ("USD/shares", ("us-gaap:CommonStockDividendsPerShareDeclared",)),
}
ROUTES = ("numeric", "textual", "comparison", "out_of_scope")
ABOUT = ("about_app", "about_collection")  # questions about FilingLens itself: see about_wording
# Forecast and advice wording (dev's o01 and o02): such a question keeps its out_of_scope route.
ADVICE = re.compile(
    r"\b(?:stock|share) price|\bgo(?:es|ing)? (?:up|down)\b|\bshould i\b"
    r"|\b(?:buy|sell)\b.{0,30}\b(?:shares?|stock)\b",
    re.IGNORECASE,
)
# A question about FilingLens itself: it is addressed or named, who made it is asked, or the
# collection is asked about with no company's business in it. Only such a question sees the about
# routes, so any other one reaches the router with the prompt and schema it always had. No golden
# question matches.
HELD = r"(?:companies|filings|documents|records|tickers|(?:fiscal\s+)?years)"
MADE = r"made|built|created|wrote|developed|designed|behind"
APOSTROPHE = "'\N{RIGHT SINGLE QUOTATION MARK}"
ABOUT_WORDING = re.compile(
    r"\b(?:you|your|yours|yourself|filinglens)\b"
    r"|\bthis\s+(?:app|application|site|website|tool|service|thing|page)\b"
    r"|\bhow\s+does\s+(?:this|it)\s+work\b"
    r"|\b(?:the|this)\s+(?:collection|corpus|database|dataset)\b"
    r"|\bthe\s+data\s+(?:last\s+)?(?:loaded|updated|refreshed)\b"
    r"|\bhow\s+(?:recent|fresh|current|old)\s+is\s+the\s+data\b"
    rf"|^\W*who(?:[{APOSTROPHE}]s|\s+is)?\s+(?:{MADE})\s+(?:this|it)\W*$"
    rf"|^\W*(?:which|what(?:\s+are)?|how\s+many)\s+(?:the\s+)?{HELD}"
    r"(?:\s+(?:are|is)\s+(?:there|covered|included|available|tracked|indexed|loaded))?\W*$"
    rf"|\b{HELD}\b.{{0,40}}\bhere\b|\bin\s+here\b"
    r"|^\W*(?:what(?:'s|\s+is)\s+)?(?:the\s+)?(?:year|company|filing)\s+coverage\W*$"
    r"|^\W*(?:is|are)\s+.{1,60}?\s+(?:covered|included|available|tracked)\W*$"
    r"|^\W*list\s+(?:the\s+|all\s+)*companies\W*$",
    re.IGNORECASE,
)
# A fiscal year tied to a filing: "its fiscal 2026 annual report", "FY2027 10-K", "the 10-K for
# fiscal 2027". Any other fiscal year in a question is a period, which an earlier 10-K may cover.
FISCAL_YEAR = r"(?:fiscal(?:\s+year)?|FY)\s?((?:19|20)\d\d)"
ANNUAL_REPORT = r"(?:form\s+)?(?:10-?k|annual\s+report)"
FILING_YEAR = re.compile(
    rf"\b{FISCAL_YEAR}\s+{ANNUAL_REPORT}\b"
    rf"|\b{ANNUAL_REPORT}\s+(?:for|of)\s+(?:the\s+)?{FISCAL_YEAR}\b",
    re.IGNORECASE,
)
# A word written as a name: capitalised, and not only because it opens a sentence.
NAME_WORD = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][A-Za-z0-9]*")
PERIODS = ("FY", "Q1", "Q2", "Q3", "Q4")
MAX_TOKENS = 400  # the JSON plus gpt-oss's short reasoning
NAME_NOISE = {
    "inc",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "ltd",
    "group",
    "the",
    "de",
    "and",
}


def schema(companies: Mapping[str, str], *, about: bool = False) -> dict[str, Any]:
    """Strict JSON Schema: every property required, null where a value may be missing, and the
    tickers limited to the tracked companies (`companies`: name by ticker). `about` adds the about
    routes, for a question in about_wording."""
    ticker: dict[str, Any] = {"type": "string"}
    if companies:
        ticker["enum"] = sorted(companies)
    properties = {
        "route": {"type": "string", "enum": [*ROUTES, *ABOUT] if about else list(ROUTES)},
        "tickers": {"type": "array", "items": ticker},
        "other_companies": {"type": "array", "items": {"type": "string"}},
        "fiscal_years": {"type": "array", "items": {"type": "integer"}},
        "fiscal_period": {"type": ["string", "null"], "enum": [*PERIODS, None]},
        "metric": {"type": ["string", "null"], "enum": [*METRICS, None]},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


class Routing(BaseModel):
    route: Literal[
        "numeric", "textual", "comparison", "out_of_scope", "about_app", "about_collection"
    ]
    tickers: list[str]
    # Companies the question names that FilingLens does not track, as the question names them.
    other_companies: list[str] = Field(default_factory=list[str])
    fiscal_years: list[int]
    fiscal_period: Literal["FY", "Q1", "Q2", "Q3", "Q4"] | None
    metric: str | None

    @field_validator("tickers")
    @classmethod
    def _upper(cls, tickers: list[str]) -> list[str]:
        return sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})

    @field_validator("other_companies")
    @classmethod
    def _named(cls, names: list[str]) -> list[str]:
        return list(dict.fromkeys(name.strip() for name in names if name.strip()))

    @field_validator("metric")
    @classmethod
    def _known(cls, metric: str | None) -> str | None:
        return metric if metric in METRICS else None


# Added to the prompt for a question in about_wording; any other question's stays as it was.
ABOUT_RULES = """

Two more routes, for questions about FilingLens itself rather than a company's filings.
"about_app": what FilingLens is, what it can do, how it works or who made it, such as "What is this
app?", "What can you do?", "How does this work?", "Who built this?" or "Who's behind FilingLens?".
"about_collection": what it holds, however loosely it is put: how many or which companies, filings,
fiscal years or filing types, how recent its data is, or whether it has a company, such as "How
many companies do you have?", "Which companies?", "What years do you cover?", "What filings are
included?", "What are the companies records here?", "How many companies are in here and year
coverage?" or "Do you have Tesla?". Put such a company in tickers or other_companies, as above.
Neither route fits a question about what a company reported or does, whatever its words: "Do you
have Apple's revenue for fiscal 2025?" is numeric, "What can you tell me about Tesla's risks?" is
textual, and so is "Which companies here mention tariffs?". Neither fits anything else: weather,
general knowledge and advice stay out_of_scope even when they say "you", such as "Can you recommend
a stock?" or "Do you know who won the World Cup?"."""


def system_prompt(today: date, companies: Mapping[str, str], *, about: bool = False) -> str:
    listed = "; ".join(f"{ticker} {name}" for ticker, name in sorted(companies.items()))
    prompt = f"""\
You route questions about US public companies' SEC filings (10-K and 10-Q) for a research tool.
Reply with JSON only.
route: "numeric" when the question asks for one reported financial figure (revenue, net income,
EPS, total assets, cash...); "comparison" when it compares a reported figure across companies or
periods; "textual" for anything else the filings can answer (business, risks, strategy, reasons
for a change, comparisons of anything but a figure); "out_of_scope" only for topics SEC filings
never cover: stock price forecasts, investment advice, general knowledge, other subjects. A
question about a company's reported figures, business or risks is in scope whatever period it
names, even one not reported yet: "What was Apple's revenue in fiscal 2031?" is numeric with
fiscal_years [2031].
FilingLens tracks these companies (ticker, then name): {listed or "none yet"}.
tickers: the tickers, from that list only, of the companies the question names; [] if it names
none of them.
other_companies: the companies the question names that are not on that list, as the question
names them; [] if none.
fiscal_years: the fiscal years the question asks about, such as [2025]; [] if it names none.
Today is {today.isoformat()}, so "last year" is {today.year - 1}.
fiscal_period: "FY" for a full year, "Q1" to "Q4" for a quarter, null if it does not say.
metric: the figure asked for, one of {", ".join(METRICS)}; null if none fits. A comparison always
has one: "total revenue" is revenue, "net income" is net_income."""
    return prompt + ABOUT_RULES if about else prompt


def about_wording(question: str) -> bool:
    """Whether a question may be about FilingLens itself, so the router may route it there. Advice
    wording never is: "Should I buy your top stock?" stays with the routes it always had."""
    return bool(ABOUT_WORDING.search(question)) and not ADVICE.search(question)


def problems(routing: Routing, companies: Mapping[str, str]) -> list[str]:
    """What breaks the rules in a reply the schema let through: a ticker FilingLens does not
    track (from a provider that ignores the enum), or a comparison without its metric."""
    found: list[str] = []
    unknown = [ticker for ticker in routing.tickers if ticker not in companies]
    if unknown:
        found.append(
            f"tickers {', '.join(unknown)} are not on the list; name such companies in"
            " other_companies"
        )
    if routing.route == "comparison" and routing.metric is None:
        found.append("a comparison needs its metric")
    return found


def _name_words(name: str) -> list[str]:
    """A company name's words without legal suffixes: "COCA COLA CO" and "Coca-Cola" agree."""
    return [word for word in re.findall(r"[a-z0-9]+", name.lower()) if word not in NAME_NOISE]


def resolve(routing: Routing, companies: Mapping[str, str]) -> Routing:
    """Move each other company that names exactly one tracked company (by its ticker, or by its
    name's leading words) into tickers: the model sometimes misses a match on the list."""
    tickers, others = set(routing.tickers), list[str]()
    for name in routing.other_companies:
        words = _name_words(name)
        matches = [
            ticker
            for ticker, company in companies.items()
            if name.strip().upper() == ticker
            or (words and _name_words(company)[: len(words)] == words)
        ]
        if len(matches) == 1:
            tickers.add(matches[0])
        else:
            others.append(name)
    return routing.model_copy(update={"tickers": sorted(tickers), "other_companies": others})


def guess(question: str, companies: Mapping[str, str]) -> tuple[list[str], list[int]]:
    """The tracked companies and fiscal years a question names, read in code so the search can
    start while the router runs: a company by its ticker, its whole name in any case, or its
    name's first word written as a name, so "Did Visa" counts and "visa rules" or a sentence's
    opening "Home prices" do not (review, 2026-11-04). A year by its four digits. A wrong guess
    costs that search, and fill's scope when the router names no company."""
    spoken = " " + " ".join(re.findall(r"[a-z0-9]+", question.lower())) + " "
    upper = set(re.findall(r"\b[A-Z]{2,5}\b", question))
    written = {word.lower() for word in NAME_WORD.findall(question.strip())}

    def named(ticker: str, name: str) -> bool:
        words = _name_words(name)
        whole = len(words) > 1 and f" {' '.join(words)} " in spoken
        return ticker in upper or whole or (bool(words) and words[0] in written)

    tickers = sorted(ticker for ticker, name in companies.items() if named(ticker, name))
    years = sorted({int(year) for year in re.findall(r"\b(?:19|20)\d\d\b", question)})
    return tickers, years


def second_look(routing: Routing, question: str, companies: Mapping[str, str]) -> list[str]:
    """The tracked companies an out-of-scope question names, unless it asks for a forecast or
    advice: the router sent x13, x14 and x18 (test, 2026-10-17) out of scope, and routed all three
    textual when asked again, so such a question gets a second look."""
    if routing.route != "out_of_scope" or ADVICE.search(question):
        return []
    return guess(question, companies)[0]


def second_look_prompt(question: str, names: Sequence[str]) -> str:
    """The question again, with the scope rule, and no claim that the last reply was wrong."""
    rule = (
        f"The question names {', '.join(names)}, which FilingLens tracks. Route it out_of_scope"
        " only if SEC filings never cover its topic (stock price forecasts, investment advice,"
        " general knowledge); a question about what a company's filings report is in scope."
    )
    return "\n".join([question, "", rule])


def fill(routing: Routing, named: Sequence[str]) -> Routing:
    """The one tracked company the question names (`guess`), when the router named none and no
    other company (x01, x06, t10, a03 searched every company or missed their time trap)."""
    if routing.route in ("out_of_scope", "about_app") or routing.tickers or routing.other_companies:
        return routing
    return routing.model_copy(update={"tickers": list(named)}) if len(named) == 1 else routing


def settle(routing: Routing) -> Routing:
    """The route the plan follows, for an about reply that asks of a company: a figure a named
    company reported is numeric, and an app question that names a company is about that company's
    filings ("Do you have Apple's revenue?", "What can you tell me about Tesla?")."""
    if routing.route in ABOUT and routing.metric and routing.tickers:
        return routing.model_copy(update={"route": "numeric"})
    if routing.route == "about_app" and (routing.tickers or routing.other_companies):
        return routing.model_copy(update={"route": "textual"})
    return routing


def filing_years(question: str) -> list[int]:
    """The fiscal years whose 10-K a question asks for, for the time-trap check when the router
    leaves them out (t07, "its fiscal 2026 annual report"). Any other year is the period asked
    about, not a filing: the latest 10-K may cover "due in fiscal 2027" (review, 2026-11-04)."""
    return sorted({int(match[1] or match[2]) for match in FILING_YEAR.finditer(question)})


def retry_prompt(question: str, broken: Sequence[str]) -> str:
    """The question again, with what the last reply got wrong."""
    rules = [f"- {problem}" for problem in broken]
    return "\n".join([question, "", "Your last reply broke the rules:", *rules, "Reply again."])


def parse(reply: str, model: str) -> Routing:
    """The routing in a reply, or UpstreamError when the reply does not hold to the schema."""
    try:
        return Routing.model_validate_json(reply)
    except ValidationError as exc:
        raise UpstreamError(f"{model} replied with an unusable route.") from exc
