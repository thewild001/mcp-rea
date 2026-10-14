"""Fixtures compartidas.

Los tests unitarios no lanzan REA: usan un FastMCP en memoria como backend, que
se inyecta en `build_server(settings, backend=...)`.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP


@pytest.fixture
def fake_rea() -> FastMCP:
    """Backend REA simulado: una tool, un prompt y ningún resource.

    Como el REA real, no implementa resources.
    """
    backend = FastMCP("fake-rea")

    @backend.tool
    def echo(text: str) -> str:
        """Devuelve el texto recibido."""
        return text

    @backend.tool
    def add(a: int, b: int) -> int:
        """Suma dos enteros."""
        return a + b

    @backend.prompt
    def investigate_feature(target: str) -> str:
        """Prompt de ejemplo."""
        return f"Investigate {target}"

    return backend
