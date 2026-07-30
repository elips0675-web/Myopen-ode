#!/usr/bin/env python3
"""MCP сервер — Model Context Protocol для интеграции с IDE (VS Code, Cursor, Claude Desktop)."""
import sys, json, os, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tools import execute_tool, validate_tool, TOOL_SCHEMAS, init_config, init_backup, WORK_DIR
from agent import OLLAMA_URL, MODEL, PLANNER_MODEL, EMBED_MODEL, NO_CONFIRM, MAX_TOKENS, OPENAI_KEY, ANTHROPIC_KEY, FALLBACK_MODEL

init_config(OLLAMA_URL=OLLAMA_URL, MODEL=MODEL, PLANNER_MODEL=PLANNER_MODEL, WORK_DIR=WORK_DIR,
    EMBED_MODEL=EMBED_MODEL, NO_CONFIRM=NO_CONFIRM, MAX_TOKENS=MAX_TOKENS,
    OPENAI_KEY=OPENAI_KEY, ANTHROPIC_KEY=ANTHROPIC_KEY, FALLBACK_MODEL=FALLBACK_MODEL)
init_backup()

logging.basicConfig(level=logging.WARNING, format='%(levelname)s [mcp] %(message)s')
log = logging.getLogger('mcp')

MCP_TOOL_MAP = {
    "read": "Read file content",
    "write": "Create or overwrite a file",
    "edit": "Replace text in a file",
    "bash": "Execute a shell command",
    "glob": "Find files by glob pattern",
    "grep": "Search file contents with regex",
    "list": "List directory contents",
    "web": "Fetch a URL",
    "diff": "Show git diff",
    "commit": "Git add + commit",
    "undo": "Restore file from backup",
    "verify": "Syntax check a file",
    "plan": "Propose a multi-step plan",
    "search": "Semantic code search (RAG)",
    "websearch": "Search the web via DuckDuckGo",
    "question": "Ask user a multiple choice question",
    "skill": "Load a .agent_skills/*.md skill",
    "patch": "Apply unified diff to file",
    "task": "Delegate to subagent (explore/scout/general)",
    "todo": "Manage in-session todo list",
    "lsp": "Code intelligence via LSP",
}

def build_tools_list():
    tools = []
    for name, desc in MCP_TOOL_MAP.items():
        schema = TOOL_SCHEMAS.get(name, {})
        required = schema.get("required", [])
        props = {}
        for key in required + schema.get("optional", []):
            props[key] = {"type": "string", "description": key}
        # Add common optional fields
        for key in ["cwd", "path", "content", "old", "new", "cmd", "pattern", "include",
                     "url", "message", "steps", "query", "top_k", "max_results",
                     "text", "options", "name", "diff", "agent", "prompt",
                     "operation", "line", "character", "action", "items", "index"]:
            if key not in props and key in str(schema):
                props[key] = {"type": "string", "description": key}
        tools.append({
            "name": name,
            "description": desc,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required if required else None,
            }
        })
    return tools

def handle_request(msg):
    req_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "0.1.0",
            "capabilities": {
                "tools": {},
                "resources": {},
                "logging": {},
            },
            "serverInfo": {"name": "ai-coder-mcp", "version": "2.0"}
        }}

    elif method == "notifications/initialized":
        return None

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": build_tools_list()}}

    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name not in MCP_TOOL_MAP:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        # Convert args to tool format
        tc = {"tool": name, **args}
        ve = validate_tool(tc)
        if ve:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": ve}}
        try:
            result = execute_tool(name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": str(result)}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": str(e)}}

    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}

    elif method == "shutdown":
        return {"jsonrpc": "2.0", "id": req_id, "result": None}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

def main():
    log.info("MCP server starting...")
    print("MCP server ready", file=sys.stderr)
    buffer = ""
    while True:
        try:
            line = sys.stdin.readline()
            if not line: break
            buffer += line
            # Try to parse complete JSON-RPC messages
            while True:
                try:
                    msg = json.loads(buffer)
                    buffer = ""
                    response = handle_request(msg)
                    if response:
                        sys.stdout.write(json.dumps(response) + "\n")
                        sys.stdout.flush()
                    break
                except json.JSONDecodeError:
                    # Incomplete message, wait for more
                    if len(buffer) > 100000:
                        buffer = ""
                    break
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error("Error: %s", e)
            buffer = ""

if __name__ == "__main__":
    main()
