FROM node:24.22.2-bookworm-slim AS web
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY frontend ./frontend
COPY tsconfig.node.json playwright*.ts vitest.config.* ./
RUN npx vite build --config frontend/vite.config.ts

FROM python:3.13.18-slim-bookworm AS python
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM postgres:17.11-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tini ca-certificates netbase tzdata libbz2-1.0 libdb5.3 libffi8 libgdbm6 libgdbm-compat4 liblzma5 libncursesw6 libreadline8 libsqlite3-0 libssl3 libtinfo6 libuuid1 zlib1g libexpat1 && rm -rf /var/lib/apt/lists/*
COPY --from=python /usr/local /usr/local
RUN ldconfig
WORKDIR /app
COPY --from=python /app/.venv ./.venv
COPY backend ./backend
COPY alembic.ini ./
COPY scripts/container.py ./scripts/container.py
COPY --from=web /app/dist ./dist
ENV PATH="/app/.venv/bin:$PATH" PORT=10000
RUN python -c 'import ssl,bz2,ctypes,lzma,sqlite3,readline,uuid,psycopg,pydantic_core'
USER postgres
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "scripts/container.py"]
