from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.filing_page import FilingPage
from ...models.form_type import FormType
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    form_type: FormType | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

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

    json_form_type: None | str | Unset
    if isinstance(form_type, Unset):
        json_form_type = UNSET
    elif isinstance(form_type, str):
        json_form_type = form_type
    else:
        json_form_type = form_type
    params["form_type"] = json_form_type

    json_fiscal_year: int | None | Unset
    if isinstance(fiscal_year, Unset):
        json_fiscal_year = UNSET
    else:
        json_fiscal_year = fiscal_year
    params["fiscal_year"] = json_fiscal_year

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/filings",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> FilingPage | Problem | None:
    if response.status_code == 200:
        response_200 = FilingPage.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

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
) -> Response[FilingPage | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    form_type: FormType | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Response[FilingPage | Problem]:
    """List Filings

     Ingested filings, newest first. Either key.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset):
        form_type (FormType | None | Unset):
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FilingPage | Problem]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        cik=cik,
        form_type=form_type,
        fiscal_year=fiscal_year,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    form_type: FormType | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> FilingPage | Problem | None:
    """List Filings

     Ingested filings, newest first. Either key.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset):
        form_type (FormType | None | Unset):
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FilingPage | Problem
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        cik=cik,
        form_type=form_type,
        fiscal_year=fiscal_year,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    form_type: FormType | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> Response[FilingPage | Problem]:
    """List Filings

     Ingested filings, newest first. Either key.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset):
        form_type (FormType | None | Unset):
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FilingPage | Problem]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        cik=cik,
        form_type=form_type,
        fiscal_year=fiscal_year,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 20,
    cursor: None | str | Unset = UNSET,
    cik: int | None | Unset = UNSET,
    form_type: FormType | None | Unset = UNSET,
    fiscal_year: int | None | Unset = UNSET,
) -> FilingPage | Problem | None:
    """List Filings

     Ingested filings, newest first. Either key.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 20.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        cik (int | None | Unset):
        form_type (FormType | None | Unset):
        fiscal_year (int | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FilingPage | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            cik=cik,
            form_type=form_type,
            fiscal_year=fiscal_year,
        )
    ).parsed
