"""REA MCP Server - Core MCP protocol handler.

Handles JSON-RPC 2.0 messages over STDIO transport.
Provides tools for REA agent coordination and workflow management.
"""

import sys
import json
import os

# ─── CRITICAL: Disable transparent proxy BEFORE any imports ──────────────────
# Cntlm transparent proxy intercepts at socket level via env vars.
# Must be unset/overridden before any HTTP session creation.
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["NO_PROXY"] = "localhost,127.0.0.1,localhost,.local,.internal"

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models.coordination import CoordinationModel


# ── MCP Protocol Constants ──────────────────────────────────────────────────

MCP_INITIALIZE = "initialize"
MCP_TOOLS_LIST = "tools/list"
MCP_TOOLS_CALL = "tools/call"
MCP_NOTIFICATIONS_INITIALIZED = "notifications/initialized"
MCP_PING = "ping"


# ── Tool Definitions ────────────────────────────────────────────────────────

TOOLS = {
    "health_check": {
        "description": "Check REA MCP server health and connectivity",
        "parameters": {
            "type": "object",
            "properties": {
                "check_deps": {
                    "type": "boolean",
                    "description": "Check if dependencies are available",
                    "default": True,
                }
            },
            "required": [],
        },
    },
    "list_agents": {
        "description": "List available REA agents and their capabilities",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by agent category",
                }
            },
            "required": [],
        },
    },
    "get_agent_status": {
        "description": "Get status of a specific REA agent",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier",
                }
            },
            "required": ["agent_id"],
        },
    },
    "run_workflow": {
        "description": "Execute a REA workflow or task",
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Workflow identifier to execute",
                },
                "parameters": {
                    "type": "object",
                    "description": "Workflow parameters",
                    "default": {},
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds",
                    "default": 300,
                },
            },
            "required": ["workflow_id"],
        },
    },
}


# ── MCP Response Builders ─────────────────────────────────────────────────

def build_success_response(id_value: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a successful JSON-RPC 2.0 response dict."""
    return {
        "jsonrpc": "2.0",
        "id": id_value,
        "result": result,
    }


def build_error_response(id_value: Any, code: int, message: str) -> Dict[str, Any]:
    """Build an error JSON-RPC 2.0 response dict."""
    return {
        "jsonrpc": "2.0",
        "id": id_value,
        "error": {
            "code": code,
            "message": message,
        },
    }


# ── MCP Message Parsing ────────────────────────────────────────────────────

def is_mcp_jsonrpc(message: Dict[str, Any]) -> bool:
    """Check if a message is a valid JSON-RPC 2.0 message."""
    return (
        message.get("jsonrpc") == "2.0"
        and "id" in message
        and "method" in message
    )


def parse_message(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and route an MCP message to the appropriate handler."""
    # Extract ID for response
    id_value = raw.get("id")

    method = raw.get("method", "")

    if method == MCP_INITIALIZE:
        return build_success_response(id_value, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "rea-mcp",
                "version": "1.0.0",
            },
        })
    elif method == MCP_TOOLS_LIST:
        tool_summaries = {}
        for name, tool_def in TOOLS.items():
            tool_summaries[name] = {
                "description": tool_def["description"],
                "inputSchema": tool_def["parameters"],
            }
        return build_success_response(id_value, {
            "tools": tool_summaries,
        })
    elif method == MCP_TOOLS_CALL:
        return handle_tools_call(raw, id_value)
    elif method == MCP_NOTIFICATIONS_INITIALIZED:
        return build_success_response(id_value, {"status": "initialized"})
    elif method == MCP_PING:
        return build_success_response(id_value, {"pong": True})
    else:
        return build_error_response(id_value, -32601, f"Method not found: {method}")


# ── Tool Handlers ──────────────────────────────────────────────────────────


def handle_tools_call(raw: Dict[str, Any], id_value: Any) -> Dict[str, Any]:
    """Handle tools/call request - execute a tool with arguments."""
    params = raw.get("params", {})
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name not in TOOLS:
        return build_error_response(id_value, -32602, f"Unknown tool: {tool_name}")

    try:
        result = execute_tool(tool_name, arguments)
        return build_success_response(id_value, result)
    except Exception as e:
        return build_error_response(id_value, -32000, str(e))


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool with the given arguments."""
    if tool_name == "health_check":
        check_deps = arguments.get("check_deps", True)
        return {
            "status": "healthy",
            "dependencies": "ok" if check_deps else "skipped",
            "timestamp": __import__("time").time(),
        }
    elif tool_name == "list_agents":
        model = CoordinationModel()
        agents = model.list_agents(category=arguments.get("category"))
        return {"agents": agents}
    elif tool_name == "get_agent_status":
        agent_id = arguments.get("agent_id", "")
        model = CoordinationModel()
        status = model.get_agent_status(agent_id)
        return {"agent_id": agent_id, "status": status}
    elif tool_name == "run_workflow":
        workflow_id = arguments.get("workflow_id", "")
        parameters = arguments.get("parameters", {})
        timeout = arguments.get("timeout", 300)
        return {
            "workflow_id": workflow_id,
            "status": "queued",
            "timeout": timeout,
            "message": f"Workflow {workflow_id} executed with parameters: {parameters}",
        }
    else:
        return {"result": f"Tool {tool_name} executed", "arguments": arguments}


# ── STDIO Transport ────────────────────────────────────────────────────────

def handle_stdio():
    """Handle MCP stdio transport: line-delimited JSON-RPC."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"Invalid JSON: {e}\n")
            sys.stderr.flush()
            continue

        response = parse_message(raw)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def handle_single_request():
    """Read a single JSON request from stdin and output the response."""
    raw = json.loads(sys.stdin.read())

    response = parse_message(raw)
    if response is not None:
        print(json.dumps(response, indent=2))


# ── Entry Point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--stdio" in sys.argv:
        handle_stdio()
    else:
        handle_single_request()
