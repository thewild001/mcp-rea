# mcp-rea

Servidor MCP para [REA (Reverse Engineer Anything)](https://www.npmjs.com/package/rea-agents),
construido sobre [FastMCP](https://github.com/PrefectHQ/fastmcp) y empaquetado en Docker.
Expone las tools y prompts de REA a cualquier agente compatible con MCP, más un
`health_check` para comprobar que todo funciona. La imagen incluye **Ghidra 12.1.4 y
JDK 21**, así que también analiza binarios nativos sin instalar nada más (probado
con ELF x86-64).

## 1. Construir la imagen

Solo hace falta Docker:

```bash
docker build -t rea-mcp .
```

- **Apple Silicon / ARM:** use `docker build --platform linux/amd64 -t rea-mcp .`.
  La release oficial de Ghidra solo trae decompilador nativo para x86-64.
- La primera vez descarga Ghidra (~540 MB, con verificación SHA-256) y termina con
  una prueba real de análisis (~30 s): en x86-64, **si el build acaba bien, el
  análisis nativo funciona**. En ARM la prueba no se ejecuta y solo avisa. Para
  omitirla: `--build-arg SKIP_SMOKE=1`.

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

## 4. Analizar un binario

Ponga el binario en la carpeta montada y pida al agente algo como:
*«Abre `/targets/miapp` y decompila la función que valida la licencia»*. El agente
usa `open_binary`, `list_procedures`, `procedure_pseudo_code`, `search_strings`…
con Ghidra por debajo.

Para comprobarlo sin agente, sobre su propio binario:

```bash
docker run --rm --entrypoint python -v /ruta/a/artefactos:/targets:ro rea-mcp \
  scripts/smoke_native.py /targets/miapp
```

**Memoria.** Ghidra usa 2 GB de heap por defecto. Para binarios grandes súbalo
(y dé al contenedor memoria de sobra, p. ej. en Docker Desktop) añadiendo a los
argumentos de `docker run`, antes de `rea-mcp`: `-e GHIDRA_HEADLESS_MAXMEM=6G`.

## Problemas habituales

| Síntoma | Causa y solución |
|---|---|
| `Unable to find image 'rea-mcp'` | No construyó la imagen (paso 1) o está en otra máquina. |
| El servidor no conecta o responde basura | Lleva `-t` en el comando, o Docker no está en marcha. |
| opencode dice que expiró | Suba `timeout`; el defecto es 5000 ms. |
| No encuentra mis archivos | Use la ruta `/targets/...` y monte la carpeta con `-v`. |
| `provider_unavailable` al analizar | Ghidra no está operativo: reconstruya la imagen (en ARM, con `--platform linux/amd64`). |
| `Analysis could not complete` | Casi siempre memoria: suba `GHIDRA_HEADLESS_MAXMEM` y la memoria del contenedor. |

## Límites

- **Hopper e IDA** no están en la imagen; con Docker el análisis nativo lo hace Ghidra.
- La imagen pesa bastante (Ghidra + JDK + Node + Python): del orden de 2 GB (estimado).
- Hay un único proceso REA por contenedor, compartido por todo lo que se conecte a él.
- Variables avanzadas (HTTP, tokens, timeouts) en `.env.example`; tests con
  `pip install -r requirements-dev.txt && pytest`.
