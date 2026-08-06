FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PSKA_API_HOST=0.0.0.0 \
    PSKA_API_PORT=8765 \
    PSKA_REVIEW_DB=/data/review.sqlite3 \
    PSKA_MEMORY_DB=/data/memory.sqlite3

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=

RUN if [ -n "${PIP_INDEX_URL}" ]; then python -m pip config set global.index-url "${PIP_INDEX_URL}"; fi \
    && if [ -n "${PIP_TRUSTED_HOST}" ]; then python -m pip config set global.trusted-host "${PIP_TRUSTED_HOST}"; fi \
    && pip install --no-cache-dir ".[mcp]" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin pska \
    && mkdir -p /data \
    && chown -R pska:pska /data

USER pska

VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8765/api/health', timeout=3).read()"

CMD ["pska-essential-api"]
