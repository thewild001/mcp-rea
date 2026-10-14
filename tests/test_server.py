import sys

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from starlette.testclient import TestClient

from src.config import Settings
from src.server import SERVER_NAME, SERVER_VERSION, _child_env, build_server, main

# ── Catálogo proxied ───────────────────────────────────────────────────────


async def test_lists_local_and_proxied_tools_without_prefix(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        names = {t.name for t in await client.list_tools()}
    assert {"health_check", "echo", "add"} <= names


async def test_proxied_tool_call_round_trips(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        echoed = await client.call_tool("echo", {"text": "hola"})
        total = await client.call_tool("add", {"a": 2, "b": 3})
    assert echoed.data == "hola"
    assert total.data == 5


async def test_proxied_prompts(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        assert "investigate_feature" in {p.name for p in await client.list_prompts()}
        result = await client.get_prompt("investigate_feature", {"target": "Notes"})
    assert "Investigate Notes" in result.messages[0].content.text


async def test_backend_without_resources_does_not_break_listing(fake_rea):
    # REA responde "Method not found" a resources/list; el cliente no debe verlo.
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        assert await client.list_resources() == []


async def test_unknown_tool_is_a_tool_error(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        with pytest.raises(Exception):
            await client.call_tool("no_existe", {})


# ── health_check ───────────────────────────────────────────────────────────


async def test_health_check_reports_backend(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        report = (await client.call_tool("health_check", {})).data
    assert report["status"] == "healthy"
    assert report["server"] == {"name": SERVER_NAME, "version": SERVER_VERSION}
    backend = report["dependencies"]["backend"]
    assert backend["reachable"] is True
    assert backend["tools"] == 2  # echo + add; health_check es local, no del backend


async def test_health_check_can_skip_dependencies(fake_rea):
    server = build_server(Settings(), backend=fake_rea)
    async with Client(server) as client:
        report = (await client.call_tool("health_check", {"check_deps": False})).data
    assert report["status"] == "healthy"
    assert report["dependencies"] == "skipped"


async def test_health_check_degrades_instead_of_raising_when_backend_is_down():
    # Un backend que muere al arrancar: el health check informa, no explota.
    dead = StdioTransport(command=sys.executable, args=["-c", "import sys; sys.exit(1)"])
    server = build_server(Settings(rea_init_timeout=20.0), backend=dead)
    async with Client(server) as client:
        report = (await client.call_tool("health_check", {})).data
    assert report["status"] == "degraded"
    backend = report["dependencies"]["backend"]
    assert backend["reachable"] is False
    assert backend["error"]


# ── HTTP: liveness y autenticación ─────────────────────────────────────────

INIT_REQUEST = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _http_app(fake_rea, **overrides):
    settings = Settings(transport="http", **overrides)
    return build_server(settings, backend=fake_rea).http_app(path=settings.path)


def test_health_route_is_up_and_does_not_touch_backend(fake_rea):
    with TestClient(_http_app(fake_rea)) as http:
        resp = http.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION}


def test_mcp_endpoint_requires_token_when_configured(fake_rea):
    app = _http_app(fake_rea, auth_token="s3cret")
    with TestClient(app) as http:
        missing = http.post("/mcp", json=INIT_REQUEST, headers=MCP_HEADERS)
        wrong = http.post(
            "/mcp", json=INIT_REQUEST, headers={**MCP_HEADERS, "Authorization": "Bearer nope"}
        )
        valid = http.post(
            "/mcp", json=INIT_REQUEST, headers={**MCP_HEADERS, "Authorization": "Bearer s3cret"}
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert valid.status_code == 200


def test_liveness_stays_open_even_with_auth(fake_rea):
    # /health no expone nada del backend, así que Docker puede sondearlo sin token.
    with TestClient(_http_app(fake_rea, auth_token="s3cret")) as http:
        assert http.get("/health").status_code == 200


# ── Entorno y arranque ─────────────────────────────────────────────────────


def test_child_env_never_leaks_the_server_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "s3cret")
    monkeypatch.setenv("REA_SOME_PROVIDER_SETTING", "keep-me")
    env = _child_env()
    assert "MCP_AUTH_TOKEN" not in env
    assert env["REA_SOME_PROVIDER_SETTING"] == "keep-me"


def test_main_rejects_insecure_config_with_exit_code_2(monkeypatch, capsys):
    for name in ("MCP_TRANSPORT", "MCP_HOST", "MCP_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    code = main(["--transport", "http", "--host", "0.0.0.0"])
    assert code == 2
    assert "MCP_AUTH_TOKEN" in capsys.readouterr().err
