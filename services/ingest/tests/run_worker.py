"""Ingest worker for the integration tests: python run_worker.py NAME QUEUES.

The production worker, except that retries skip their 1 to 32 s backoff, so a filing uses up its
retries in about a second. The solo pool runs one task at a time (and works on Windows).
"""

import sys

import celery.app.autoretry

celery.app.autoretry.get_exponential_backoff_interval = lambda **_: 0  # pyright: ignore[reportAttributeAccessIssue]

from filinglens_ingest.worker import app  # noqa: E402 - the patch must come first

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
