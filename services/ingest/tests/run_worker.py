"""Ingest worker for the integration tests: python run_worker.py NAME QUEUES.

The production worker, with shorter waits: retries skip their 1 to 32 s backoff, an SEC cool-off
lasts 1 s instead of 60, and a task without Redis pauses 0.3 s instead of 30. The solo pool runs
one task at a time (and works on Windows).
"""

import sys

import celery.app.autoretry

import filinglens_sec_client
from filinglens_ingest import pipeline

celery.app.autoretry.get_exponential_backoff_interval = lambda **_: 0  # pyright: ignore[reportAttributeAccessIssue]
filinglens_sec_client.COOL_OFF_S = 1
pipeline.LIMITER_PAUSE_S = 0.3

from filinglens_ingest.worker import app  # noqa: E402 - the patches must come first

name, queues = sys.argv[1:3]
app.worker_main(
    [
        "worker",
        "--pool=solo",
        "--without-gossip",
        "--without-mingle",
        "--without-heartbeat",
        "--loglevel=INFO",
        f"--hostname={name}@%h",
        f"--queues={queues}",
    ]
)
