"""Prueba contra el backend REA real (`npx rea-agents`).

Desactivada por defecto: descarga/arranca REA (unos segundos en caliente,
bastante más en frío) y necesita Node >= 22.19. Actívela con:

    REA_INTEGRATION=1 pytest -m integration
"""

import os

import pytest
from fastmcp import Client

from src.config import Settings
from src.server import build_server

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("REA_INTEGRATION") != "1",
        reason="defina REA_INTEGRATION=1 para usar el REA real",
    ),
]


@pytest.fixture
def real_server():
    return build_server(Settings.from_env())


async def test_catalog_is_proxied_without_collisions(real_server):
    async with Client(real_server, timeout=300) as client:
        names = [t.name for t in await client.list_tools()]
        prompts = {p.name for p in await client.list_prompts()}
        resources = await client.list_resources()
    assert len(names) > 100
    assert "health_check" in names
    assert len(names) == len(set(names)), "una tool de REA colisiona con una local"
    assert "investigate_feature" in prompts
    assert resources == []


async def test_health_check_against_real_backend(real_server):
    async with Client(real_server, timeout=300) as client:
        report = (await client.call_tool("health_check", {})).data
    assert report["status"] == "healthy"
    assert report["dependencies"]["backend"]["name"] == "rea"
