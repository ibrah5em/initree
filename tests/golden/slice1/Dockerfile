# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Dependencies install into /app/.venv; putting it on PATH makes the app entrypoint runnable.
ENV PATH="/app/.venv/bin:$PATH"

# uv drives dependency resolution; copy the static binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY . .
RUN uv sync

EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
