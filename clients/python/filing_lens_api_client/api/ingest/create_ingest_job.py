from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ingest_job_accepted import IngestJobAccepted
from ...models.ingest_job_request import IngestJobRequest
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: IngestJobRequest,
    idempotency_key: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["Idempotency-Key"] = idempotency_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/ingest-jobs",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> IngestJobAccepted | Problem | None:
    if response.status_code == 202:
        response_202 = IngestJobAccepted.from_dict(response.json())

        return response_202

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 413:
        response_413 = Problem.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if response.status_code == 503:
        response_503 = Problem.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[IngestJobAccepted | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: IngestJobRequest,
    idempotency_key: str,
) -> Response[IngestJobAccepted | Problem]:
    """Create Ingest Job

     Queue ingestion of the companies' filings. Admin route: ADMIN_API_KEY only.

    Args:
        idempotency_key (str): Unique per job. A retry with the same key and body gets the same
            job.
        body (IngestJobRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestJobAccepted | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        idempotency_key=idempotency_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: IngestJobRequest,
    idempotency_key: str,
) -> IngestJobAccepted | Problem | None:
    """Create Ingest Job

     Queue ingestion of the companies' filings. Admin route: ADMIN_API_KEY only.

    Args:
        idempotency_key (str): Unique per job. A retry with the same key and body gets the same
            job.
        body (IngestJobRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestJobAccepted | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
        idempotency_key=idempotency_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: IngestJobRequest,
    idempotency_key: str,
) -> Response[IngestJobAccepted | Problem]:
    """Create Ingest Job

     Queue ingestion of the companies' filings. Admin route: ADMIN_API_KEY only.

    Args:
        idempotency_key (str): Unique per job. A retry with the same key and body gets the same
            job.
        body (IngestJobRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestJobAccepted | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        idempotency_key=idempotency_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: IngestJobRequest,
    idempotency_key: str,
) -> IngestJobAccepted | Problem | None:
    """Create Ingest Job

     Queue ingestion of the companies' filings. Admin route: ADMIN_API_KEY only.

    Args:
        idempotency_key (str): Unique per job. A retry with the same key and body gets the same
            job.
        body (IngestJobRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestJobAccepted | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            idempotency_key=idempotency_key,
        )
    ).parsed
