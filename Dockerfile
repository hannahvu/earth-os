# EarthOS hourly ingest — runs as a Cloud Run Job, triggered by Cloud Scheduler.
FROM python:3.9-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Dependencies first, so code changes don't reinstall them
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY models/ models/
COPY sources/ sources/
COPY apps/ apps/
COPY metrics/ metrics/
COPY flows/ flows/

ENTRYPOINT ["/app/.venv/bin/python", "-m", "flows.ingest"]
