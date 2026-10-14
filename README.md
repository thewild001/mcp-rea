# mcp-rea

Servidor MCP para [REA (Reverse Engineer Anything)](https://www.npmjs.com/package/rea-agents),
construido sobre [FastMCP](https://github.com/PrefectHQ/fastmcp) y empaquetado en Docker.
Expone las tools y prompts de REA a cualquier agente compatible con MCP, más un
`health_check` para comprobar que todo funciona.

## 1. Construir la imagen

Solo hace falta Docker:

```bash
docker build -t rea-mcp .
```

## 2. Registrarlo en el agente

El agente lanza el contenedor por stdio con este comando:

```
docker run -i --rm --init -v /ruta/a/artefactos:/targets:ro rea-mcp
```

- Sustituya `/ruta/a/artefactos` por la **ruta absoluta** de la carpeta con lo que
  quiera analizar. El agente la verá como `/targets/...`.
- Use `-i`, **nunca `-t`**: un TTY corrompe el protocolo.

### Claude Code

```bash
claude mcp add rea --scope user -- docker run -i --rm --init -v /ruta/a/artefactos:/targets:ro rea-mcp
```

O en `.mcp.json` (proyecto):

```json
{
  "mcpServers": {
    "rea": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init", "-v", "/ruta/a/artefactos:/targets:ro", "rea-mcp"]
    }
  }
}
```

### Claude Desktop

Mismo bloque JSON anterior, en `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`).
Reinicie la aplicación.

### Cursor

`.cursor/mcp.json` (proyecto) o `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "rea": {
      "type": "stdio",
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init", "-v", "/ruta/a/artefactos:/targets:ro", "rea-mcp"]
    }
  }
}
```

### opencode

`opencode.json` (proyecto) o `~/.config/opencode/opencode.json` (global). Aquí el
comando es un único array y el `timeout` es imprescindible: el defecto (5 s) es
poco para arrancar el contenedor.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "rea": {
      "type": "local",
      "command": ["docker", "run", "-i", "--rm", "--init", "-v", "/ruta/a/artefactos:/targets:ro", "rea-mcp"],
      "enabled": true,
      "timeout": 60000
    }
  }
}
```

### Hermes Agent

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  rea:
    command: "docker"
    args: ["run", "-i", "--rm", "--init", "-v", "/ruta/a/artefactos:/targets:ro", "rea-mcp"]
    connect_timeout: 60
    timeout: 600
```

Recargue con `/reload-mcp` (o abra una sesión nueva) y compruebe con
`hermes mcp test rea`. Los valores de `connect_timeout` y `timeout` no tienen
unidad documentada; se asumen segundos, así que revíselos si algo expira.

## 3. Comprobar que funciona

Pida al agente que llame a la tool **`health_check`**. Debe devolver
`status: "healthy"` y `backend.reachable: true`. La primera llamada tarda unos
segundos más porque REA arranca en frío.

## Problemas habituales

| Síntoma | Causa y solución |
|---|---|
| `Unable to find image 'rea-mcp'` | No construyó la imagen (paso 1) o está en otra máquina. |
| El servidor no conecta o responde basura | Lleva `-t` en el comando, o Docker no está en marcha. |
| opencode dice que expiró | Suba `timeout`; el defecto es 5000 ms. |
| No encuentra mis archivos | Use la ruta `/targets/...` y monte la carpeta con `-v`. |

## Límites

- **Análisis nativo** (Hopper, Ghidra, IDA): esos programas viven en su máquina y el
  contenedor no los ve. Para ese caso ejecute el servidor sin Docker:
  `pip install -r requirements.txt` y use `python -m src.server` como comando.
- Hay un único proceso REA por contenedor, compartido por todo lo que se conecte a él.
- Variables avanzadas (HTTP, tokens, timeouts) en `.env.example`; tests con
  `pip install -r requirements-dev.txt && pytest`.
