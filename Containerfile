# Build stage: resolve and install dependencies with uv, then the project.
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Dependencies first: this layer only rebuilds when the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Runtime stage: slim image, non-root user (uid 1000 matches the usual
# Kubernetes securityContext).
FROM python:3.14-slim-trixie
RUN useradd --uid 1000 --create-home minirail
WORKDIR /app
COPY --from=builder --chown=minirail:minirail /app /app
USER minirail
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
ENTRYPOINT ["minirail"]
CMD ["serve", "--host", "0.0.0.0"]
