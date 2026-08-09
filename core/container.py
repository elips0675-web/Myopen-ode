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
    event_bus     -> EventBus (stage 66) — pub/sub for modules
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


# ─── stage 66: event bus (pub/sub) ────────────────────────
class EventBus:
    """Thread-safe publish/subscribe bus.

    Modules publish lifecycle events ("tool.executed", "agent.iteration",
    "subagent.finished"...) and other modules subscribe to react without
    coupling to each other. Handler exceptions are logged and isolated —
    one bad subscriber never breaks the publisher or other subscribers.

    Events in use:
        tool.executed        {"name", "ok", "result_preview"}
        agent.iteration      {"it", "max_iter", "tool", "ok"}
        agent.done           {"reason", "text_preview"}
        subagent.spawned     {"agent_type", "prompt_preview"}
        subagent.finished    {"agent_type", "ok", "result_preview"}
    """

    def __init__(self):
        self._subs = {}  # event -> {token: handler}
        self._lock = threading.Lock()
        self._seq = 0

    def subscribe(self, event, handler):
        """Register handler(event, payload). Returns a token for unsubscribe()."""
        with self._lock:
            self._seq += 1
            token = (event, self._seq)
            self._subs.setdefault(event, {})[token] = handler
            return token

    def once(self, event, handler):
        """One-shot subscription: removed after the first fire."""
        token = []

        def wrapped(ev, payload):
            self.unsubscribe(token[0])
            handler(ev, payload)

        token.append(self.subscribe(event, wrapped))
        return token[0]

    def unsubscribe(self, token):
        with self._lock:
            subs = self._subs.get(token[0])
            if subs:
                subs.pop(token, None)
                if not subs:
                    self._subs.pop(token[0], None)

    def publish(self, event, payload=None):
        with self._lock:
            handlers = list(self._subs.get(event, {}).values())
        for h in handlers:
            try:
                h(event, payload)
            except Exception:
                import logging
                logging.getLogger("core.container").warning(
                    "event handler failed for %r", event, exc_info=True)

    def has_subscribers(self, event):
        with self._lock:
            return bool(self._subs.get(event))

    def clear(self):
        with self._lock:
            self._subs.clear()


def new_event_bus():
    return EventBus()
