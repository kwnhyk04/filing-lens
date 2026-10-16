"""Question router: one structured call to the small model (LLM_ROUTER) picks the answer path.

The router sees the companies FilingLens tracks, and its tickers must come from them: the schema
holds them as an enum, and `problems` checks each reply in code for providers that do not enforce
one. The Answerer asks once more on a problem, then refuses a ticker that is still unknown.
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


def schema(companies: Mapping[str, str]) -> dict[str, Any]:
    """Strict JSON Schema: every property required, null where a value may be missing, and the
    tickers limited to the tracked companies (`companies`: name by ticker)."""
    ticker: dict[str, Any] = {"type": "string"}
    if companies:
        ticker["enum"] = sorted(companies)
    properties = {
        "route": {"type": "string", "enum": list(ROUTES)},
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
    route: Literal["numeric", "textual", "comparison", "out_of_scope"]
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


def system_prompt(today: date, companies: Mapping[str, str]) -> str:
    listed = "; ".join(f"{ticker} {name}" for ticker, name in sorted(companies.items()))
    return f"""\
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
    start while the router runs: a company by its ticker or its name's first word, a year by
    its four digits. A wrong guess costs only that search, which is kept when the router agrees."""
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    upper = set(re.findall(r"\b[A-Z]{2,5}\b", question))

    def named(ticker: str, name: str) -> bool:
        first = _name_words(name)[:1]
        return ticker in upper or (bool(first) and first[0] in words)

    tickers = sorted(ticker for ticker, name in companies.items() if named(ticker, name))
    years = sorted({int(year) for year in re.findall(r"\b(?:19|20)\d\d\b", question)})
    return tickers, years


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
