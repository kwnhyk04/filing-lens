from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    x_session_id: str,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    headers["X-Session-ID"] = x_session_id

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/v1/answers/recent",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | Problem | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    x_session_id: str,
) -> Response[Any | Problem]:
    """Clear Recent Answers

     Forget this sign-in's answers; the web does at sign-out. Either key.

    Args:
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        x_session_id=x_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    x_session_id: str,
) -> Any | Problem | None:
    """Clear Recent Answers

     Forget this sign-in's answers; the web does at sign-out. Either key.

    Args:
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return sync_detailed(
        client=client,
        x_session_id=x_session_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    x_session_id: str,
) -> Response[Any | Problem]:
    """Clear Recent Answers

     Forget this sign-in's answers; the web does at sign-out. Either key.

    Args:
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        x_session_id=x_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    x_session_id: str,
) -> Any | Problem | None:
    """Clear Recent Answers

     Forget this sign-in's answers; the web does at sign-out. Either key.

    Args:
        x_session_id (str): The web's sign-in id. Answers are kept for that sign-in alone, and
            only for RECENT_ANSWERS_TTL_S (default 30 minutes).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            x_session_id=x_session_id,
        )
    ).parsed
