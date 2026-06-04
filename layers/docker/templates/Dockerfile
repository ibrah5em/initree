# syntax=docker/dockerfile:1
FROM ${runtime.base_image}

WORKDIR /app

# Dependencies install into /app/.venv; putting it on PATH makes the app entrypoint runnable.
ENV PATH="/app/.venv/bin:$PATH"

# uv drives dependency resolution; copy the static binary from its official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY . .
RUN ${runtime.install_cmd}

EXPOSE ${app.port}
CMD ${app.start_command}
