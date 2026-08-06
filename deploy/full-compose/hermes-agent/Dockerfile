ARG HERMES_AGENT_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_AGENT_IMAGE}

USER root
WORKDIR /opt/pska-essential

COPY pyproject.toml README.md ./
COPY src ./src

ARG UV_DEFAULT_INDEX=

RUN if [ -n "${UV_DEFAULT_INDEX}" ]; then export UV_DEFAULT_INDEX; fi \
    && uv pip install --python /opt/hermes/.venv/bin/python --no-cache ".[mcp]"
