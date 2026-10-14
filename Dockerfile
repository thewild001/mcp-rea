# syntax=docker/dockerfile:1
# Multi-stage build for rea-mcp.
# Uses the official REA installation: npx -y rea-agents@6.4.0 mcp
# No pip needed - npx downloads from npm automatically

# ── Stage 1: Setup with npx (REA agent MCP server) ─────────────────────
FROM node:22-bookworm AS builder

# Pass proxy args
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

WORKDIR /app

# Install rea-agents globally so npx can find it
# This mirrors: npm install -g rea-agents@6.4.0
RUN npm install -g rea-agents@6.4.0

# ── Stage 2: Runtime ────────────────────────────────────────────────────
FROM node:22-slim-bookworm AS runtime

# Pass proxy args to runtime
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

WORKDIR /app

# Copy globally installed rea-agents from builder
COPY --from=builder /usr/local/lib/node_modules/rea-agents /usr/local/lib/node_modules/rea-agents

# Make binaries available
ENV PATH="/usr/local/lib/node_modules/rea-agents/node_modules/.bin:$PATH \
    NODE_OPTIONS="--enable-source-maps" \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

# Health check: verify npx rea-agents mcp responds to initialize
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | npx -y rea-agents@6.4.0 mcp 2>/dev/null | grep -q 'jsonrpc' || exit 1

# Default: run MCP stdio server via npx rea-agents
ENTRYPOINT ["npx", "-y", "rea-agents@6.4.0", "mcp"]
