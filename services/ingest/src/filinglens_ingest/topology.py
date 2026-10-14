"""kombu declarations of the queues in filinglens_core.queues; importing this needs no settings."""

from kombu import Exchange, Queue

from filinglens_core import queues

DEAD_LETTER_EXCHANGE = Exchange(queues.DEAD_LETTER_EXCHANGE, type="direct")
WORK_QUEUES = {
    name: Queue(name, routing_key=name, queue_arguments=arguments)
    for name, arguments in queues.QUEUE_ARGUMENTS.items()
}
DEAD_LETTER_QUEUES = {
    name: Queue(name, DEAD_LETTER_EXCHANGE, routing_key=name) for name in queues.DEAD_LETTER_QUEUES
}
