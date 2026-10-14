"""Prueba de humo del análisis nativo, de extremo a extremo.

Arranca este mismo servidor MCP por stdio, abre un binario con el proveedor
nativo (Ghidra) y comprueba que lista procedimientos. Falla con código distinto
de 0 si el análisis nativo no funciona, así que sirve igual en el `docker build`
que a mano:

    python scripts/smoke_native.py                 # analiza /bin/true
    python scripts/smoke_native.py /targets/app    # analiza su binario

    docker run --rm --entrypoint python rea-mcp scripts/smoke_native.py

Códigos de salida: 0 correcto, 1 el análisis falló, 2 uso incorrecto.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = "/bin/true"
# El primer análisis de Ghidra es lento (JVM en frío + análisis automático).
TIMEOUT_S = float(os.environ.get("SMOKE_TIMEOUT", "600"))


def _text(result) -> str:
    data = getattr(result, "structured_content", None) or getattr(result, "data", None)
    if data is not None:
        return json.dumps(data, default=str)
    return "".join(getattr(block, "text", "") for block in result.content)


async def run(target: str) -> int:
    transport = StdioTransport(
        command=sys.executable,
        args=["-m", "src.server"],
        cwd=str(ROOT),
        env=dict(os.environ),
        keep_alive=False,
    )
    # mode="legacy": REA habla 2024-11-05 (ver src/server.py).
    async with Client(transport, mode="legacy", timeout=TIMEOUT_S, init_timeout=TIMEOUT_S) as client:
        opened = await client.call_tool("open_binary", {"path": target}, raise_on_error=False)
        if opened.is_error:
            print(f"FALLO open_binary({target}): {_text(opened)[:600]}", file=sys.stderr)
            return 1

        listed = await client.call_tool("list_procedures", {}, raise_on_error=False)
        body = _text(listed)
        await client.call_tool("close_binary", {}, raise_on_error=False)

        if listed.is_error:
            print(f"FALLO list_procedures: {body[:600]}", file=sys.stderr)
            return 1
        if '"ghidra"' not in body.lower():
            print("FALLO: el análisis no lo hizo Ghidra (¿GHIDRA_INSTALL_DIR/JAVA_HOME?).", file=sys.stderr)
            print(body[:600], file=sys.stderr)
            return 1

    print(f"OK: {target} analizado con Ghidra y procedimientos listados.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 2 or (len(argv) == 2 and argv[1] in ("-h", "--help")):
        print(__doc__, file=sys.stderr)
        return 2
    target = argv[1] if len(argv) == 2 else DEFAULT_TARGET
    if not Path(target).is_file():
        print(f"No existe el binario: {target}", file=sys.stderr)
        return 2
    return asyncio.run(run(target))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
