"""Tool block parsers extracted from agent.py/tools.py.

Parsing layer only (no HTTP, no loop): ```tool/json blocks, bare JSON,
yaml-style blocks, lenient JSON, pending-tool extraction, marker stripping.
"""
import json
import re

TOOL_BLOCK_PAT = re.compile(r'```(?:tool|json)\n(.*?)\n```', re.DOTALL)
BARE_TOOL_PAT = re.compile(r'\{\s*"tool"\s*:\s*"[^"]+"\s*.*?\}', re.DOTALL)
YAML_TOOL_PAT = re.compile(r'```[^\n]*\ntool\s+(\w+)\n(.*?)\n```', re.DOTALL)


def _parse_tool_json(raw):
    """Parse a ```tool block body with lenient heuristics:
    plain JSON -> single quotes -> unquoted keys -> trailing-comma / garbage
    trimming (models often append prose after the closing brace)."""
    attempts = [raw, raw.replace("'", '"')]
    attempts.append(re.sub(r'([{,]\s*)([A-Za-z_]\w*)\s*:', r'\1"\2":', attempts[-1]))
    attempts.append(re.sub(r':\s*([A-Za-z_][A-Za-z0-9_]*)([\s,}])', r': "\1"\2', attempts[-1]))
    for a in attempts:
        try:
            return json.loads(a)
        except json.JSONDecodeError:
            pass
    # trailing garbage / unterminated last value: try truncating at last '}'
    for i in range(len(raw) - 1, -1, -1):
        if raw[i] == "}":
            head = re.sub(r",\s*}", "}", raw[: i + 1])
            try:
                return json.loads(head)
            except json.JSONDecodeError:
                try:
                    return json.loads(head.replace("'", '"'))
                except json.JSONDecodeError:
                    break
    raise json.JSONDecodeError("unparseable tool JSON", raw, 0)


def _strip_system_markers(text):
    """Remove fake system markers a model may echo inside its prose
    ([PLAN], [CONFIRM], [tool:...], "Reply 'yes'..."). Real markers are
    appended by the loop itself, so stripping them from model text is safe."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if (s.startswith(("[PLAN]", "[CONFIRM]", "[tool:", "[tool]", "[Format error"))
                or s.lower().startswith("reply 'yes'")
                or "```tool" in s):
            continue
        out.append(ln)
    return "\n".join(out)


def extract_pending_tool(msgs):
    """Find the last destructive ```tool block in history (used for the
    CONFIRM resume path). Returns (tool_name, args) or (None, None)."""
    bad = ("write", "edit", "bash", "commit", "undo")
    for m in reversed(msgs):
        if m.get("role") != "assistant":
            continue
        c = m.get("content", "")
        for match in TOOL_BLOCK_PAT.finditer(c):
            raw = match.group(1).strip()
            try:
                j = json.loads(raw)
            except json.JSONDecodeError:
                try:
                    j = json.loads(raw.replace("'", '"'))
                except json.JSONDecodeError:
                    continue
            n = j.get("tool", "")
            if n in bad:
                tc = dict(j)
                tc.pop("tool", None)
                return n, tc
        for match in BARE_TOOL_PAT.finditer(c):
            try:
                j = json.loads(match.group())
                n = j.get("tool", "")
                if n in bad:
                    tc = dict(j)
                    tc.pop("tool", None)
                    return n, tc
            except json.JSONDecodeError:
                pass
    return None, None


def parse_tool_blocks(content, valid_tools):
    """Extract all tool blocks from model output. Tries in order:
    ```tool/json fences -> bare JSON anywhere -> yaml-style `tool name` fences.
    Returns [(match, raw_text, parsed_json)]."""
    blocks = []
    for m in TOOL_BLOCK_PAT.finditer(content):
        raw = m.group(1).strip()
        try:
            j = _parse_tool_json(raw)
            blocks.append((m, raw, j))
        except json.JSONDecodeError:
            pass

    if not blocks:
        for match in BARE_TOOL_PAT.finditer(content):
            try:
                j = _parse_tool_json(match.group())
                if "tool" in j and j["tool"] in valid_tools:
                    blocks.append((match, match.group(), j))
                    break
            except json.JSONDecodeError:
                pass

    if not blocks:
        # yaml-style fallback: models sometimes emit `tool <name>` blocks
        # (```python\ntool write\npath "demo.py"\ncontent "..."\n```)
        for m in YAML_TOOL_PAT.finditer(content):
            name, body = m.group(1), m.group(2)
            if name not in valid_tools:
                continue
            args = {}
            for line in body.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or " " not in line:
                    continue
                k, _, v = line.partition(" ")
                k = k.strip().rstrip(":")
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                    v = v[1:-1]
                elif v.startswith("[") or v.startswith("{"):
                    try:
                        v = json.loads(v)
                    except json.JSONDecodeError:
                        pass
                args[k] = v
            if args:
                blocks.append((m, m.group(0), {"tool": name, **args}))
    return blocks
