from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.answer_request import AnswerRequest
from ...models.problem import Problem
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: AnswerRequest,
    fresh: bool | Unset = False,
    x_session_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_session_id, Unset):
        headers["X-Session-ID"] = x_session_id

    params: dict[str, Any] = {}

    params["fresh"] = fresh

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/answers/stream",
        "params": params,
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
    fresh: bool | Unset = False,
    x_session_id: None | str | Unset = UNSET,
) -> Response[Any | Problem]:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    With `X-Session-ID`, a completed answer that is not refused or degraded is kept for that
    sign-in, and the same question again (same words, ignoring case, spacing, curly quotes and
    closing punctuation, over the same companies and years) gets it back at once as one
    `completed` event with `stored_at`, without a model call. `fresh=true` answers again.

    Args:
        fresh (bool | Unset): Answer again, even when this sign-in has the answer already.
            Default: False.
        x_session_id (None | str | Unset): The web's sign-in id. Answers are kept for that sign-in
            alone, and only for RECENT_ANSWERS_TTL_S (default 30 minutes).
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        fresh=fresh,
        x_session_id=x_session_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
    fresh: bool | Unset = False,
    x_session_id: None | str | Unset = UNSET,
) -> Any | Problem | None:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    With `X-Session-ID`, a completed answer that is not refused or degraded is kept for that
    sign-in, and the same question again (same words, ignoring case, spacing, curly quotes and
    closing punctuation, over the same companies and years) gets it back at once as one
    `completed` event with `stored_at`, without a model call. `fresh=true` answers again.

    Args:
        fresh (bool | Unset): Answer again, even when this sign-in has the answer already.
            Default: False.
        x_session_id (None | str | Unset): The web's sign-in id. Answers are kept for that sign-in
            alone, and only for RECENT_ANSWERS_TTL_S (default 30 minutes).
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
        fresh=fresh,
        x_session_id=x_session_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
    fresh: bool | Unset = False,
    x_session_id: None | str | Unset = UNSET,
) -> Response[Any | Problem]:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    With `X-Session-ID`, a completed answer that is not refused or degraded is kept for that
    sign-in, and the same question again (same words, ignoring case, spacing, curly quotes and
    closing punctuation, over the same companies and years) gets it back at once as one
    `completed` event with `stored_at`, without a model call. `fresh=true` answers again.

    Args:
        fresh (bool | Unset): Answer again, even when this sign-in has the answer already.
            Default: False.
        x_session_id (None | str | Unset): The web's sign-in id. Answers are kept for that sign-in
            alone, and only for RECENT_ANSWERS_TTL_S (default 30 minutes).
        body (AnswerRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
        fresh=fresh,
        x_session_id=x_session_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: AnswerRequest,
    fresh: bool | Unset = False,
    x_session_id: None | str | Unset = UNSET,
) -> Any | Problem | None:
    """Stream Answer

     POST /v1/answers as Server-Sent Events. Either key; shares the answers limits.

    `delta` events carry the answer's text as the model writes it, then one `completed` event
    carries the whole answer after validation. The two agree unless validation rewrote the draft,
    and then the completed answer has warnings and replaces the streamed text. An error after the
    stream has started arrives as a `failed` event with a problem, and so does a stream still
    running after 30 s.

    With `X-Session-ID`, a completed answer that is not refused or degraded is kept for that
    sign-in, and the same question again (same words, ignoring case, spacing, curly quotes and
    closing punctuation, over the same companies and years) gets it back at once as one
    `completed` event with `stored_at`, without a model call. `fresh=true` answers again.

    Args:
        fresh (bool | Unset): Answer again, even when this sign-in has the answer already.
            Default: False.
        x_session_id (None | str | Unset): The web's sign-in id. Answers are kept for that sign-in
            alone, and only for RECENT_ANSWERS_TTL_S (default 30 minutes).
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
            fresh=fresh,
            x_session_id=x_session_id,
        )
    ).parsed
