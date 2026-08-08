"""Plugin loading from .agent_plugins/*.py."""
import importlib.util, sys
import logging
from . import _state
from ._state import PLUGINS, TOOL_SCHEMAS, WORK_DIR
from ._state import _sync_register

log = logging.getLogger("tools")

def load_plugins():
    global PLUGINS
    PLUGINS = {}
    _state.PLUGINS = PLUGINS
    pd = WORK_DIR / ".agent_plugins"
    if not pd.exists(): return
    for f in sorted(pd.glob("*.py")):
        try:
            mod_name = f.stem
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "register"):
                    tools, defs = mod.register()
                    for name in tools:
                        PLUGINS[name] = {"module": mod, "tools": tools, "defs": defs}
                        if name in tools:
                            TOOL_SCHEMAS[name] = defs.get("schema", {"required": []})
                    log.info("Plugin loaded: %s (%d tools)", mod_name, len(tools))
        except Exception as e:
            log.warning("Plugin load failed %s: %s", f.name, e)

def call_plugin(name, args):
    plugin = PLUGINS.get(name)
    if not plugin: return None
    func = plugin["tools"].get(name)
    if func: return func(args)
    return None

_sync_register(sys.modules[__name__])
