"""Análisis de un binario nativo real con Ghidra, a través de este servidor.

Desactivada por defecto: necesita Ghidra 12.1.x + JDK 21 y un compilador de C.
La imagen Docker ya lo trae todo; fuera de Docker, defina GHIDRA_INSTALL_DIR y
JAVA_HOME. Actívela con:

    REA_INTEGRATION=1 GHIDRA_INSTALL_DIR=/ruta/ghidra pytest -m integration
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client

from src.config import Settings
from src.server import build_server

SECRET = "REA-TEST-2026-OK"

C_SOURCE = f"""
#include <stdio.h>
#include <string.h>

static int check_license(const char *key) {{
    return strcmp(key, "{SECRET}") == 0;
}}

int main(int argc, char **argv) {{
    if (argc < 2) return 2;
    return check_license(argv[1]) ? 0 : 1;
}}
"""

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("REA_INTEGRATION") != "1",
        reason="defina REA_INTEGRATION=1 para usar el REA real",
    ),
    pytest.mark.skipif(
        not os.environ.get("GHIDRA_INSTALL_DIR"),
        reason="defina GHIDRA_INSTALL_DIR (Ghidra 12.1.x)",
    ),
    pytest.mark.skipif(shutil.which("gcc") is None, reason="se necesita gcc para crear el binario"),
]


def _text(result) -> str:
    data = getattr(result, "structured_content", None) or getattr(result, "data", None)
    if data is not None:
        return json.dumps(data, default=str)
    return "".join(getattr(block, "text", "") for block in result.content)


@pytest.fixture(scope="module")
def crackme(tmp_path_factory) -> Path:
    workdir = tmp_path_factory.mktemp("native")
    source, binary = workdir / "crackme.c", workdir / "crackme"
    source.write_text(C_SOURCE)
    subprocess.run(["gcc", "-O0", "-o", str(binary), str(source)], check=True)
    return binary


async def test_native_analysis_through_the_server(crackme):
    server = build_server(Settings.from_env())
    async with Client(server, timeout=900) as client:
        opened = await client.call_tool("open_binary", {"path": str(crackme)}, raise_on_error=False)
        assert not opened.is_error, _text(opened)[:400]

        procedures = _text(await client.call_tool("list_procedures", {}))
        assert '"ghidra"' in procedures.lower(), "el análisis no lo hizo Ghidra"
        assert "check_license" in procedures

        pseudo = await client.call_tool(
            "procedure_pseudo_code", {"procedure": "check_license"}, raise_on_error=False
        )
        assert not pseudo.is_error
        # El pseudo-código recuperado debe contener la comparación con el secreto.
        assert re.search(r"strcmp\(.*" + re.escape(SECRET), _text(pseudo).replace('\\"', '"'))

        strings = _text(await client.call_tool("search_strings", {"pattern": "REA-TEST"}))
        assert SECRET in strings

        await client.call_tool("close_binary", {}, raise_on_error=False)
