# mcp-rea

Servidor MCP sobre [FastMCP](https://github.com/PrefectHQ/fastmcp) para
[REA (Reverse Engineer Anything)](https://www.npmjs.com/package/rea-agents), el
MCP de ingeniería inversa para binarios nativos, aplicaciones JavaScript/Electron,
ensamblados .NET y sitios web.

Este servidor **no reimplementa REA**: lanza el MCP oficial (`rea-agents mcp`,
protocolo 2024-11-05 por stdio) y lo reexpone con FastMCP. Un cliente ve el mismo
catálogo que hablando directamente con REA (170 tools y 6 prompts en 6.4.0), más:

| Aporta | Detalle |
|---|---|
| Transporte HTTP | Streamable HTTP con token Bearer, además de stdio |
| `health_check` | Tool que comprueba de verdad el backend (comando, conexión, nº de tools) |
| `GET /health` | Liveness para Docker; no arranca ni consulta REA |
| Arranque seguro | Se niega a servir HTTP fuera de loopback sin `MCP_AUTH_TOKEN` |
| Un solo proceso REA | Reutilizado entre llamadas: REA guarda estado en proceso |

## Requisitos

- Python ≥ 3.11
- Node ≥ 22.19 (lo exige `rea-agents`) y acceso a npm la primera vez
- Para análisis nativo, un proveedor instalado (Hopper, Ghidra o IDA); ver la
  [documentación de REA](https://rea.tools/)

```bash
pip install -r requirements.txt
```

## Uso

### stdio (Claude Desktop, Claude Code, Cursor…)

```json
{
  "mcpServers": {
    "rea": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/ruta/a/mcp-rea"
    }
  }
}
```

Con Claude Code: `claude mcp add rea --scope user -- python -m src.server`
(ejecutado desde la carpeta del repo, o con la ruta completa en `cwd`).

El cliente debe dejar `node`/`npx` en el `PATH` del proceso.

### HTTP

```bash
export MCP_AUTH_TOKEN=$(openssl rand -hex 32)
python -m src.server --transport http          # 127.0.0.1:8000/mcp
```

Los clientes envían `Authorization: Bearer <token>`. En loopback el token es
opcional; fuera de loopback es obligatorio.

### Docker

```bash
cp .env.example .env        # defina MCP_AUTH_TOKEN
docker compose up -d --build
```

Publica `127.0.0.1:8000` y monta `./targets` (o `REA_TARGETS_DIR`) como `/targets`
en solo lectura: ahí van los artefactos a analizar. Para stdio:
`docker run -i --rm rea-mcp`.

> La imagen instala `rea-agents` una vez en build y lo ejecuta directamente,
> sin `npx` en tiempo de ejecución.

## Configuración

Todas por variable de entorno (ver `.env.example`); `--transport`, `--host`,
`--port` y `--path` en la CLI prevalecen.

| Variable | Defecto | Descripción |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` o `http` |
| `MCP_HOST` / `MCP_PORT` / `MCP_PATH` | `127.0.0.1` / `8000` / `/mcp` | Solo HTTP |
| `MCP_AUTH_TOKEN` | — | Token Bearer; obligatorio si el host no es loopback |
| `REA_COMMAND` / `REA_ARGS` | `npx` / `-y --prefer-offline rea-agents@6.4.0 mcp` | Cómo lanzar REA |
| `REA_INIT_TIMEOUT` | `180` | Segundos para arrancar REA |
| `REA_CALL_TIMEOUT` | `600` | Segundos por llamada a una tool |
| `LOG_LEVEL` | `INFO` | Se escribe en stderr (stdout es el canal del protocolo) |

`MCP_AUTH_TOKEN` no se hereda al proceso REA; el resto del entorno sí, para que
REA vea su propia configuración de proveedores.

## Desarrollo

```bash
pip install -r requirements-dev.txt
pytest                              # unitarios, backend simulado en memoria
REA_INTEGRATION=1 pytest -m integration   # contra el REA real
```

## Límites conocidos

- **Estado compartido.** Hay un único proceso REA; todos los clientes HTTP
  comparten documentos abiertos y snapshots. Pensado para un usuario o equipo
  pequeño, no para multiusuario aislado.
- **Arranque en frío.** La primera conexión descarga `rea-agents` si no está en
  la caché de npm; por eso el timeout de arranque es generoso.
- **Modo `legacy` forzado hacia REA.** FastMCP 4 negocia por defecto con
  `server/discover`, que REA no contesta: cada conexión esperaría ~60 s. Si REA
  pasa a hablar el protocolo moderno, se puede quitar `mode="legacy"` en
  `build_backend_client`.
