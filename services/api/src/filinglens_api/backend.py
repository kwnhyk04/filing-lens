"""The routes' data seam. LiveBackend serves production; the tests swap in an in-memory fake."""

import base64
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import date
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy import Row, Select, select, tuple_
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
    AnswerDelta,
    AnswerRequest,
    Chunk,
    ChunkPage,
    Company,
    CompanyPage,
    FactPage,
    Filing,
    FilingPage,
    FinancialFact,
    FormType,
    IngestJob,
    IngestJobRequest,
    SearchPage,
    Section,
)
from filinglens_core.errors import InvalidInputError, NotImplementedYetError
from filinglens_db.models import Chunk as ChunkRow
from filinglens_db.models import Company as CompanyRow
from filinglens_db.models import Filing as FilingRow
from filinglens_db.models import FilingStatus
from filinglens_db.models import FinancialFact as FactRow
from filinglens_db.models import Section as SectionRow

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
UNUSABLE_CURSOR = "Unusable cursor; start again without one"


# Keyset cursor contents: the sort key of the last item on a page.
class CompanyKey(BaseModel):
    cik: int


class FilingKey(BaseModel):
    filed_on: date
    accession_number: str


class FailureKey(BaseModel):
    accession_number: str


class ItemKey(BaseModel):
    """Chunks and facts page by id."""

    id: str


class SearchKey(BaseModel):
    """Hits rank by (score desc, chunk_id); index_version pins the page to one embedding index."""

    score: float
    chunk_id: str
    index_version: str


def encode_cursor(key: BaseModel) -> str:
    """Opaque cursor: unpadded URL-safe base64 of the key's JSON."""
    return base64.urlsafe_b64encode(key.model_dump_json().encode()).decode().rstrip("=")


def decode_cursor[K: BaseModel](cursor: str, key: type[K]) -> K:
    try:
        return key.model_validate_json(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except ValueError:  # bad base64, bad JSON and ValidationError are all ValueErrors
        raise InvalidInputError(UNUSABLE_CURSOR) from None


def _page[T](
    items: list[T], limit: int, key: Callable[[T], BaseModel]
) -> tuple[list[T], str | None]:
    """Cut a query's limit + 1 items to a page; the extra one only says another page exists."""
    if len(items) <= limit:
        return items, None
    return items[:limit], encode_cursor(key(items[limit - 1]))


def _row_id(value: str) -> int | None:
    """A bigint id from client input, or None when the input cannot be one."""
    return int(value) if value.isascii() and value.isdigit() and len(value) < 19 else None


def _filing(row: Row[*tuple[Any, ...]]) -> Filing:
    folder = row.accession_number.replace("-", "")
    return Filing(
        accession_number=row.accession_number,
        cik=row.cik,
        form_type=row.form_type,
        filed_on=row.filed_on,
        period_end=row.period_end,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        url=f"{SEC_ARCHIVES}/{row.cik}/{folder}/{row.primary_document}",
    )


class Backend(Protocol):
    async def create_ingest_job(self, request: IngestJobRequest, idempotency_key: str) -> UUID:
        """Same key and body: the existing job. Same key, other body: IdempotencyKeyReusedError."""
        ...

    async def get_ingest_job(self, job_id: UUID, limit: int, cursor: str | None) -> IngestJob:
        """Raises NotFoundError for an unknown job; limit and cursor page its failures."""
        ...

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage: ...

    async def list_filings(
        self,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
    ) -> FilingPage: ...

    async def list_sections(self, accession_number: str) -> list[Section]: ...

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage: ...

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage: ...

    async def search(self, q: str, limit: int, cursor: str | None) -> SearchPage: ...

    async def answer(self, request: AnswerRequest) -> Answer: ...

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        """Admit the request first, so errors here still get a status code; then return events."""
        ...


def get_backend(request: Request) -> Backend:
    return request.app.state.backend


BackendDep = Annotated[Backend, Depends(get_backend)]


class LiveBackend:
    """Production backend: catalog reads come from Postgres; the rest is 501 until its step."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _rows[*Ts](self, query: Select[*Ts]) -> Sequence[Row[*Ts]]:
        async with self._engine.connect() as connection:
            return (await connection.execute(query)).all()

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage:
        query = select(CompanyRow.cik, CompanyRow.ticker, CompanyRow.name)
        if cursor is not None:
            query = query.where(CompanyRow.cik > decode_cursor(cursor, CompanyKey).cik)
        rows = await self._rows(query.order_by(CompanyRow.cik).limit(limit + 1))
        companies = [Company(cik=row.cik, ticker=row.ticker, name=row.name) for row in rows]
        items, next_cursor = _page(companies, limit, lambda c: CompanyKey(cik=c.cik))
        return CompanyPage(items=items, next_cursor=next_cursor)

    async def create_ingest_job(self, request: IngestJobRequest, idempotency_key: str) -> UUID:
        raise NotImplementedYetError("Ingest jobs are not available yet.")

    async def get_ingest_job(self, job_id: UUID, limit: int, cursor: str | None) -> IngestJob:
        raise NotImplementedYetError("Ingest jobs are not available yet.")

    async def list_filings(
        self,
        limit: int,
        cursor: str | None,
        *,
        cik: int | None = None,
        form_type: FormType | None = None,
        fiscal_year: int | None = None,
    ) -> FilingPage:
        query = select(
            FilingRow.accession_number,
            FilingRow.cik,
            FilingRow.form_type,
            FilingRow.filed_on,
            FilingRow.period_end,
            FilingRow.fiscal_year,
            FilingRow.fiscal_period,
            FilingRow.primary_document,
        ).where(FilingRow.status == FilingStatus.INDEXED)
        if cik is not None:
            query = query.where(FilingRow.cik == cik)
        if form_type is not None:
            query = query.where(FilingRow.form_type == form_type.value)
        if fiscal_year is not None:
            query = query.where(FilingRow.fiscal_year == fiscal_year)
        if cursor is not None:
            last = decode_cursor(cursor, FilingKey)
            position = tuple_(FilingRow.filed_on, FilingRow.accession_number)
            query = query.where(position < (last.filed_on, last.accession_number))
        newest_first = (FilingRow.filed_on.desc(), FilingRow.accession_number.desc())
        rows = await self._rows(query.order_by(*newest_first).limit(limit + 1))
        items, next_cursor = _page(
            [_filing(row) for row in rows],
            limit,
            lambda f: FilingKey(filed_on=f.filed_on, accession_number=f.accession_number),
        )
        return FilingPage(items=items, next_cursor=next_cursor)

    async def list_sections(self, accession_number: str) -> list[Section]:
        query = (
            select(SectionRow.id, SectionRow.item, SectionRow.title)
            .join(FilingRow, FilingRow.id == SectionRow.filing_id)
            .where(FilingRow.accession_number == accession_number)
            .order_by(SectionRow.char_start)
        )
        rows = await self._rows(query)
        return [Section(id=str(row.id), item=row.item, title=row.title) for row in rows]

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage:
        query = (
            select(ChunkRow.id, ChunkRow.section_id, ChunkRow.text)
            .join(SectionRow, SectionRow.id == ChunkRow.section_id)
            .join(FilingRow, FilingRow.id == SectionRow.filing_id)
            .where(FilingRow.accession_number == accession_number)
        )
        if section_id is not None:  # an id that cannot exist matches nothing
            query = query.where(ChunkRow.section_id == _row_id(section_id))
        if cursor is not None:
            # The cursor holds only the chunk id, so look up where that chunk sits in the text.
            last = decode_cursor(cursor, ItemKey).id
            found = await self._rows(select(ChunkRow.char_start).where(ChunkRow.id == last))
            if not found:
                raise InvalidInputError(UNUSABLE_CURSOR)
            position = tuple_(ChunkRow.char_start, ChunkRow.id)
            query = query.where(position > (found[0].char_start, last))
        rows = await self._rows(query.order_by(ChunkRow.char_start, ChunkRow.id).limit(limit + 1))
        chunks = [Chunk(id=row.id, section_id=str(row.section_id), text=row.text) for row in rows]
        items, next_cursor = _page(chunks, limit, lambda c: ItemKey(id=c.id))
        return ChunkPage(items=items, next_cursor=next_cursor)

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage:
        query = select(
            FactRow.id,
            FactRow.taxonomy,
            FactRow.concept,
            FactRow.label,
            FactRow.value,
            FactRow.unit,
            FactRow.period_start,
            FactRow.period_end,
            FactRow.fiscal_year,
            FactRow.fiscal_period,
        ).where(FactRow.accession_number == accession_number)
        if concept is not None:
            taxonomy, _, name = concept.partition(":")  # the API names concepts us-gaap:Revenues
            query = query.where(FactRow.taxonomy == taxonomy, FactRow.concept == name)
        if cursor is not None:
            last = _row_id(decode_cursor(cursor, ItemKey).id)
            if last is None:
                raise InvalidInputError(UNUSABLE_CURSOR)
            query = query.where(FactRow.id > last)
        rows = await self._rows(query.order_by(FactRow.id).limit(limit + 1))
        facts = [
            FinancialFact(
                id=str(row.id),
                concept=f"{row.taxonomy}:{row.concept}",
                label=row.label,
                value=float(row.value),
                unit=row.unit,
                period_start=row.period_start,
                period_end=row.period_end,
                fiscal_year=row.fiscal_year,
                fiscal_period=row.fiscal_period,
                accession_number=accession_number,
            )
            for row in rows
        ]
        items, next_cursor = _page(facts, limit, lambda f: ItemKey(id=f.id))
        return FactPage(items=items, next_cursor=next_cursor)

    async def search(self, q: str, limit: int, cursor: str | None) -> SearchPage:
        raise NotImplementedYetError("Search is not available yet.")

    async def answer(self, request: AnswerRequest) -> Answer:
        raise NotImplementedYetError("Answers are not available yet.")

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        raise NotImplementedYetError("Answers are not available yet.")
