# One image per Python service, chosen with --build-arg PACKAGE (filinglens-api or filinglens-ingest).
FROM python:3.12.15-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY . .
ARG PACKAGE
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable --package "$PACKAGE"

FROM python:3.12.15-slim-trixie
RUN useradd --system --uid 10001 app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER app
