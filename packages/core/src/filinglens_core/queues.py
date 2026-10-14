"""RabbitMQ queues of the ingest pipeline, shared by the API (it queues discover) and the worker.

RabbitMQ refuses to redeclare a queue with different arguments, so every process builds its kombu
queues from these definitions.
"""

DISCOVER_TASK = "filinglens_ingest.pipeline.discover"
FETCH_TASK = "filinglens_ingest.pipeline.fetch"

DISCOVER = "discover"
FETCH = "fetch"
FETCH_RETRY = "fetch.retry"  # unbounded, so a full fetch queue cannot refuse a retry
REEMBED = "reembed"
DEAD_LETTER_EXCHANGE = "filinglens.dlx"
FETCH_MAX_LENGTH = 10_000


def _dead_letters_to(queue: str) -> dict[str, str | int]:
    """A message rejected without requeue moves to `queue` through the dead-letter exchange."""
    return {"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE, "x-dead-letter-routing-key": queue}


# Work queues and their arguments. Each dead-letter queue is bound to the exchange by its name.
QUEUE_ARGUMENTS: dict[str, dict[str, str | int]] = {
    DISCOVER: _dead_letters_to("discover.dlq"),
    # Backpressure: past the limit RabbitMQ nacks the publish, and discover backs off.
    FETCH: _dead_letters_to("fetch.dlq")
    | {"x-max-length": FETCH_MAX_LENGTH, "x-overflow": "reject-publish"},
    FETCH_RETRY: _dead_letters_to("fetch.dlq"),
    REEMBED: {},
}
DEAD_LETTER_QUEUES = ("discover.dlq", "fetch.dlq")
