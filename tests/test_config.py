import pytest

from src.config import ConfigError, Settings


def test_defaults():
    s = Settings.from_env({})
    assert s.transport == "stdio"
    assert s.log_level == "INFO"
    assert s.rea_command == "npx"
    assert "rea-agents@6.4.0" in s.rea_args
    assert s.rea_args[-1] == "mcp"
    assert s.host == "127.0.0.1" and s.port == 8000 and s.path == "/mcp"
    assert s.auth_token is None


def test_env_overrides_are_parsed():
    s = Settings.from_env(
        {
            "LOG_LEVEL": "debug",
            "MCP_TRANSPORT": "HTTP",
            "MCP_PORT": "9000",
            "MCP_PATH": "rea",  # sin barra inicial: se normaliza
            "REA_CALL_TIMEOUT": "42.5",
        }
    )
    assert s.log_level == "DEBUG"
    assert s.transport == "http"
    assert s.port == 9000
    assert s.path == "/rea"
    assert s.rea_call_timeout == 42.5


def test_custom_command_requires_args():
    with pytest.raises(ConfigError, match="REA_ARGS"):
        Settings.from_env({"REA_COMMAND": "rea-agents"})


def test_custom_command_with_args():
    s = Settings.from_env({"REA_COMMAND": "rea-agents", "REA_ARGS": "mcp"})
    assert s.rea_command == "rea-agents"
    assert s.rea_args == ("mcp",)


def test_args_respect_shell_quoting():
    s = Settings.from_env({"REA_COMMAND": "node", "REA_ARGS": '"/opt/my dir/rea.mjs" mcp'})
    assert s.rea_args == ("/opt/my dir/rea.mjs", "mcp")


@pytest.mark.parametrize(
    "env",
    [
        {"MCP_TRANSPORT": "carrier-pigeon"},
        {"LOG_LEVEL": "LOUD"},
        {"MCP_PORT": "abc"},
        {"MCP_PORT": "0"},
        {"MCP_PORT": "70000"},
        {"REA_INIT_TIMEOUT": "-1"},
        {"REA_CALL_TIMEOUT": "mucho"},
    ],
)
def test_invalid_values_raise(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_http_off_loopback_requires_token():
    with pytest.raises(ConfigError, match="MCP_AUTH_TOKEN"):
        Settings.from_env({"MCP_TRANSPORT": "http", "MCP_HOST": "0.0.0.0"})


def test_http_off_loopback_with_token_is_ok():
    s = Settings.from_env(
        {"MCP_TRANSPORT": "http", "MCP_HOST": "0.0.0.0", "MCP_AUTH_TOKEN": "s3cret"}
    )
    assert s.auth_token == "s3cret"


def test_http_on_loopback_without_token_is_ok():
    assert Settings.from_env({"MCP_TRANSPORT": "http"}).auth_token is None


def test_stdio_ignores_host_restriction():
    # Con stdio no se abre ningún puerto: el host no importa.
    Settings.from_env({"MCP_TRANSPORT": "stdio", "MCP_HOST": "0.0.0.0"})


def test_blank_token_is_treated_as_unset():
    assert Settings.from_env({"MCP_AUTH_TOKEN": "   "}).auth_token is None
