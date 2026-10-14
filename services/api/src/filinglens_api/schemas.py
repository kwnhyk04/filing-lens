"""REST contract models (pydantic v2). A change here changes contracts/openapi.json."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Named enums become shared components in the spec; GraphQL reuses them (member names there).
class FormType(StrEnum):
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"


class FiscalPeriod(StrEnum):
    FY = "FY"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"


Cik = Annotated[int, Field(ge=1, le=9_999_999_999, description="SEC Central Index Key.")]
FiscalYear = Annotated[int, Field(ge=1993, le=2100)]
AccessionNumber = Annotated[
    str, Field(pattern=r"^\d{10}-\d{2}-\d{6}$", examples=["0000320193-25-000079"])
]
Url = Annotated[str, Field(json_schema_extra={"format": "uri"})]


class Schema(BaseModel):
    # Responses always include fields that have defaults, so the contract marks them required.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Health(Schema):
    status: Literal["ok", "unavailable"]
    checks: dict[str, bool] = {}


class FieldError(BaseModel):
    detail: str
    pointer: str = Field(description="JSON Pointer to the invalid input, such as /query/limit.")


def _absent(value: object) -> bool:
    return value is None


class Problem(BaseModel):
    """RFC 9457 problem details (application/problem+json). Absent members are omitted."""

    type: str = "about:blank"
    title: str = Field(description="HTTP status phrase.")
    status: int
    detail: str | None = Field(default=None, exclude_if=_absent)
    code: str = Field(description="Stable machine-readable error code, such as rate_limited.")
    errors: list[FieldError] | None = Field(
        default=None,
        exclude_if=_absent,
        description="Each invalid input; sent with validation_failed only.",
    )


class Page[T](Schema):
    items: list[T]
    next_cursor: str | None = Field(
        description="Send as `cursor` to get the next page; null on the last page."
    )


class Company(Schema):
    cik: Cik
    ticker: str
    name: str


class CompanyPage(Page[Company]):
    pass


class Filing(Schema):
    accession_number: AccessionNumber
    cik: Cik
    form_type: FormType
    filed_on: date
    period_end: date
    fiscal_year: FiscalYear
    fiscal_period: FiscalPeriod
    url: Url


class FilingPage(Page[Filing]):
    pass


class IngestJobRequest(Schema):
    ciks: list[Cik] = Field(min_length=1, max_length=50)
    form_types: list[FormType] = Field(min_length=1)
    since: date = Field(description="Ingest filings filed on or after this date.")


class IngestJobAccepted(Schema):
    job_id: UUID


class FilingCounts(Schema):
    """How many of the job's filings are in each status."""

    pending: int
    running: int
    succeeded: int
    failed: int
    skipped: int = Field(description="Already ingested by an earlier job.")


class FilingFailure(Schema):
    accession_number: AccessionNumber
    cik: Cik
    form_type: FormType
    error: str
    attempts: int
    failed_at: datetime


class FailurePage(Page[FilingFailure]):
    pass


class IngestJob(Schema):
    job_id: UUID
    status: Literal["queued", "running", "succeeded", "partially_failed", "failed"]
    request: IngestJobRequest
    created_at: datetime
    counts: FilingCounts
    failures: FailurePage


class SearchHit(Schema):
    chunk_id: str
    score: float
    text: str
    section: str
    filing: Filing


class SearchPage(Page[SearchHit]):
    degraded: bool = Field(
        description="True when the reranker timed out, so hits keep their fused order."
    )


class AnswerRequest(Schema):
    question: str = Field(min_length=3, max_length=1000)
    company_ids: list[Cik] | None = Field(
        default=None, max_length=20, description="Only use these companies (CIKs)."
    )
    fiscal_years: list[FiscalYear] | None = Field(default=None, max_length=10)


class Citation(Schema):
    """Exactly one source: chunk_id for filing text, fact_id for an XBRL fact."""

    chunk_id: str | None = None
    fact_id: str | None = None
    quote: str
    filing_url: Url

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.chunk_id is None) == (self.fact_id is None):
            raise ValueError("set exactly one of chunk_id and fact_id")
        return self


class Usage(Schema):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0, description="Estimated provider cost; 0 on free tiers.")


class Answer(Schema):
    answer: str
    citations: list[Citation]
    degraded: bool = Field(description="True when retrieval skipped the reranker after a timeout.")
    usage: Usage


class AnswerDelta(Schema):
    type: Literal["delta"] = "delta"
    text: str


class AnswerCompleted(Schema):
    type: Literal["completed"] = "completed"
    answer: Answer


class AnswerFailed(Schema):
    type: Literal["failed"] = "failed"
    problem: Problem


AnswerEvent = Annotated[AnswerDelta | AnswerCompleted | AnswerFailed, Field(discriminator="type")]


# GraphQL-only shapes: no REST route returns them yet, so they stay out of openapi.json.
class Section(Schema):
    id: str
    item: str = Field(examples=["1A"])
    title: str = Field(examples=["Risk Factors"])


class Chunk(Schema):
    id: str
    section_id: str
    text: str


class ChunkPage(Page[Chunk]):
    pass


class FinancialFact(Schema):
    id: str
    concept: str = Field(examples=["us-gaap:Revenues"])
    label: str
    value: float
    unit: str = Field(examples=["USD"])
    period_start: date | None
    period_end: date
    fiscal_year: FiscalYear
    fiscal_period: FiscalPeriod
    accession_number: AccessionNumber


class FactPage(Page[FinancialFact]):
    pass
