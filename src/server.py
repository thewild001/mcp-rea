"""REA MCP Server, construido sobre FastMCP.

REA = "Reverse Engineer Anything" (paquete npm `rea-agents`). Este servidor
envuelve el MCP oficial de REA, que habla stdio con protocolo 2024-11-05, y lo
reexpone mediante FastMCP. Aporta lo que el MCP original no tiene:

* transporte HTTP (streamable) con token Bearer, además de stdio;
* un `health_check` que comprueba de verdad el backend;
* una ruta HTTP `/health` de liveness para Docker/orquestadores;
* configuración por entorno y un arranque que falla pronto con mensajes claros.

Las tools y prompts de REA se montan sin prefijo, así que un cliente ve el
mismo catálogo que si hablara directamente con `npx rea-agents mcp`.

Uso:
    python -m src.server                       # stdio (por defecto)
    python -m src.server --transport http      # HTTP en 127.0.0.1:8000/mcp
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
import time
from typing import Any, Optional, Sequence

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport
from fastmcp.server import create_proxy
from fastmcp.server.auth import StaticTokenVerifier
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import VALID_TRANSPORTS, ConfigError, Settings

SERVER_NAME = "rea-mcp"
SERVER_VERSION = "2.0.0"

INSTRUCTIONS = (
    "Servidor MCP que expone REA (Reverse Engineer Anything): herramientas para "
    "analizar binarios nativos, aplicaciones JavaScript/Electron, ensamblados .NET "
    "y páginas web. Use la herramienta que responda directamente a la pregunta; "
    "los resultados incluyen la evidencia y sus límites. `health_check` informa "
    "del estado del servidor y de la conexión con el backend REA."
)

logger = logging.getLogger("rea-mcp")

# Variables que no deben heredar los procesos hijo.
_SECRET_ENV = frozenset({"MCP_AUTH_TOKEN"})


# ── Backend REA ────────────────────────────────────────────────────────────

def _child_env() -> dict[str, str]:
    """Entorno para el proceso REA: el del servidor, sin secretos propios.

    El SDK de MCP, por defecto, solo hereda un puñado de variables (HOME, PATH,
    ...). REA necesita su configuración de proveedores nativos, así que se
    pasa el entorno completo salvo el token del propio servidor.
    """
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV}


def build_backend_client(settings: Settings, backend: Any = None) -> Client:
    """Cliente hacia el backend REA.

    `backend` permite inyectar otro destino (p. ej. un FastMCP en memoria en
    los tests). Por defecto lanza REA como proceso hijo por stdio.

    * `mode="legacy"`: REA habla 2024-11-05 y no contesta a `server/discover`.
      Con el modo `auto` de FastMCP 4 cada conexión espera a que expire el
      sondeo (≈60 s) antes de caer al `initialize` clásico.
    * `keep_alive=True`: un único proceso REA, reutilizado entre llamadas. REA
      mantiene estado en proceso (documentos abiertos, snapshots); relanzarlo
      por llamada lo perdería y pagaría el arranque en cada una.
    """
    if backend is None:
        backend = StdioTransport(
            command=settings.rea_command,
            args=list(settings.rea_args),
            env=_child_env(),
            keep_alive=True,
        )
    return Client(
        backend,
        mode="legacy",
        timeout=settings.rea_call_timeout,
        init_timeout=settings.rea_init_timeout,
    )


async def _probe_backend(client: Client, timeout: float) -> dict[str, Any]:
    """Conecta con el backend y cuenta sus tools. Nunca lanza."""
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            async with client.new() as session:
                tools = await session.list_tools()
                init = session.initialize_result
        info = getattr(init, "server_info", None)
        return {
            "reachable": True,
            "name": getattr(info, "name", None),
            "version": getattr(info, "version", None),
            "tools": len(tools),
            "latency_s": round(time.monotonic() - started, 2),
        }
    except Exception as exc:  # noqa: BLE001 - el health check debe informar, no propagar
        return {
            "reachable": False,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_s": round(time.monotonic() - started, 2),
        }


# ── Servidor ───────────────────────────────────────────────────────────────

def build_server(
    settings: Optional[Settings] = None,
    backend: Any = None,
) -> FastMCP:
    """Construye el servidor FastMCP con el backend REA montado."""
    settings = settings or Settings.from_env()

    auth = None
    if settings.transport == "http" and settings.auth_token:
        auth = StaticTokenVerifier(
            tokens={settings.auth_token: {"client_id": SERVER_NAME, "scopes": []}}
        )

    mcp = FastMCP(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        version=SERVER_VERSION,
        auth=auth,
    )
    backend_client = build_backend_client(settings, backend)

    @mcp.tool(
        annotations={
            "title": "REA health check",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def health_check(check_deps: bool = True) -> dict[str, Any]:
        """Comprueba el estado del servidor y su conexión con el backend REA.

        Con check_deps=True verifica que el comando de REA existe y que el
        backend responde (la primera vez puede tardar: REA arranca en frío).
        """
        report: dict[str, Any] = {
            "status": "healthy",
            "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "timestamp": time.time(),
        }
        if not check_deps:
            report["dependencies"] = "skipped"
            return report

        command_path = shutil.which(settings.rea_command)
        backend_report = await _probe_backend(backend_client, settings.rea_init_timeout)
        report["dependencies"] = {
            "rea_command": {"command": settings.rea_command, "found": command_path is not None},
            "backend": backend_report,
        }
        # Con un backend inyectado no hay comando que buscar.
        command_ok = command_path is not None or backend is not None
        if not (command_ok and backend_report["reachable"]):
            report["status"] = "degraded"
        return report

    @mcp.custom_route("/health", methods=["GET"])
    async def http_health(_: Request) -> JSONResponse:
        """Liveness barata para Docker: no arranca ni consulta el backend REA."""
        return JSONResponse(
            {"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION}
        )

    # Sin namespace: el cliente ve las tools/prompts de REA tal cual.
    mcp.mount(create_proxy(backend_client, name="rea"))
    return mcp


# ── Entry point ────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m src.server",
        description="Servidor MCP para REA (Reverse Engineer Anything) sobre FastMCP.",
    )
    parser.add_argument(
        "--transport", choices=VALID_TRANSPORTS, help="stdio (defecto) o http"
    )
    parser.add_argument(
        "--stdio",
        dest="transport",
        action="store_const",
        const="stdio",
        help="alias de --transport stdio (compatibilidad)",
    )
    parser.add_argument("--host", help="solo http (defecto 127.0.0.1)")
    parser.add_argument("--port", type=int, help="solo http (defecto 8000)")
    parser.add_argument("--path", help="solo http (defecto /mcp)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)

    # La CLI prevalece sobre el entorno; ambas pasan por la misma validación.
    env = dict(os.environ)
    for arg_name, env_name in (
        ("transport", "MCP_TRANSPORT"),
        ("host", "MCP_HOST"),
        ("port", "MCP_PORT"),
        ("path", "MCP_PATH"),
    ):
        value = getattr(args, arg_name)
        if value is not None:
            env[env_name] = str(value)

    try:
        settings = Settings.from_env(env)
    except ConfigError as exc:
        print(f"Configuración inválida: {exc}", file=sys.stderr)
        return 2

    # En stdio, stdout es el canal del protocolo: todo el log va a stderr.
    logging.basicConfig(
        level=settings.log_level,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    mcp = build_server(settings)
    if settings.transport == "stdio":
        logger.info("Arrancando %s %s por stdio", SERVER_NAME, SERVER_VERSION)
        mcp.run(transport="stdio", show_banner=False)
    else:
        logger.info(
            "Arrancando %s %s por HTTP en %s:%s%s (auth=%s)",
            SERVER_NAME,
            SERVER_VERSION,
            settings.host,
            settings.port,
            settings.path,
            "token" if settings.auth_token else "ninguna (loopback)",
        )
        mcp.run(
            transport="http",
            host=settings.host,
            port=settings.port,
            path=settings.path,
            show_banner=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
