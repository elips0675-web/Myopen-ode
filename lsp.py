"""LSP client — JSON-RPC communication with language servers."""

import json, os, subprocess, threading, logging, time
from pathlib import Path

log = logging.getLogger('lsp')

LSP_SERVERS = {
    ".py":  ["pylsp"],
    ".js":  ["typescript-language-server", "--stdio"],
    ".ts":  ["typescript-language-server", "--stdio"],
    ".jsx": ["typescript-language-server", "--stdio"],
    ".tsx": ["typescript-language-server", "--stdio"],
    ".go":  ["gopls"],
    ".rs":  ["rust-analyzer"],
    ".java": ["java", "-jar", "eclipse.jdt.ls"],
}

class LSPClient:
    def __init__(self, workspace):
        self.workspace = str(Path(workspace).resolve())
        self.proc = None
        self.req_id = 0
        self.buffer = ""
        self.responses = {}
        self.cv = threading.Condition()
        self._ready = False

    def _ensure_server(self, ext):
        cmd = LSP_SERVERS.get(ext)
        if not cmd: return None
        if self.proc and self.proc.poll() is None: return True
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=self.workspace,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREAT_NO_WINDOW') else 0
            )
            threading.Thread(target=self._reader, daemon=True).start()
            self._send({
                "jsonrpc": "2.0", "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "processId": os.getpid(),
                    "rootUri": f"file://{self.workspace}",
                    "capabilities": {
                        "textDocument": {
                            "definition": {"dynamicRegistration": False},
                            "references": {"dynamicRegistration": False},
                            "hover": {"dynamicRegistration": False},
                            "documentSymbol": {"dynamicRegistration": False},
                        }
                    },
                }
            })
            self._wait_response(self.req_id)
            self._send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
            self._ready = True
            return True
        except Exception as e:
            log.warning("LSP start failed for %s: %s", ext, e)
            return False

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    def _send(self, msg):
        if not self.proc or not self.proc.stdin: return
        data = json.dumps(msg)
        header = f"Content-Length: {len(data)}\r\n\r\n"
        try:
            self.proc.stdin.write(header.encode())
            self.proc.stdin.write(data.encode())
            self.proc.stdin.flush()
        except: pass

    def _wait_response(self, rid, timeout=10):
        with self.cv:
            if rid not in self.responses:
                self.cv.wait(timeout=timeout)
            return self.responses.pop(rid, None)

    def _reader(self):
        while self.proc and self.proc.stdout:
            try:
                line = self.proc.stdout.readline()
                if not line: break
                line = line.decode("utf-8", errors="ignore").strip()
                if line.startswith("Content-Length:"):
                    length = int(line.split(":")[1].strip())
                    # Skip blank line
                    self.proc.stdout.readline()
                    body = self.proc.stdout.read(length).decode("utf-8", errors="ignore")
                    try:
                        data = json.loads(body)
                        rid = data.get("id")
                        if rid:
                            with self.cv:
                                self.responses[rid] = data
                                self.cv.notify_all()
                    except: pass
            except: break

    def _open_doc(self, path):
        uri = f"file://{Path(path).resolve()}"
        try:
            text = Path(path).read_text("utf-8", errors="ignore")
        except: text = ""
        self._send({
            "jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {
                "textDocument": {"uri": uri, "languageId": self._lang(path), "version": 1, "text": text}
            }
        })
        return uri

    def _lang(self, path):
        ext = Path(path).suffix
        return {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascriptreact", ".tsx": "typescriptreact",
            ".go": "go", ".rs": "rust", ".java": "java",
        }.get(ext, "plaintext")

    def _close_doc(self, uri):
        self._send({
            "jsonrpc": "2.0", "method": "textDocument/didClose",
            "params": {"textDocument": {"uri": uri}}
        })

    def goto_definition(self, path, line, character):
        ext = Path(path).suffix
        if not self._ensure_server(ext): return "LSP not available for " + ext
        uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            }
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        return self._fmt_location(result)

    def find_references(self, path, line, character):
        ext = Path(path).suffix
        if not self._ensure_server(ext): return "LSP not available for " + ext
        uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/references",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True}
            }
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        return self._fmt_location(result, multi=True)

    def hover(self, path, line, character):
        ext = Path(path).suffix
        if not self._ensure_server(ext): return "LSP not available for " + ext
        uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character}
            }
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        if result and "result" in result:
            contents = result["result"].get("contents", {})
            if isinstance(contents, dict):
                return contents.get("value", str(contents))
            return str(contents)
        return "No hover info"

    def document_symbols(self, path):
        ext = Path(path).suffix
        if not self._ensure_server(ext): return "LSP not available for " + ext
        uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": uri}}
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        if not result or "result" not in result: return "No symbols"
        symbols = result["result"]
        if not symbols: return "No symbols"
        lines = []
        for s in symbols:
            name = s.get("name", "?")
            kind = ["", "File", "Module", "Namespace", "Package", "Class", "Method", "Property", "Field", "Constructor", "Enum", "Interface", "Function", "Variable", "Constant", "String", "Number", "Boolean", "Array", "Object", "Key", "Null", "EnumMember", "Struct", "Event", "Operator", "TypeParameter"].get(s.get("kind", 0), "?")
            r = s.get("range", {}); r2 = s.get("selectionRange", {})
            pos = r2.get("start", r.get("start", {}))
            lines.append(f"  {kind} {name} — line {pos.get('line', 0)+1}")
        return "\n".join(lines)

    def completion(self, path, line, character, text=None):
        """Request autocomplete items. text = current editor buffer (optional)."""
        ext = Path(path).suffix
        if not self._ensure_server(ext): return None
        uri = f"file://{Path(path).resolve()}"
        if text is not None:
            self._send({
                "jsonrpc": "2.0", "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {"uri": uri, "languageId": self._lang(path), "version": 1, "text": text}
                }
            })
        else:
            uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"triggerKind": 1}
            }
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        if not result or "error" in result or "result" not in result:
            return None
        items = result["result"]
        if isinstance(items, dict): items = items.get("items", [])
        return [
            {
                "label": it.get("label", ""),
                "kind": it.get("kind", 0),
                "detail": it.get("detail", ""),
                "insertText": it.get("insertText") or it.get("label", ""),
            }
            for it in items[:50]
        ]

    def rename(self, path, line, character, new_name):
        ext = Path(path).suffix
        if not self._ensure_server(ext): return "LSP not available for " + ext
        uri = self._open_doc(path)
        rid = self._next_id()
        self._send({
            "jsonrpc": "2.0", "id": rid,
            "method": "textDocument/rename",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "newName": new_name
            }
        })
        result = self._wait_response(rid)
        self._close_doc(uri)
        if not result or "error" in result or "result" not in result:
            return "Rename failed"
        changes = result["result"].get("changes", {}) or {}
        total = 0
        for uri2, edits in changes.items():
            p = uri2.replace("file://", "").replace("/", "\\") if "://" in uri2 else uri2
            try:
                if not os.path.isabs(p): p = os.path.join(self.workspace, p)
                with open(p, "r", encoding="utf-8") as f: text = f.read()
                # Apply edits in reverse order
                lines = text.split("\n")
                for ed in sorted(edits, key=lambda e: -e["range"]["start"]["line"]):
                    r = ed["range"]; s = r["start"]; en = r["end"]
                    if s["line"] == en["line"]:
                        line_text = lines[s["line"]]
                        lines[s["line"]] = line_text[:s["character"]] + ed["newText"] + line_text[en["character"]:]
                    else:
                        lines[s["line"]] = lines[s["line"]][:s["character"]] + ed["newText"]
                        del lines[s["line"]+1:en["line"]+1]
                with open(p, "w", encoding="utf-8") as f: f.write("\n".join(lines))
                total += len(edits)
            except Exception as e:
                return f"Rename apply error in {p}: {e}"
        return f"Renamed: {total} edits applied"

    def _fmt_location(self, result, multi=False):
        if not result or "result" not in result or not result["result"]:
            return "Not found"
        data = result["result"]
        if multi and isinstance(data, list):
            lines = []
            for loc in data:
                uri = loc.get("uri", "")
                r = loc.get("range", {})
                start = r.get("start", {})
                path = uri.replace("file://", "").replace("/", "\\") if "://" in uri else uri
                lines.append(f"  {path}:{start.get('line', 0)+1}:{start.get('character', 0)}")
            return "\n".join(lines) if lines else "No references"
        if isinstance(data, list):
            data = data[0] if data else {}
        uri = data.get("uri", "")
        r = data.get("range", {})
        start = r.get("start", {})
        path = uri.replace("file://", "").replace("/", "\\") if "://" in uri else uri
        return f"{path}:{start.get('line', 0)+1}:{start.get('character', 0)}"

    def stop(self):
        if self.proc:
            try:
                self._send({"jsonrpc": "2.0", "method": "shutdown", "id": self._next_id()})
                self.proc.terminate()
            except: pass
            self.proc = None
