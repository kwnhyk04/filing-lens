from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.search_page import SearchPage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["q"] = q

    params["limit"] = limit

    json_cursor: None | str | Unset
    if isinstance(cursor, Unset):
        json_cursor = UNSET
    else:
        json_cursor = cursor
    params["cursor"] = json_cursor

    json_cik: int | None | Unset
    if isinstance(cik, Unset):
        json_cik = UNSET
    else:
        json_cik = cik
    params["cik"] = json_cik

    json_fiscal_year: int | None | Unset
    if isinstance(fiscal_year, Unset):
        json_fiscal_year = UNSET
    else:
        json_fiscal_year = fiscal_year
    params["fiscal_year"] = json_fiscal_year

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/search",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Problem | SearchPage | None:
    if response.status_code == 200:
        response_200 = SearchPage.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

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
) -> Response[Problem | SearchPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Response[Problem | SearchPage]:
    """Search

     Hybrid search over the text of indexed filings. Either key.

    Vector and full-text matches are fused and reranked. The cursor holds the last hit's score
    and chunk id and the index version, so later pages come from the same index; once the index
    changes (a new embedding model), a cursor gets 409 and the search starts again without one.

    Args:
        q (str): Search text.
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset): One company.
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchPage]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
        cursor=cursor,
        cik=cik,
        fiscal_year=fiscal_year,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Problem | SearchPage | None:
    """Search

     Hybrid search over the text of indexed filings. Either key.

    Vector and full-text matches are fused and reranked. The cursor holds the last hit's score
    and chunk id and the index version, so later pages come from the same index; once the index
    changes (a new embedding model), a cursor gets 409 and the search starts again without one.

    Args:
        q (str): Search text.
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset): One company.
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchPage
    """

    return sync_detailed(
        client=client,
        q=q,
        limit=limit,
        cursor=cursor,
        cik=cik,
        fiscal_year=fiscal_year,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Response[Problem | SearchPage]:
    """Search

     Hybrid search over the text of indexed filings. Either key.

    Vector and full-text matches are fused and reranked. The cursor holds the last hit's score
    and chunk id and the index version, so later pages come from the same index; once the index
    changes (a new embedding model), a cursor gets 409 and the search starts again without one.

    Args:
        q (str): Search text.
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset): One company.
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchPage]
    """

    kwargs = _get_kwargs(
        q=q,
        limit=limit,
        cursor=cursor,
        cik=cik,
        fiscal_year=fiscal_year,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    q: str,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Problem | SearchPage | None:
    """Search

     Hybrid search over the text of indexed filings. Either key.

    Vector and full-text matches are fused and reranked. The cursor holds the last hit's score
    and chunk id and the index version, so later pages come from the same index; once the index
    changes (a new embedding model), a cursor gets 409 and the search starts again without one.

    Args:
        q (str): Search text.
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset): One company.
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchPage
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            limit=limit,
            cursor=cursor,
            cik=cik,
            fiscal_year=fiscal_year,
        )
    ).parsed
