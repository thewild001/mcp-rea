#
# Servidor MCP para REA (Reverse Engineer Anything) sobre FastMCP, con análisis
# de binarios nativos incluido: Ghidra + JDK 21 dentro de la imagen.
#
# REA no instala Ghidra ni Java por su cuenta ("bring your own"), así que se
# empaquetan aquí con versiones fijadas. REA acepta la línea Ghidra 12.1.x
# (verificada con 12.1.4) y exige un JDK 64 bits completo (con javac) >= 21.
#
#   stdio:  docker run -i --rm --init -v /ruta:/targets:ro rea-mcp
#   http:   docker compose up -d      (ver docker-compose.yml)
#
# IMPORTANTE (Apple Silicon / ARM): la release oficial de Ghidra solo trae
# decompilador nativo para linux_x86_64. En ARM, construya con
#   docker build --platform linux/amd64 -t rea-mcp .

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13
ARG REA_VERSION=6.4.0
ARG JDK_TAG=21-jdk
ARG GHIDRA_VERSION=12.1.4
ARG GHIDRA_DATE=20260921
# SHA-256 del zip oficial de la release (GitHub, NationalSecurityAgency/ghidra).
ARG GHIDRA_SHA256=ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db

# ── Etapa 1: REA (npm) ─────────────────────────────────────────────────────
FROM node:${NODE_VERSION}-bookworm-slim AS rea
ARG REA_VERSION
# rea-agents exige Node >= 22.19; la etiqueta node:22 apunta a la última 22.x.
RUN npm install -g --omit=dev "rea-agents@${REA_VERSION}" \
 && npm cache clean --force

# ── Etapa 2: JDK 21 completo (Temurin) ─────────────────────────────────────
# Solo se copia el directorio del JDK; el sistema operativo de esta etapa no
# llega a la imagen final (Temurin es un tarball relocatable).
FROM eclipse-temurin:${JDK_TAG} AS jdk

# ── Etapa 3: Ghidra (descarga verificada) ──────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS ghidra
ARG GHIDRA_VERSION
ARG GHIDRA_DATE
ARG GHIDRA_SHA256
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/ghidra
RUN set -eux; \
    zip="ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_DATE}.zip"; \
    curl -fsSL --proto '=https' --tlsv1.2 --retry 5 --retry-delay 3 \
      -o ghidra.zip \
      "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/${zip}"; \
    echo "${GHIDRA_SHA256}  ghidra.zip" | sha256sum -c -; \
    unzip -q ghidra.zip -d /opt; \
    mv "/opt/ghidra_${GHIDRA_VERSION}_PUBLIC" /opt/ghidra; \
    rm -rf /opt/ghidra/docs; \
    chmod -R a+rX /opt/ghidra; \
    test -x /opt/ghidra/support/analyzeHeadless; \
    test -x /opt/ghidra/Ghidra/Features/Decompiler/os/linux_x86_64/decompile

# ── Etapa 4: dependencias Python ───────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS pydeps
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Etapa 5: runtime ───────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# Misma base Debian (bookworm) en todas las etapas => misma glibc para los
# binarios nativos de rea-agents y de Ghidra.
#
# libfreetype6 + fontconfig: la JVM los carga si algo toca java.awt (incluso en
# modo headless). Son ~5 MB y evitan un UnsatisfiedLinkError difícil de rastrear.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fontconfig libfreetype6 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=rea /usr/local/bin/node /usr/local/bin/node
COPY --from=rea /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=rea /usr/local/bin/rea-agents /usr/local/bin/rea-agents
COPY --from=jdk /opt/java/openjdk /opt/java/openjdk
COPY --from=ghidra /opt/ghidra /opt/ghidra
COPY --from=pydeps /install /usr/local

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin rea

WORKDIR /app
COPY src ./src
COPY scripts ./scripts

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JAVA_HOME=/opt/java/openjdk \
    GHIDRA_INSTALL_DIR=/opt/ghidra \
    PATH="/opt/java/openjdk/bin:${PATH}" \
    REA_COMMAND=rea-agents \
    REA_ARGS=mcp \
    MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Fallo rápido en build si el binario de REA no quedó utilizable.
RUN rea-agents --help >/dev/null

USER rea

# Prueba de humo real: abre un ELF con Ghidra a través de este servidor y lista
# sus procedimientos. Si Ghidra, el JDK o REA no encajan, el build falla aquí y
# no en la primera consulta del agente. Tarda ~30 s.
#   --build-arg SKIP_SMOKE=1   la omite (p. ej. bajo emulación lenta)
# En ARM no hay decompilador nativo de Ghidra: se avisa y se continúa.
ARG SKIP_SMOKE=0
RUN if [ "${SKIP_SMOKE}" = "1" ]; then \
      echo "AVISO: prueba de humo omitida (SKIP_SMOKE=1)." >&2; \
    elif [ "$(uname -m)" != "x86_64" ]; then \
      echo "AVISO: Ghidra no trae decompilador nativo para $(uname -m); el analisis de binarios no funcionara en esta imagen. Construya con --platform linux/amd64." >&2; \
    else \
      python scripts/smoke_native.py; \
    fi

# Sin HEALTHCHECK aquí: en modo stdio no hay puerto que sondear. El de HTTP
# vive en docker-compose.yml, donde sí se sabe que el transporte es HTTP.
EXPOSE 8000
ENTRYPOINT ["python", "-m", "src.server"]
