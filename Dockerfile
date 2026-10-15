FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY main.py validate.py ./
COPY scripts ./scripts
COPY mappings.json ./
COPY garde-manger.txt courses-hebdo.txt ./
COPY examples ./examples

RUN uv sync --frozen --no-dev

RUN mkdir -p data exports docs

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    COMIDA_UI_HOST=0.0.0.0 \
    COMIDA_NO_BROWSER=1 \
    COMIDA_PORT=8765 \
    HOME=/app/data

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/session')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
