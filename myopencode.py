"""CLI entry point: `python -m myopencode "create a fibonacci function"`.

Runs the agent loop headlessly against the local Ollama models and prints
the final result to stdout. No confirmation prompts (destructive tools run
immediately) — use the web UI for interactive sessions.
"""
import os
import sys

os.environ.setdefault("NO_CONFIRM", "1")
os.environ.setdefault("PYTHONUTF8", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent_loop  # noqa: E402
from tools.llm import pick_task_model  # noqa: E402
from tools._state import MODEL  # noqa: E402


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Usage: python -m myopencode \"<task>\"", file=sys.stderr)
        return 2
    task = " ".join(argv)
    model = pick_task_model(task, MODEL)
    out = run_agent_loop([{"role": "user", "content": task}], None, model=model)
    if out:
        print("\n" + out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
