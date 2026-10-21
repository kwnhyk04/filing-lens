"""GraphQL contract (Strawberry). Resolvers read through the same Backend as the REST routes."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from functools import partial
from typing import Annotated, Any

import strawberry
import structlog
from fastapi import Depends
from graphql import GraphQLError, ValueNode, VariableNode
from pydantic import BaseModel, ValidationError
from strawberry.dataloader import DataLoader
from strawberry.extensions import (
    DisableIntrospection,
    MaskErrors,
    MaxAliasesLimiter,
    QueryDepthLimiter,
)
from strawberry.relay import PageInfo
from strawberry.types import ExecutionContext

from filinglens_api import schemas
from filinglens_api.backend import (
    Backend,
    ChunkSource,
    CompanyKey,
    FilingKey,
    ItemKey,
    encode_cursor,
    get_backend,
)
from filinglens_api.limits import answer_limits_for, timed_answer
from filinglens_api.schemas import FiscalPeriod, FormType
from filinglens_core.errors import FilingLensError, InvalidInputError, NotFoundError

FIRST = "Page size (at most 100)."
AFTER = "endCursor from the previous page."
MAX_IDS = 20
MAX_DEPTH = 6  # Coverage and Filings, the deepest operations in clients/operations.graphql
MAX_ALIASES = 0  # no client sends one, and each would multiply what a query may look up
IDS = (
    f"Up to {MAX_IDS} ids per call, of 1 to 64 characters each. Results keep the order given,"
    " hold each id once and leave unknown ids out."
)
BAD_VALUE = "Invalid value for an argument or variable."  # never the value: it is user input
log = structlog.get_logger(__name__)

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


def _ids(ids: list[strawberry.ID]) -> list[str]:
    if len(ids) > MAX_IDS or not all(1 <= len(i) <= 64 and "\x00" not in i for i in ids):
        raise InvalidInputError(
            f"ids takes at most {MAX_IDS} ids, each 1 to 64 characters with no NUL."
        )
    return [str(i) for i in ids]


async def _company(info: strawberry.Info, known: schemas.Company | None, cik: int) -> "Company":
    # Shielded: a link cancelled by a sibling's error must not cancel what other links await.
    company = known or await asyncio.shield(info.context["companies"].load(cik))
    return Company(**company.model_dump())


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
    source: strawberry.Private[ChunkSource | None] = None  # set when looked up by id

    @classmethod
    def of(cls, chunk: schemas.Chunk, source: ChunkSource | None = None) -> "Chunk":
        return cls(**chunk.model_dump(), source=source)

    async def _source(self, info: strawberry.Info) -> ChunkSource:
        # Shielded, as in _company: other links may await the same lookup.
        return self.source or await asyncio.shield(info.context["chunk_sources"].load(self.id))

    @strawberry.field(description="The section the chunk belongs to.")
    async def section(self, info: strawberry.Info) -> "Section":
        source = await self._source(info)
        return Section(
            **source.section.model_dump(), accession_number=source.filing.accession_number
        )

    @strawberry.field(description="The filing the chunk comes from.")
    async def filing(self, info: strawberry.Info) -> "Filing":
        source = await self._source(info)
        return Filing.of(source.filing, source.company)


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
    cik: strawberry.Private[int]
    known_company: strawberry.Private[schemas.Company | None] = None

    @classmethod
    def of(
        cls, fact: schemas.FinancialFact, cik: int, company: schemas.Company | None = None
    ) -> "FinancialFact":
        return cls(**fact.model_dump(), cik=cik, known_company=company)

    @strawberry.field(description="The company that reported the fact.")
    async def company(self, info: strawberry.Info) -> "Company":
        return await _company(info, self.known_company, self.cik)


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
    known_company: strawberry.Private[schemas.Company | None] = None

    @classmethod
    def of(cls, filing: schemas.Filing, company: schemas.Company | None = None) -> "Filing":
        return cls(**filing.model_dump(), known_company=company)

    @strawberry.field(description="The company that filed it.")
    async def company(self, info: strawberry.Info) -> "Company":
        return await _company(info, self.known_company, self.cik)

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
        if concept is not None and "\x00" in concept:  # Postgres refuses a NUL in text
            raise InvalidInputError("concept must not hold a NUL character.")
        page = await _backend(info).list_facts(
            self.accession_number, _page_size(first), after, concept=concept
        )
        return _connection(page, lambda fact: FinancialFact.of(fact, self.cik), _item_key)


async def _filings(
    info: strawberry.Info,
    first: int,
    after: str | None,
    cik: int | None,
    form_type: FormType | None,
    fiscal_year: int | None,
) -> Connection[Filing]:
    if fiscal_year is not None and not 1993 <= fiscal_year <= 2100:  # REST's bounds; SMALLINT
        raise InvalidInputError("fiscalYear must be between 1993 and 2100.")
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

    @strawberry.field(description="Text chunks of indexed filings by id, in the order given.")
    async def chunks(
        self,
        info: strawberry.Info,
        ids: Annotated[list[strawberry.ID], strawberry.argument(description=IDS)],
    ) -> list[Chunk]:
        found = await _backend(info).get_chunks(_ids(ids)) if ids else []
        return [Chunk.of(source.chunk, source) for source in found]

    @strawberry.field(description="Financial facts by id, in the order given.")
    async def facts(
        self,
        info: strawberry.Info,
        ids: Annotated[list[strawberry.ID], strawberry.argument(description=IDS)],
    ) -> list[FinancialFact]:
        found = await _backend(info).get_facts(_ids(ids)) if ids else []
        return [FinancialFact.of(s.fact, s.company.cik, s.company) for s in found]

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


def _bad_value(error: GraphQLError) -> bool:
    """A value that does not fit its type, whose message would echo the value back."""
    if isinstance(error.original_error, GraphQLError):  # a variable's or an argument's coercion
        return True
    nodes = error.nodes or ()
    return any(isinstance(n, ValueNode) and not isinstance(n, VariableNode) for n in nodes)


def error_code(error: GraphQLError) -> str | None:
    """The code an error answers with; None for a query the schema refuses (no input in it)."""
    original = error.original_error
    if isinstance(original, FilingLensError):
        return original.code
    if _bad_value(error):
        return "invalid_input"
    if original is not None and not isinstance(original, GraphQLError):
        return "internal"
    return None


class ErrorCodes(MaskErrors):
    """Taxonomy errors keep their message and gain extensions.code; a bad value and any other
    error are masked."""

    def __init__(self) -> None:
        super().__init__(should_mask_error=lambda error: error_code(error) is not None)

    def anonymise_error(self, error: GraphQLError) -> GraphQLError:
        original, code = error.original_error, error_code(error)
        if isinstance(original, FilingLensError):
            message = str(original)
        else:
            message = BAD_VALUE if code == "invalid_input" else self.error_message
        return GraphQLError(
            message,
            error.nodes,
            error.source,
            error.positions,
            error.path,
            extensions={"code": code},
        )


class Schema(strawberry.Schema):
    def process_errors(
        self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None
    ) -> None:
        """Log each error's code and path, never its message, which can quote the input."""
        for error in errors:
            code = error_code(error)
            if code == "internal":  # Strawberry caught it, so this is its only traceback
                log.error(
                    "graphql_error", code=code, path=error.path, exc_info=error.original_error
                )
            else:
                log.warning("graphql_error", code=code, path=error.path)


async def _chunk_sources(backend: Backend, ids: list[str]) -> list[ChunkSource | NotFoundError]:
    found = {source.chunk.id: source for source in await backend.get_chunks(ids)}
    return [found.get(i) or NotFoundError("This chunk's filing is not indexed.") for i in ids]


async def _companies(backend: Backend, ciks: list[int]) -> list[schemas.Company | NotFoundError]:
    found = {company.cik: company for company in await backend.get_companies(ciks)}
    return [found.get(cik) or NotFoundError(f"No company with CIK {cik}.") for cik in ciks]


async def get_context(
    backend: Annotated[Backend, Depends(get_backend)],
    answer_limits: Annotated[Callable[[], Awaitable[None]], Depends(answer_limits_for)],
) -> dict[str, Any]:
    # New loaders per request: the links on one page wait for each other and share one lookup.
    return {
        "backend": backend,
        "answer_limits": answer_limits,
        "chunk_sources": DataLoader(partial(_chunk_sources, backend)),
        "companies": DataLoader(partial(_companies, backend)),
    }


# The limits are validation rules, so a query past them is refused before any resolver runs.
# Introspection is off: codegen prints the schema itself, and nothing reads it from this server.
schema = Schema(
    query=Query,
    extensions=[
        ErrorCodes,
        DisableIntrospection,
        lambda: QueryDepthLimiter(max_depth=MAX_DEPTH),
        lambda: MaxAliasesLimiter(max_alias_count=MAX_ALIASES),
    ],
)
