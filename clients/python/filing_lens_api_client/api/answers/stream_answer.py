from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.answer_request import AnswerRequest
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: AnswerRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/answers/stream",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | Problem | None:
    if response.status_code == 200:
        response_200 = cast(Any, None)
        return response_200

    if response.status_code == 401:
        response_401 = Problem.from_dict(response.json())

        return response_401

    if response.status_code == 413:
        response_413 = Problem.from_dict(response.json())

        return response_413

    if response.status_code == 422:
        response_422 = Problem.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if response.status_code == 502:
        response_502 = Problem.from_dict(response.json())

        return response_502

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
    body: AnswerRequest,
) -> Response[Any | Problem]:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    Args:
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
) -> Any | Problem | None:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    Args:
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
) -> Response[Any | Problem]:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    Args:
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
) -> Any | Problem | None:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    Args:
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
