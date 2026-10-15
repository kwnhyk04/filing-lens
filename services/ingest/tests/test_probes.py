import importlib
import socket
from types import SimpleNamespace

import httpx2
import pytest


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_probes_report_liveness_and_each_unreachable_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health = free_port()
    # Nothing answers on 0.0.0.0:1, and at once: a closed 127.0.0.1 port takes 2 s on Windows.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@0.0.0.0:1/app")
    monkeypatch.setenv("REDIS_URL", "redis://0.0.0.0:1/0")
    monkeypatch.setenv("BROKER_URL", "amqp://app:app@0.0.0.0:1//")
    monkeypatch.setenv("HEALTH_PORT", str(health))
    monkeypatch.setenv("SEC_USER_AGENT", "FilingLens tests tests@filinglens.test")
    worker = importlib.import_module("filinglens_ingest.worker")
    server = worker.start_probes(sender=SimpleNamespace(hostname="celery@test"))
    base = f"http://127.0.0.1:{health}"
    try:
        assert httpx2.get(f"{base}/healthz").json() == {"status": "ok"}
        response = httpx2.get(f"{base}/readyz", timeout=30)
        assert response.status_code == 503
        checks = {"rabbitmq": False, "redis": False, "postgres": False}
        assert response.json()["checks"] == checks
    finally:
        server.shutdown()
