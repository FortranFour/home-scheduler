"""Small HA service/storage doubles; test the real scheduler, not a copy of it."""
import copy
import importlib.util
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    value = types.ModuleType(name)
    sys.modules[name] = value
    return value


vol = module("voluptuous")
vol.Schema = lambda value, **kw: (lambda data: data)
vol.Any = lambda *args: args
vol.Optional = vol.Required = lambda value: value
vol.ALLOW_EXTRA = object()
module("homeassistant")
config_entries=module("homeassistant.config_entries")
config_entries.SOURCE_IMPORT="import"


class ConfigFlow:
    def __init_subclass__(cls, **kw):
        super().__init_subclass__()
    def _async_current_entries(self):
        return getattr(self,"entries",[])
    async def async_set_unique_id(self,value):
        self.unique_id=value
    def _abort_if_unique_id_configured(self):
        pass
    def async_create_entry(self,**kw):
        return {"type":"create_entry",**kw}
    def async_abort(self,**kw):
        return {"type":"abort",**kw}
    def async_show_form(self,**kw):
        return {"type":"form",**kw}


config_entries.ConfigFlow=ConfigFlow
module("homeassistant.components")
frontend=module("homeassistant.components.frontend")
frontend.add_extra_js_url=lambda hass,url:hass.modules.add(url)
frontend.remove_extra_js_url=lambda hass,url:hass.modules.discard(url)
http=module("homeassistant.components.http")


@dataclass
class StaticPathConfig:
    url_path:str
    path:str
    cache_headers:bool


http.StaticPathConfig=StaticPathConfig
const = module("homeassistant.const")
const.EVENT_HOMEASSISTANT_STARTED, const.EVENT_HOMEASSISTANT_STOP = "started", "stop"
exceptions = module("homeassistant.exceptions")
exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
module("homeassistant.helpers")
service = module("homeassistant.helpers.service")
service.async_register_admin_service = lambda hass,domain,name,handler,**kw: hass.services.registered.update({(domain,name):handler})
storage = module("homeassistant.helpers.storage")


class MemoryStore:
    def __init__(self, hass, version, key):
        self.saved = None
    async def async_load(self):
        return copy.deepcopy(self.saved)
    async def async_save(self, value):
        self.saved = copy.deepcopy(value)
    def async_delay_save(self, fn, delay):
        self.saved = copy.deepcopy(fn())


storage.Store = MemoryStore
module("homeassistant.util")
dt = module("homeassistant.util.dt")
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
dt.now = lambda: NOW
dt.utcnow = lambda: NOW
spec = importlib.util.spec_from_file_location("home_scheduler_test_target",
    ROOT / "custom_components/home_scheduler/__init__.py",
    submodule_search_locations=[str(ROOT / "custom_components/home_scheduler")])
target = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = target
spec.loader.exec_module(target)
mathmod = sys.modules[spec.name + ".schedule"]


class States:
    def __init__(self):
        self.values = {}
    def get(self, entity):
        return self.values.get(entity)
    def is_state(self, entity, value):
        state = self.get(entity)
        return state is not None and state.state == value
    def async_set(self, entity, value, attributes=None):
        self.values[entity] = types.SimpleNamespace(state=value, attributes=attributes or {})
    def async_remove(self, entity):
        self.values.pop(entity,None)


class Services:
    def __init__(self, states):
        self.calls = []
        self.states = states
        self.fail = False
        self.registered = {}
    def async_remove(self,domain,name):
        self.registered.pop((domain,name),None)
    async def async_call(self, domain, action, data, **kw):
        self.calls.append((domain, action, copy.deepcopy(data), kw))
        if self.fail:
            raise RuntimeError("Fixture service failure")
        entity = data["entity_id"]
        old = self.states.get(entity)
        if old is None:
            return
        attrs = {**old.attributes, **{k: v for k, v in data.items() if k != "entity_id"}}
        state = old.state
        if domain == "cover":
            position = data.get("position", 100 if action == "open_cover" else 0)
            attrs["current_position"] = position
            state = "open" if position else "closed"
        elif domain == "scene":
            state = NOW.isoformat()
        else:
            state = "on" if action == "turn_on" else "off"
        self.states.async_set(entity, state, attrs)


def hass_fixture():
    states = States()
    return types.SimpleNamespace(states=states, services=Services(states))


def mask(start, end):
    result = mathmod.ZERO
    for slot in range(start, end):
        result = mathmod.put(result, slot, True)
    return result
