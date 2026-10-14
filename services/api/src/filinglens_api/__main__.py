"""Serve the API with uvicorn and JSON logs: `python -m filinglens_api`."""

import uvicorn

from filinglens_api.main import app
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_telemetry import configure_logging

settings = load_settings(ApiSettings)
keys = [settings.api_key.get_secret_value(), settings.admin_api_key.get_secret_value()]
configure_logging("api", settings.log_level, secrets=keys)
uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)
