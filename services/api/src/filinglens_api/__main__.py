"""Serve the API with uvicorn and JSON logs: `python -m filinglens_api`."""

import uvicorn

from filinglens_api.main import app
from filinglens_core.settings import ApiSettings, load_settings
from filinglens_telemetry import configure_logging

settings = load_settings(ApiSettings)
configure_logging("api", settings.log_level, secrets=[settings.api_key.get_secret_value()])
uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_config=None)
