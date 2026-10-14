from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.ingest_job import IngestJob
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/ingest-jobs/{job_id}".format(
            job_id=quote(str(job_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> IngestJob | Problem | None:
    if response.status_code == 200:
        response_200 = IngestJob.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = Problem.from_dict(response.json())

        return response_403

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[IngestJob | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
) -> Response[IngestJob | Problem]:
    """Get Ingest Job

     Per-filing status counts and a page of failures (limit and cursor page the failures).

    Admin route: ADMIN_API_KEY only.

    Args:
        job_id (UUID):
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestJob | Problem]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
) -> IngestJob | Problem | None:
    """Get Ingest Job

     Per-filing status counts and a page of failures (limit and cursor page the failures).

    Admin route: ADMIN_API_KEY only.

    Args:
        job_id (UUID):
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestJob | Problem
    """

    return sync_detailed(
        job_id=job_id,
        client=client,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
) -> Response[IngestJob | Problem]:
    """Get Ingest Job

     Per-filing status counts and a page of failures (limit and cursor page the failures).

    Admin route: ADMIN_API_KEY only.

    Args:
        job_id (UUID):
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[IngestJob | Problem]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
) -> IngestJob | Problem | None:
    """Get Ingest Job

     Per-filing status counts and a page of failures (limit and cursor page the failures).

    Admin route: ADMIN_API_KEY only.

    Args:
        job_id (UUID):
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        IngestJob | Problem
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            client=client,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
