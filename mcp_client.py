"""External MCP client support.

Connects to external MCP servers (stdio) listed in mcp_servers.json:
{
  "servers": [
    {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "E:/Projects"]}
  ]
}
Exposes each server's tools via the "mcp" tool: {"tool": "mcp", "server": "filesystem", "call": "read_file", "args": {...}}
"""

import json, os, subprocess, threading, logging
from pathlib import Path

log = logging.getLogger("mcp")

CONFIG_PATH = Path(__file__).parent / "mcp_servers.json"
_procs = {}
_tools = {}
_lock = threading.Lock()


def _load_config():
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("servers", [])
    except Exception as e:
        log.warning("mcp config load failed: %s", e)
    return []


class MCPStdioClient:
    def __init__(self, name, command, args):
        self.name = name
        self.command = command
        self.args = args or []
        self.proc = None
        self.req_id = 0
        self.responses = {}
        self.cv = threading.Condition()
        self.ready = False

    def start(self):
        if self.proc and self.proc.poll() is None:
            return True
        try:
            self.proc = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
            )
            threading.Thread(target=self._reader, daemon=True).start()
            self._request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "my-opencode", "version": "2.0"},
            }, timeout=15)
            self.ready = True
            return True
        except Exception as e:
            log.warning("MCP %s start failed: %s", self.name, e)
            return False

    def _reader(self):
        while self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line: break
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                except: continue
                if "id" in data:
                    with self.cv:
                        self.responses[data["id"]] = data
                        self.cv.notify_all()
                elif data.get("method") == "notifications/tools/list_changed":
                    with self.cv:
                        self.responses["_tools_changed"] = True
                        self.cv.notify_all()
            except: break

    def _request(self, method, params, timeout=30):
        with self.cv:
            self.req_id += 1
            rid = self.req_id
            self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}) + "\n")
            self.proc.stdin.flush()
            self.cv.wait(timeout=timeout)
            return self.responses.pop(rid, None)

    def list_tools(self):
        result = self._request("tools/list", {})
        if not result or "result" not in result:
            return []
        tools = result["result"].get("tools", [])
        self._cache_tools(tools)
        return tools

    def _cache_tools(self, tools):
        with _lock:
            _tools[self.name] = {t.get("name"): t for t in tools}

    def call_tool(self, name, args):
        result = self._request("tools/call", {"name": name, "arguments": args or {}})
        if not result or "result" not in result:
            return f"MCP error: {result}"
        content = result["result"].get("content", [])
        parts = []
        for c in content:
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            else:
                parts.append(str(c))
        return "\n".join(parts)

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
            except: pass
            self.proc = None


def get_clients():
    """Return {name: client} — starts configured servers lazily."""
    clients = {}
    for cfg in _load_config():
        name = cfg.get("name", "")
        if not name: continue
        with _lock:
            client = _procs.get(name)
        if client is None:
            client = MCPStdioClient(name, cfg.get("command", ""), cfg.get("args", []))
            if not client.command:
                continue
            with _lock:
                _procs[name] = client
        clients[name] = client
    return clients


def mcp_tools_list():
    """All external tool names with their servers, e.g. [("filesystem", "read_file"), ...]."""
    out = []
    for name, client in get_clients().items():
        if not client.ready:
            client.start()
        if not client.ready:
            continue
        try:
            tools = client.list_tools()
        except Exception as e:
            log.warning("MCP %s list_tools failed: %s", name, e)
            continue
        for t in tools:
            out.append((name, t.get("name", "")))
    return out


def mcp_call(server, tool, args):
    """Call an external MCP tool. Returns text result or error message."""
    client = get_clients().get(server)
    if client is None:
        return f"MCP server '{server}' not configured (see mcp_servers.json)"
    if not client.ready:
        client.start()
    if not client.ready:
        return f"MCP server '{server}' failed to start"
    try:
        return client.call_tool(tool, args)
    except Exception as e:
        return f"MCP call error: {e}"
