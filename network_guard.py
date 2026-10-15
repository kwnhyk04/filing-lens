"""Keeps tests off the network: looking up any host but this machine fails at once.

Recorded fixtures stand in for SEC EDGAR, the model providers and Hugging Face. The root
conftest.py installs the guard in the pytest process, and the processes that tests start install
it too. It wraps socket.getaddrinfo, which the HTTP, Redis, AMQP and Postgres clients here call
before they connect.
"""

import ipaddress
import socket
from typing import Any

_getaddrinfo = socket.getaddrinfo


class NetworkBlockedError(RuntimeError):
    """A test tried to reach another machine. Not an OSError, so no client retries it."""


def _local(host: bytes | str | None) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not host or host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified  # 0.0.0.0: the tests' dead dependency


def _guarded_getaddrinfo(
    host: bytes | str | None, port: bytes | str | int | None, *args: Any, **kwargs: Any
) -> Any:
    if not _local(host):
        raise NetworkBlockedError(f"Tests must not reach {host!r} (port {port!r}): use fixtures.")
    return _getaddrinfo(host, port, *args, **kwargs)


def install() -> None:
    socket.getaddrinfo = _guarded_getaddrinfo
