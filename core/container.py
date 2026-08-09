"""Stage 41: tiny dependency-injection container.

API routers no longer reach into `import agent as _agent` for runtime
state (WORK_DIR, SESSIONS_DIR, logger...). Instead they resolve services
through this container. agent.py registers providers at startup; the
providers are callables so values stay CURRENT after switch_project()
mutates globals.

Registered services (agent.py):
    work_dir      -> lambda: WORK_DIR
    sessions_dir  -> lambda: SESSIONS_DIR
    memory_dir    -> lambda: MEMORY_DIR
    logger        -> lambda: log
    rag           -> RagStore adapter (stage 42)
    sessions_db   -> SessionsStore adapter (stage 42)
"""
import threading

_REGISTRY = {}
_LOCK = threading.Lock()


def register(name, provider):
    """provider: callable returning the current service value (no args)."""
    with _LOCK:
        _REGISTRY[name] = provider


def resolve(name):
    with _LOCK:
        provider = _REGISTRY.get(name)
    if provider is None:
        raise KeyError(f"service '{name}' not registered in DI container")
    return provider()


def has(name):
    return name in _REGISTRY


def reset():
    with _LOCK:
        _REGISTRY.clear()


# convenience aliases used by api_*.py
def work_dir():
    return resolve("work_dir")


def sessions_dir():
    return resolve("sessions_dir")


def logger():
    return resolve("logger")
