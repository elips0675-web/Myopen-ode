"""Built-in stdio MCP server (JSON-RPC 2.0 over stdin/stdout, newline-delimited).

Serves a few demo tools (echo, add, path_exists) and one resource so that
external MCP integration can be tested and demoed without installing any
npm packages. Run it as:

    python mcp_servers.py

and point mcp_servers.json at it:
    {"servers": [{"name": "local", "command": "python", "args": ["mcp_servers.py"]}]}
"""

import json, sys
from pathlib import Path

SERVER_INFO = {"name": "my-opencode-local", "version": "1.0"}

TOOLS = [
    {
        "name": "echo",
        "description": "Return the input text back.",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {
        "name": "add",
        "description": "Sum two numbers.",
        "inputSchema": {"type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                        "required": ["a", "b"]},
    },
    {
        "name": "path_exists",
        "description": "Check whether a filesystem path exists.",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
]

RESOURCES = [
    {"uri": "local://readme", "name": "Local README",
     "description": "README of the built-in local MCP server"},
]


def _text(content):
    return {"content": [{"type": "text", "text": content}]}


def handle(method, params):
    params = params or {}
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": SERVER_INFO}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "resources/list":
        return {"resources": RESOURCES}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "echo":
            return _text("echo: " + str(args.get("text", "")))
        if name == "add":
            return _text("sum=" + str(float(args.get("a", 0)) + float(args.get("b", 0))))
        if name == "path_exists":
            return _text(str(Path(str(args.get("path", ""))).exists()).lower())
        raise ValueError(f"unknown tool: {name}")
    if method == "resources/read":
        uri = params.get("uri")
        if uri == "local://readme":
            return {"contents": [{"uri": uri, "mimeType": "text/markdown",
                                  "text": "# Local MCP\nBuilt-in stdio server for My OpenCode."}]}
        raise ValueError(f"unknown resource: {uri}")
    raise ValueError(f"unsupported method: {method}")


def main():
    if sys.platform == "win32":
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("local MCP server ready", file=sys.stderr, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        rid = msg.get("id")
        if msg.get("method") == "notifications/initialized":
            continue
        try:
            result = handle(msg.get("method"), msg.get("params"))
            out = {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as e:
            out = {"jsonrpc": "2.0", "id": rid,
                   "error": {"code": -32601, "message": str(e)}}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
