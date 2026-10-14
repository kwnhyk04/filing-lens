"""Replay dead letters: python -m filinglens_ingest.replay --queue fetch.dlq --limit 100.

Moves up to `limit` messages, oldest first, from a dead-letter queue back to its work queue with
the retry count reset. Each message leaves the dead-letter queue only after RabbitMQ confirmed
its copy; replay stops early when the work queue is full. Run it in the ingest container, which
has the settings: docker compose exec ingest python -m filinglens_ingest.replay --queue fetch.dlq
"""

import argparse

import structlog
from amqp.exceptions import MessageNacked
from kombu import Connection, Producer

from filinglens_core import queues
from filinglens_core.settings import IngestSettings, load_settings
from filinglens_ingest import topology
from filinglens_telemetry import configure_logging

log = structlog.get_logger(__name__)


def replay(connection: Connection, queue: str, limit: int) -> int:
    """Move up to `limit` messages from dead-letter `queue` to its work queue; returns how many."""
    target = queue.removesuffix(".dlq")
    dead = topology.DEAD_LETTER_QUEUES[queue](connection)  # the connection's default channel
    dead.declare()
    topology.WORK_QUEUES[target](connection).declare()  # a message to a missing queue would vanish
    producer = Producer(connection)
    moved = 0
    while moved < limit:
        message = dead.get(no_ack=False)
        if message is None:
            break
        # Drop RabbitMQ's x-death history and restart Celery's retry count.
        headers = {k: v for k, v in message.headers.items() if not k.startswith("x-")}
        headers["retries"] = 0
        try:
            producer.publish(
                message.body,
                exchange="",
                routing_key=target,
                headers=headers,
                content_type=message.content_type,
                content_encoding=message.content_encoding,
                correlation_id=message.properties.get("correlation_id"),
                delivery_mode=2,
            )
        except MessageNacked:  # the work queue is full: keep the message for a later replay
            message.requeue()
            log.warning("work queue full; replay stopped", queue=target)
            break
        message.ack()
        moved += 1
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Move dead letters back to their work queue.")
    parser.add_argument("--queue", required=True, choices=queues.DEAD_LETTER_QUEUES)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    settings = load_settings(IngestSettings)
    configure_logging("replay", settings.log_level)
    url = str(settings.broker_url.get_secret_value())
    with Connection(url, connect_timeout=5, transport_options={"confirm_publish": True}) as broker:
        moved = replay(broker, args.queue, args.limit)
    log.info("replayed dead letters", queue=args.queue, count=moved)


if __name__ == "__main__":
    main()
