"""Serve the API with uvicorn, JSON logs and telemetry (when OTEL_EXPORTER_OTLP_ENDPOINT is set):
`python -m filinglens_api`."""

from functools import partial

import uvicorn
from redis import Redis

from filinglens_api.main import app
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_llm import budget
from filinglens_telemetry import configure_logging, metrics
from filinglens_telemetry.otel import configure_telemetry

settings = load_settings(ApiSettings)
keys = [settings.api_key.get_secret_value(), settings.admin_api_key.get_secret_value()]
configure_logging("api", settings.log_level, secrets=keys)
endpoint = settings.otel_exporter_otlp_endpoint
configure_telemetry(settings.otel_service_name, str(endpoint) if endpoint else None)
# Once per process, not in lifespan: a gauge registered twice keeps its first callback.
redis = Redis.from_url(
    str(settings.redis_url.get_secret_value()), socket_timeout=2, socket_connect_timeout=2
)
metrics.observe_answer_limits(
    partial(budget.tokens_today, redis), settings.daily_ai_token_budget, settings.llm_max_inflight
)
metrics.observe_claude(partial(budget.claude_off_kind, redis))  # ClaudeKeyOrModelRejected
roles = (settings.llm_router, settings.llm_primary, settings.llm_fallback)
metrics.start_answer_series({*roles, *filter(None, [settings.llm_answer_fallback])})
uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)
