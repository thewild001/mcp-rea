"""Configuración en tiempo de ejecución, leída de variables de entorno.

Ninguna variable es obligatoria para uso local por stdio. Para exponer el
servidor por HTTP fuera de loopback se exige MCP_AUTH_TOKEN (ver `validate`).
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Mapping, Optional

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
VALID_TRANSPORTS = ("stdio", "http")
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Comando por defecto para lanzar el MCP oficial de REA. En Docker se
# sobreescribe con el binario instalado (REA_COMMAND=rea-agents, REA_ARGS=mcp)
# para no depender de `npx` ni de la red en tiempo de ejecución.
#
# `--prefer-offline` es deliberado: sin él, `npx -y` consulta el registro en
# cada arranque y, si la red no es alcanzable (proxy ausente, sin conexión),
# se queda ~70 s esperando antes de usar la caché. Con la versión fijada y ya
# en caché arranca en ~3 s; si no está en caché, la descarga igualmente.
DEFAULT_REA_COMMAND = "npx"
DEFAULT_REA_ARGS = "-y --prefer-offline rea-agents@6.4.0 mcp"


class ConfigError(ValueError):
    """Configuración inválida o insegura."""


def _float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser numérico, recibido {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} debe ser > 0, recibido {raw!r}")
    return value


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe ser entero, recibido {raw!r}") from exc
    if not 1 <= value <= 65535:
        raise ConfigError(f"{name} fuera de rango (1-65535): {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Parámetros del servidor. Inmutable; se construye con `from_env`."""

    log_level: str = "INFO"

    # Backend REA (proceso hijo por stdio).
    rea_command: str = DEFAULT_REA_COMMAND
    rea_args: tuple[str, ...] = tuple(shlex.split(DEFAULT_REA_ARGS))
    # REA arranca lento en frío (npx descarga el paquete). Margen amplio.
    rea_init_timeout: float = 180.0
    # Un análisis nativo grande puede tardar minutos.
    rea_call_timeout: float = 600.0

    # Transporte hacia los clientes MCP.
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"
    auth_token: Optional[str] = None

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if env is None else env

        command = (env.get("REA_COMMAND") or DEFAULT_REA_COMMAND).strip()
        args_raw = env.get("REA_ARGS")
        if args_raw is None or args_raw.strip() == "":
            # Si solo se cambió el comando, los args por defecto (npx -y ...)
            # no tienen sentido: se exigen explícitos.
            if command != DEFAULT_REA_COMMAND:
                raise ConfigError(
                    "REA_COMMAND personalizado requiere REA_ARGS (p. ej. REA_ARGS=mcp)"
                )
            args_raw = DEFAULT_REA_ARGS

        path = (env.get("MCP_PATH") or "/mcp").strip()
        if not path.startswith("/"):
            path = "/" + path

        token = (env.get("MCP_AUTH_TOKEN") or "").strip() or None

        settings = cls(
            log_level=(env.get("LOG_LEVEL") or "INFO").strip().upper(),
            rea_command=command,
            rea_args=tuple(shlex.split(args_raw)),
            rea_init_timeout=_float(env, "REA_INIT_TIMEOUT", 180.0),
            rea_call_timeout=_float(env, "REA_CALL_TIMEOUT", 600.0),
            transport=(env.get("MCP_TRANSPORT") or "stdio").strip().lower(),
            host=(env.get("MCP_HOST") or "127.0.0.1").strip(),
            port=_int(env, "MCP_PORT", 8000),
            path=path,
            auth_token=token,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.log_level not in VALID_LOG_LEVELS:
            raise ConfigError(
                f"LOG_LEVEL inválido {self.log_level!r}; use uno de {VALID_LOG_LEVELS}"
            )
        if self.transport not in VALID_TRANSPORTS:
            raise ConfigError(
                f"MCP_TRANSPORT inválido {self.transport!r}; use uno de {VALID_TRANSPORTS}"
            )
        if self.transport == "http" and self.auth_token is None:
            if self.host not in LOOPBACK_HOSTS:
                # REA puede leer binarios locales y lanzar análisis nativo:
                # exponerlo en red sin autenticación no es aceptable.
                raise ConfigError(
                    f"MCP_HOST={self.host!r} no es loopback: defina MCP_AUTH_TOKEN "
                    "para exponer el servidor por HTTP"
                )
