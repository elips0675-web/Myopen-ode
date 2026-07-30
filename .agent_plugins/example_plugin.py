"""Example plugin for AI Coder v2.
Create .py files in .agent_plugins/ with a register() function.
Each tool gets a dict with "func" (callable) and "schema" (for validation).
"""

import os, subprocess
from pathlib import Path

def register():
    tools = {}
    defs = {}

    def count_lines(args):
        path = args.get("path", ".")
        p = Path(path)
        if not p.exists(): return f"Error: {path} not found"
        if p.is_dir():
            total = 0
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".h"):
                    try: total += len(f.read_text().splitlines())
                    except: pass
            return f"Total lines in {path}: {total}"
        return f"Lines: {len(p.read_text().splitlines())}"

    def format_code(args):
        path = args.get("path", "")
        p = Path(path)
        if not p.exists(): return f"Error: {path} not found"
        ext = p.suffix
        if ext == ".py":
            try:
                import autopep8
                code = p.read_text()
                formatted = autopep8.fix_code(code)
                p.write_text(formatted)
                return f"Formatted {path} with autopep8"
            except ImportError:
                return "Install autopep8: pip install autopep8"
        return f"No formatter for {ext}"

    def git_stats(args):
        try:
            r = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True, text=True, timeout=10)
            commits = r.stdout.strip()
            r2 = subprocess.run(["git", "shortlog", "-sn", "--all"], capture_output=True, text=True, timeout=10)
            authors = r2.stdout.strip()
            return f"Recent commits:\n{commits}\n\nAuthors:\n{authors}"
        except: return "Git not available"

    tools["count_lines"] = count_lines
    tools["format_code"] = format_code
    tools["git_stats"] = git_stats

    defs["count_lines"] = {"schema": {"required": []}}
    defs["format_code"] = {"schema": {"required": ["path"]}}
    defs["git_stats"] = {"schema": {"required": []}}

    return tools, defs
