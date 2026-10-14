# syntax=docker/dockerfile:1
#
# Servidor MCP para REA (Reverse Engineer Anything) sobre FastMCP.
#
# Necesita dos runtimes: Python (FastMCP) y Node (rea-agents). REA se instala
# UNA vez en build y se ejecuta con su binario, sin `npx` en tiempo de
# ejecución: así el arranque no depende de la red ni del registro npm.
#
#   stdio:  docker run -i --rm rea-mcp
#   http:   docker compose up -d      (ver docker-compose.yml)

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13
ARG REA_VERSION=6.4.0

# ── Etapa 1: REA (npm) ─────────────────────────────────────────────────────
FROM node:${NODE_VERSION}-bookworm-slim AS rea
ARG REA_VERSION
# rea-agents exige Node >= 22.19; la etiqueta node:22 apunta a la última 22.x.
RUN npm install -g --omit=dev "rea-agents@${REA_VERSION}" \
 && npm cache clean --force

# ── Etapa 2: dependencias Python ───────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS pydeps
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Etapa 3: runtime ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# Misma base Debian (bookworm) en ambas etapas => misma glibc para los
# binarios nativos que trae rea-agents.
COPY --from=rea /usr/local/bin/node /usr/local/bin/node
COPY --from=rea /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=rea /usr/local/bin/rea-agents /usr/local/bin/rea-agents
COPY --from=pydeps /install /usr/local

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin rea

WORKDIR /app
COPY src ./src

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    REA_COMMAND=rea-agents \
    REA_ARGS=mcp \
    MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Fallo rápido en build si el binario de REA no quedó utilizable.
RUN rea-agents --help >/dev/null

USER rea

# Sin HEALTHCHECK aquí: en modo stdio no hay puerto que sondear. El de HTTP
# vive en docker-compose.yml, donde sí se sabe que el transporte es HTTP.
EXPOSE 8000
ENTRYPOINT ["python", "-m", "src.server"]
