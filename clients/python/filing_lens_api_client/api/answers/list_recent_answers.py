from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.recent_answer_page import RecentAnswerPage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Session-ID"] = x_session_id

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
        "url": "/v1/answers/recent",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | RecentAnswerPage | None:
    if response.status_code == 200:
        response_200 = RecentAnswerPage.from_dict(response.json())

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
) -> Response[Problem | RecentAnswerPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: str,
) -> Response[Problem | RecentAnswerPage]:
    """List Recent Answers

     This sign-in's questions with their completed answers, newest first. Either key.

    At most 10 are kept, each for RECENT_ANSWERS_TTL_S; refused and degraded answers never are.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RecentAnswerPage]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: str,
) -> Problem | RecentAnswerPage | None:
    """List Recent Answers

     This sign-in's questions with their completed answers, newest first. Either key.

    At most 10 are kept, each for RECENT_ANSWERS_TTL_S; refused and degraded answers never are.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RecentAnswerPage
    """

    return sync_detailed(
        client=client,
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: str,
) -> Response[Problem | RecentAnswerPage]:
    """List Recent Answers

     This sign-in's questions with their completed answers, newest first. Either key.

    At most 10 are kept, each for RECENT_ANSWERS_TTL_S; refused and degraded answers never are.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RecentAnswerPage]
    """

    kwargs = _get_kwargs(
        limit=limit,
        cursor=cursor,
        x_session_id=x_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    cursor: None | str | Unset = UNSET,
    x_session_id: str,
) -> Problem | RecentAnswerPage | None:
    """List Recent Answers

     This sign-in's questions with their completed answers, newest first. Either key.

    At most 10 are kept, each for RECENT_ANSWERS_TTL_S; refused and degraded answers never are.

    Args:
        limit (int | Unset): Page size (at most 100). Default: 10.
        cursor (None | str | Unset): `next_cursor` from the previous page.
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RecentAnswerPage
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            cursor=cursor,
            x_session_id=x_session_id,
        )
    ).parsed
