"""Question router: one structured call to the small model (LLM_ROUTER) picks the answer path."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

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
# Strict JSON Schema: every property required, null where a value may be missing.
SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": list(ROUTES)},
        "tickers": {"type": "array", "items": {"type": "string"}},
        "fiscal_years": {"type": "array", "items": {"type": "integer"}},
        "fiscal_period": {"type": ["string", "null"], "enum": [*PERIODS, None]},
        "metric": {"type": ["string", "null"], "enum": [*METRICS, None]},
    },
    "required": ["route", "tickers", "fiscal_years", "fiscal_period", "metric"],
    "additionalProperties": False,
}


class Routing(BaseModel):
    route: Literal["numeric", "textual", "comparison", "out_of_scope"]
    tickers: list[str]
    fiscal_years: list[int]
    fiscal_period: Literal["FY", "Q1", "Q2", "Q3", "Q4"] | None
    metric: str | None

    @field_validator("tickers")
    @classmethod
    def _upper(cls, tickers: list[str]) -> list[str]:
        return sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})

    @field_validator("metric")
    @classmethod
    def _known(cls, metric: str | None) -> str | None:
        return metric if metric in METRICS else None


def system_prompt(today: date) -> str:
    return f"""\
You route questions about US public companies' SEC filings (10-K and 10-Q) for a research tool.
Reply with JSON only.
route: "numeric" when the question asks for one reported financial figure (revenue, net income,
EPS, total assets, cash...); "comparison" when it compares companies or periods; "textual" for
anything else the filings can answer (business, risks, strategy, reasons for a change);
"out_of_scope" only for topics SEC filings never cover: stock price forecasts, investment advice,
general knowledge, other subjects. A question about a company's reported figures, business or
risks is in scope whatever period it names, even one not reported yet: "What was Apple's revenue
in fiscal 2031?" is numeric with fiscal_years [2031].
tickers: the stock tickers of the companies the question names, such as AAPL; [] if none.
fiscal_years: the fiscal years the question asks about, such as [2025]; [] if it names none.
Today is {today.isoformat()}, so "last year" is {today.year - 1}.
fiscal_period: "FY" for a full year, "Q1" to "Q4" for a quarter, null if it does not say.
metric: the figure asked for, one of {", ".join(METRICS)}; null if none fits."""


def parse(reply: str, model: str) -> Routing:
    """The routing in a reply, or UpstreamError when the reply does not hold to the schema."""
    try:
        return Routing.model_validate_json(reply)
    except ValidationError as exc:
        raise UpstreamError(f"{model} replied with an unusable route.") from exc
