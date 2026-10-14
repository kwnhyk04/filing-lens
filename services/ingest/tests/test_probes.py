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
    dead, health = free_port(), free_port()  # nothing listens on `dead`
    monkeypatch.setenv("DATABASE_URL", f"postgresql+asyncpg://app:app@127.0.0.1:{dead}/app")
    monkeypatch.setenv("REDIS_URL", f"redis://127.0.0.1:{dead}/0")
    monkeypatch.setenv("BROKER_URL", f"amqp://app:app@127.0.0.1:{dead}//")
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
