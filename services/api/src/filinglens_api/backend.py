"""The routes' data seam. LiveBackend serves production; the tests swap in an in-memory fake."""

import base64
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from filinglens_api.schemas import (
    Answer,
    AnswerCompleted,
    AnswerDelta,
    AnswerRequest,
    ChunkPage,
    Company,
    CompanyPage,
    FactPage,
    FilingPage,
    FormType,
    IngestJob,
    IngestJobRequest,
    SearchPage,
    Section,
)
from filinglens_core.errors import InvalidInputError, NotImplementedYetError
from filinglens_db.models import Company as CompanyRow


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
        raise InvalidInputError("Unusable cursor; start again without one") from None


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
    """Production backend: companies come from Postgres; the rest is 501 until its build step."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def list_companies(self, limit: int, cursor: str | None) -> CompanyPage:
        query = select(CompanyRow.cik, CompanyRow.ticker, CompanyRow.name)
        if cursor is not None:
            query = query.where(CompanyRow.cik > decode_cursor(cursor, CompanyKey).cik)
        async with self._engine.connect() as connection:
            rows = (await connection.execute(query.order_by(CompanyRow.cik).limit(limit + 1))).all()
        items = [Company(cik=row.cik, ticker=row.ticker, name=row.name) for row in rows[:limit]]
        more = len(rows) > limit  # the extra row only says whether another page exists
        next_cursor = encode_cursor(CompanyKey(cik=items[-1].cik)) if more else None
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
        raise NotImplementedYetError("Filings are not available yet.")

    async def list_sections(self, accession_number: str) -> list[Section]:
        raise NotImplementedYetError("Filing sections are not available yet.")

    async def list_chunks(
        self,
        accession_number: str,
        limit: int,
        cursor: str | None,
        *,
        section_id: str | None = None,
    ) -> ChunkPage:
        raise NotImplementedYetError("Filing chunks are not available yet.")

    async def list_facts(
        self, accession_number: str, limit: int, cursor: str | None, *, concept: str | None = None
    ) -> FactPage:
        raise NotImplementedYetError("Financial facts are not available yet.")

    async def search(self, q: str, limit: int, cursor: str | None) -> SearchPage:
        raise NotImplementedYetError("Search is not available yet.")

    async def answer(self, request: AnswerRequest) -> Answer:
        raise NotImplementedYetError("Answers are not available yet.")

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerCompleted]:
        raise NotImplementedYetError("Answers are not available yet.")
