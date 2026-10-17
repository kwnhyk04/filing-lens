# One image per Python service, chosen with --build-arg PACKAGE (filinglens-api or filinglens-ingest).
# Base images are pinned by digest; Dependabot proposes updates.
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY . .
ARG PACKAGE
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable --package "$PACKAGE"

FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ARG PACKAGE
# The SEC cache directory belongs to the app user, so a new named volume mounted there does too.
RUN useradd --system --uid 10001 app && install -d -o app /var/cache/filinglens/sec
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 FILINGLENS_PACKAGE=$PACKAGE
USER app
# Liveness for a plain docker run (compose adds readiness checks): the api serves /healthz on
# API_PORT, a worker's probe on HEALTH_PORT.
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=6 CMD ["python", "-c", "import os, urllib.request as u; api = os.environ['FILINGLENS_PACKAGE'] == 'filinglens-api'; port = os.environ.get('API_PORT', '4100') if api else os.environ.get('HEALTH_PORT', '8001'); u.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=8)"]
