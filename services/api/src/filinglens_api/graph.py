"""GraphQL contract (Strawberry). Resolvers read through the same Backend as the REST routes."""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated, Any

import strawberry
from fastapi import Depends
from graphql import GraphQLError
from pydantic import BaseModel, ValidationError
from strawberry.extensions import MaskErrors
from strawberry.relay import PageInfo

from filinglens_api import schemas
from filinglens_api.backend import (
    Backend,
    CompanyKey,
    FilingKey,
    ItemKey,
    encode_cursor,
    get_backend,
)
from filinglens_api.limits import answer_limits_for, timed_answer
from filinglens_api.schemas import FiscalPeriod, FormType
from filinglens_core.errors import FilingLensError, InvalidInputError

FIRST = "Page size (at most 100)."
AFTER = "endCursor from the previous page."

# The REST enums double as GraphQL enums, whose values are the member names (FORM_10K).
strawberry.enum(FormType)
strawberry.enum(FiscalPeriod)


# Relay cursor connections. strawberry.relay's own types require relay.Node items (global ids).
@strawberry.type(description="An edge in a connection.")
class Edge[T]:
    cursor: str = strawberry.field(description="A cursor for use in pagination")
    node: T = strawberry.field(description="The item at the end of the edge")


@strawberry.type(description="A connection to a list of items.")
class Connection[T]:
    page_info: PageInfo = strawberry.field(description="Pagination data for this connection")
    edges: list[Edge[T]] = strawberry.field(description="Contains the nodes in this connection")


def _backend(info: strawberry.Info) -> Backend:
    return info.context["backend"]


def _page_size(first: int) -> int:
    if not 1 <= first <= 100:
        raise InvalidInputError("first must be between 1 and 100.")
    return first


def _connection[M, N](
    page: schemas.Page[M], node: Callable[[M], N], key: Callable[[M], BaseModel]
) -> Connection[N]:
    """A Relay connection whose edge cursors are the same keyset cursors as REST."""
    edges = [Edge(cursor=encode_cursor(key(item)), node=node(item)) for item in page.items]
    return Connection(
        edges=edges,
        page_info=PageInfo(
            has_next_page=page.next_cursor is not None,
            has_previous_page=False,  # keyset pages only go forward
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
        ),
    )


def _item_key(item: schemas.Chunk | schemas.FinancialFact) -> ItemKey:
    return ItemKey(id=item.id)


def _filing_key(filing: schemas.Filing) -> FilingKey:
    return FilingKey(filed_on=filing.filed_on, accession_number=filing.accession_number)


@strawberry.type
class Usage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


@strawberry.type(description="Exactly one of chunkId (filing text) and factId (XBRL fact) is set.")
class Citation:
    chunk_id: strawberry.ID | None
    fact_id: strawberry.ID | None
    quote: str
    filing_url: str


@strawberry.type
class Answer:
    answer: str
    citations: list[Citation]
    degraded: bool = strawberry.field(
        description="True when retrieval skipped the reranker after a timeout."
    )
    usage: Usage
    refused: bool = strawberry.field(
        description="True when FilingLens declined to answer; `answer` says why."
    )
    warnings: list[str] = strawberry.field(
        description="Validation notes, such as sentences removed because a check failed."
    )

    @classmethod
    def of(cls, answer: schemas.Answer) -> "Answer":
        return cls(
            answer=answer.answer,
            citations=[Citation(**citation.model_dump()) for citation in answer.citations],
            degraded=answer.degraded,
            usage=Usage(**answer.usage.model_dump()),
            refused=answer.refused,
            warnings=answer.warnings,
        )


@strawberry.type
class Chunk:
    id: strawberry.ID
    section_id: strawberry.ID
    text: str

    @classmethod
    def of(cls, chunk: schemas.Chunk) -> "Chunk":
        return cls(**chunk.model_dump())


@strawberry.type
class FinancialFact:
    id: strawberry.ID
    concept: str
    label: str
    value: float
    unit: str
    period_start: date | None
    period_end: date
    fiscal_year: int
    fiscal_period: FiscalPeriod
    accession_number: str

    @classmethod
    def of(cls, fact: schemas.FinancialFact) -> "FinancialFact":
        return cls(**fact.model_dump())


@strawberry.type
class Section:
    id: strawberry.ID
    item: str
    title: str
    accession_number: strawberry.Private[str]

    @strawberry.field(description="This section's text chunks, in reading order.")
    async def chunks(
        self,
        info: strawberry.Info,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[Chunk]:
        page = await _backend(info).list_chunks(
            self.accession_number, _page_size(first), after, section_id=self.id
        )
        return _connection(page, Chunk.of, _item_key)


@strawberry.type
class Filing:
    accession_number: str
    cik: int
    form_type: FormType
    filed_on: date
    period_end: date
    fiscal_year: int
    fiscal_period: FiscalPeriod
    url: str

    @classmethod
    def of(cls, filing: schemas.Filing) -> "Filing":
        return cls(**filing.model_dump())

    @strawberry.field
    async def sections(self, info: strawberry.Info) -> list[Section]:
        sections = await _backend(info).list_sections(self.accession_number)
        return [Section(**s.model_dump(), accession_number=self.accession_number) for s in sections]

    @strawberry.field(description="All text chunks of the filing, in reading order.")
    async def chunks(
        self,
        info: strawberry.Info,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[Chunk]:
        page = await _backend(info).list_chunks(self.accession_number, _page_size(first), after)
        return _connection(page, Chunk.of, _item_key)

    @strawberry.field(description="XBRL facts reported in the filing, optionally one concept.")
    async def facts(
        self,
        info: strawberry.Info,
        concept: str | None = None,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[FinancialFact]:
        page = await _backend(info).list_facts(
            self.accession_number, _page_size(first), after, concept=concept
        )
        return _connection(page, FinancialFact.of, _item_key)


async def _filings(
    info: strawberry.Info,
    first: int,
    after: str | None,
    cik: int | None,
    form_type: FormType | None,
    fiscal_year: int | None,
) -> Connection[Filing]:
    page = await _backend(info).list_filings(
        _page_size(first), after, cik=cik, form_type=form_type, fiscal_year=fiscal_year
    )
    return _connection(page, Filing.of, _filing_key)


@strawberry.type
class Company:
    cik: int
    ticker: str
    name: str

    @strawberry.field(description="This company's filings, newest first.")
    async def filings(
        self,
        info: strawberry.Info,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[Filing]:
        return await _filings(info, first, after, self.cik, form_type, fiscal_year)


@strawberry.type
class Query:
    @strawberry.field(description="Tracked companies in CIK order.")
    async def companies(
        self,
        info: strawberry.Info,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[Company]:
        page = await _backend(info).list_companies(_page_size(first), after)
        return _connection(
            page, lambda c: Company(**c.model_dump()), lambda c: CompanyKey(cik=c.cik)
        )

    @strawberry.field(description="Ingested filings, newest first.")
    async def filings(
        self,
        info: strawberry.Info,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
        first: Annotated[int, strawberry.argument(description=FIRST)] = 20,
        after: Annotated[str | None, strawberry.argument(description=AFTER)] = None,
    ) -> Connection[Filing]:
        return await _filings(info, first, after, cik, form_type, fiscal_year)

    @strawberry.field(description="Answer a question from the filings, with citations.")
    async def answer(
        self,
        info: strawberry.Info,
        question: str,
        company_ids: Annotated[
            list[int] | None, strawberry.argument(description="Only these companies (CIKs).")
        ] = None,
        fiscal_years: list[int] | None = None,
    ) -> Answer:
        try:
            request = schemas.AnswerRequest(
                question=question, company_ids=company_ids, fiscal_years=fiscal_years
            )
        except ValidationError as exc:
            problems = exc.errors(include_input=False, include_url=False)
            raise InvalidInputError(
                "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in problems)
            ) from None
        await info.context["answer_limits"]()  # REST's: 10 a minute per key, the AI budget
        return Answer.of(await timed_answer(_backend(info), request))


class ErrorCodes(MaskErrors):
    """Taxonomy errors keep their message and gain extensions.code; other errors are masked."""

    def __init__(self) -> None:
        super().__init__(
            should_mask_error=lambda error: (
                error.original_error is not None
                and not isinstance(error.original_error, GraphQLError)
            )
        )

    def anonymise_error(self, error: GraphQLError) -> GraphQLError:
        original = error.original_error
        message, code = (
            (str(original), original.code)
            if isinstance(original, FilingLensError)
            else (self.error_message, "internal")
        )
        return GraphQLError(
            message,
            error.nodes,
            error.source,
            error.positions,
            error.path,
            extensions={"code": code},
        )


async def get_context(
    backend: Annotated[Backend, Depends(get_backend)],
    answer_limits: Annotated[Callable[[], Awaitable[None]], Depends(answer_limits_for)],
) -> dict[str, Any]:
    return {"backend": backend, "answer_limits": answer_limits}


schema = strawberry.Schema(query=Query, extensions=[ErrorCodes])
