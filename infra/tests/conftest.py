"""Shared by the production checks: the docker CLI, waiting, and production's compose model."""

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["docker", *args],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,  # the first image build
        check=False,
    )


def _docker(*args: str) -> str:
    done = _run(*args)
    assert done.returncode == 0, f"docker {args[0]} failed: {done.stderr.strip()}"
    return done.stdout


def _wait_for(ready: Callable[[], bool], seconds: float = 30) -> bool:
    deadline = time.monotonic() + seconds
    while not ready():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.5)
    return True


@pytest.fixture(scope="session")
def run() -> Callable[..., subprocess.CompletedProcess[str]]:
    """run(*args): `docker <args>`, whatever its exit code."""
    return _run


@pytest.fixture(scope="session")
def docker() -> Callable[..., str]:
    """docker(*args): the output of `docker <args>`; the test fails when it exits non-zero."""
    return _docker


@pytest.fixture(scope="session")
def wait_for() -> Callable[..., bool]:
    """wait_for(ready, seconds=30): asks ready() every half second; False once time runs out."""
    return _wait_for


@pytest.fixture(scope="session")
def prod(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Production's compose model, merged but not interpolated, with every profile's services. The
    env file is empty, so no value of .env or .env.prod is read."""
    empty = tmp_path_factory.mktemp("compose") / "empty.env"
    empty.write_text("", encoding="utf-8")
    files = ("-f", "infra/docker-compose.yml", "-f", "infra/docker-compose.prod.yml")
    profiles = ("--profile", "ingest", "--profile", "observability", "--profile", "test")
    options = ("config", "--no-interpolate", "--format", "json")
    return json.loads(_docker("compose", "--env-file", str(empty), *files, *profiles, *options))
