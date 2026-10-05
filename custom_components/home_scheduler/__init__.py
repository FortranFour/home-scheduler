"""Home Scheduler preview: weekly device plans and isolated 3D simulation."""
import asyncio
import copy
import hashlib
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .defaults import DEFAULT_DEVICES
from .devices import (KINDS, effect_state, normalize_device, number, state_for,
                      validate_on, validate_outside, validate_target)
from .schedule import ZERO, put
from .timeline import build_timeline, frame_at, scene_markers, spans_for
from .model_import import MAX_DEVICES, import_bindings, parse_source, validate_model
from .const import ASSET_PATH, DOMAIN, VERSION

LOG = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Any(None, vol.Schema({
    vol.Optional("devices"): [dict],
})),}, extra=vol.ALLOW_EXTRA)


def boolean(value):
    if type(value) is not bool:
        raise HomeAssistantError("Use true or false for checkbox values")
    return value


class Scheduler:
    def __init__(self, hass, devices=None, model_presets_url=None):
        self.hass = hass
        self.model_presets_url = model_presets_url
        self.configured = devices is not None
        self.initial_devices = self.validate_catalog(DEFAULT_DEVICES if devices is None else devices)
        self.store = Store(hass, 1, DOMAIN)
        self.lock = asyncio.Lock()
        self.cache, self.data, self.requests, self.restore = {}, {}, {}, {}
        self.playing = self.stopping = False
        self.task = self.last_clock = self.last_plan = self.event_cursor = self.last_scene = None
        self.errors = []

    @staticmethod
    def validate_catalog(devices):
        if not isinstance(devices, list) or not 1 <= len(devices) <= MAX_DEVICES:
            raise ValueError("Choose between 1 and 128 devices")
        result = [normalize_device(d) for d in devices]
        catalog = {d["entity"]: d for d in result}
        if len(catalog) != len(result):
            raise ValueError("Preview entity IDs must be unique")
        targets = [d["target"] for d in result if d["target"]]
        if len(set(targets)) != len(targets):
            raise ValueError("Map each real entity to only one device row")
        for device in result:
            effects = device.get("effects", {})
            if not isinstance(effects, dict) or len(effects) > MAX_DEVICES:
                raise ValueError("Preview scene effects must be an object")
            for entity, effect in effects.items():
                if device["kind"] != "scene" or entity not in catalog:
                    raise ValueError("Scene effects must name devices in this preview")
                effect_state(catalog[entity], effect, {"attributes": {}})
        return result

    @property
    def devices(self):
        return self.data.get("devices", self.initial_devices)

    @property
    def ids(self):
        return {d["entity"] for d in self.devices}

    def device(self, entity):
        for device in self.devices:
            if device["entity"] == entity:
                return device
        raise HomeAssistantError("Device is outside this scheduler")

    def fresh_row(self, device):
        return {"use": device.get("use", True), "days": [ZERO] * 7,
                "outside": device["outside"], "off_position": device["off_position"],
                "on": copy.deepcopy(device["on"])}

    def fresh_profile(self, key, name, state="", demo=False):
        rows = {d["entity"]: self.fresh_row(d) for d in self.devices}
        if demo:
            for device in self.devices:
                mask = ZERO
                for start, end in device.get("slots", []):
                    for slot in range(start, end):
                        mask = put(mask, slot, True)
                rows[device["entity"]]["days"] = [mask] * 7
        return {"id": key, "name": name,
                "condition_entity": "input_select.home_scheduler_mode" if state else "",
                "condition_state": state, "scene": "", "rows": rows}

    async def load(self):
        saved = await self.store.async_load()
        self.data = {"devices": copy.deepcopy(self.initial_devices)}
        self.data.update({
            "profiles": [self.fresh_profile("weekly", "Weekly demo", demo=not self.configured),
                         self.fresh_profile("guest", "Guest", "Guest", demo=not self.configured),
                         self.fresh_profile("worker", "Worker", "Worker"),
                         self.fresh_profile("away", "Away", "Away", demo=not self.configured)],
            "watts": {d["entity"]: d["watts"] for d in self.devices},
            "random": {d["entity"]: False for d in self.devices},
            "profile": "weekly", "date": dt_util.now().date().isoformat(), "minute": 1110,
            "physical": False, "clock": False, "auto": False, "repeat": True,
            "jitter": 15, "seed": 1, "speed": 1.0,
            "shown_types": ["light"], "hidden_devices": [],
            "renderer": None, "renderer_revision": 0, "fired_events": {},
            "device_memory": {}, "imported_models": [], "model_imported": False,
            "last_import": None,
        })
        if isinstance(saved, dict):
            self.data.update(saved)
        self.data["devices"] = self.validate_catalog(self.initial_devices if self.configured and not self.data["model_imported"] else self.data["devices"])
        # This review integration always starts in simulation after a restart.
        self.data["physical"] = False
        for profile in self.data["profiles"]:
            for device in self.devices:
                entity = device["entity"]
                profile["rows"].setdefault(entity, self.fresh_row(device))
                self.data["watts"].setdefault(entity, device["watts"])
                self.data["random"].setdefault(entity, False)
        if self.data["profile"] not in {p["id"] for p in self.data["profiles"]}:
            self.data["profile"] = self.data["profiles"][0]["id"]
        self.data["hidden_devices"] = [e for e in self.data["hidden_devices"] if e in self.ids]

    def profile(self, key=None):
        key = self.data["profile"] if key is None else key
        for profile in self.data["profiles"]:
            if profile["id"] == key:
                return profile
        raise HomeAssistantError("Unknown schedule")

    def context(self):
        if self.data["clock"]:
            now = dt_util.now()
            profile = self.profile()
            if self.data["auto"]:
                profile = self.data["profiles"][0]
                for candidate in self.data["profiles"][1:]:
                    entity, state = candidate["condition_entity"], candidate["condition_state"]
                    current = self.hass.states.get(entity) if entity else None
                    if current and current.state not in ("unknown", "unavailable") and state and current.state == state:
                        profile = candidate
                        break
            return profile, now.date(), now.hour * 60 + now.minute
        return self.profile(), date.fromisoformat(self.data["date"]), self.data["minute"]

    def timeline(self, profile, day):
        key = (profile["id"], day.isoformat())
        if key not in self.cache:
            value = build_timeline(self.devices, profile, self.data, day)
            self.cache[key] = value
            if len(self.cache) > 24:
                self.cache = {key: value}
        return self.cache[key]

    def publish_plan(self):
        timeline = self.timeline(self.profile(), date.fromisoformat(self.data["date"]))
        attrs = {**{k: v for k, v in self.data.items() if k not in ("minute", "fired_events", "device_memory")},
                 "version": VERSION, "energy": timeline["energy"],
                 "model_presets_url": self.model_presets_url,
                 "friendly_name": "Home scheduler"}
        if attrs != self.last_plan:
            self.hass.states.async_set("sensor.home_scheduler", "ready", attrs)
            self.last_plan = copy.deepcopy(attrs)

    async def apply(self, control=True, advance=False):
        profile, day, minute = self.context()
        timeline = self.timeline(profile, day)
        virtual = frame_at(timeline, self.devices, minute, day)
        self.errors = []
        if control and self.data["physical"]:
            await self.apply_devices(profile, day, minute)
            if self.data["clock"]:
                await self.apply_activation(profile, day)
                await self.apply_events(profile, day, minute, advance)
        active = [e for e, value in virtual.items() if value["state"] == "on" or
                  (e.startswith("cover.") and value["attributes"].get("current_position", 0) > 0)]
        watts = 0.0
        for device in self.devices:
            entity = device["entity"]
            if device["kind"] in ("light", "switch", "fan") and virtual[entity]["state"] == "on":
                watts += self.data["watts"][entity]
            elif device["kind"] == "cover" and any(m["minute"] <= minute < m["minute"] + m["seconds"] / 60
                                                   for m in timeline["movements"][entity]):
                watts += self.data["watts"][entity]
        attrs = {"minute": minute, "date": day.isoformat(), "profile": profile["id"],
                 "profile_name": profile["name"], "physical": self.data["physical"],
                 "clock": self.data["clock"], "playing": self.playing, "on": sorted(active),
                 "states": virtual, "events": timeline["events"],
                 "watts": round(watts, 1), "kwh": round(sum(s["kwh"] or 0 for s in timeline["energy"].values()), 4),
                 "errors": list(dict.fromkeys(self.errors)), "friendly_name": "Home scheduler playback"}
        self.hass.states.async_set("sensor.home_scheduler_frame", "physical" if self.data["physical"] else "simulation", attrs)
        self.publish_plan()

    async def apply_devices(self, profile, day, minute):
        for device in self.devices:
            entity, kind = device["entity"], device["kind"]
            row, target = profile["rows"][entity], device["target"]
            if not row["use"] or kind == "scene" or not target:
                continue
            current = self.hass.states.get(target)
            if current is None or current.state in ("unknown", "unavailable"):
                self.errors.append(f"Unavailable: {target}")
                continue
            jitter = self.data["jitter"] if self.data["random"][entity] else 0
            active = any(a <= minute < b for a, b in spans_for(row, entity, day, self.data["seed"], jitter))
            desired = state_for(device, row, active)
            if active and row["outside"] == "restore":
                self.restore.setdefault(entity, {"state": current.state, "attributes": dict(current.attributes)})
            elif not active:
                if row["outside"] == "unchanged":
                    self.requests.pop(entity, None)
                    continue
                if row["outside"] == "restore":
                    desired = self.restore.get(entity)
                    if desired is None:
                        continue
            try:
                domain, action, values, matches = self.device_action(device, current, desired)
            except ValueError as err:
                self.errors.append(f"{device['name']}: {err}")
                continue
            signature = json.dumps([domain, action, values], sort_keys=True)
            pending = self.requests.get(entity)
            if matches:
                self.requests[entity] = (signature, 0)
                if not active and row["outside"] == "restore":
                    self.restore.pop(entity, None)
                continue
            if pending and pending[0] == signature and time.monotonic() < pending[1]:
                continue
            try:
                self.requests[entity] = (signature, time.monotonic() + max(10, device["travel_seconds"] + 5 if kind == "cover" else 10))
                await self.hass.services.async_call(domain, action, {"entity_id": target, **values}, blocking=False)
            except Exception as err:
                self.requests.pop(entity, None)
                self.errors.append(f"{device['name']}: {err}")

    @staticmethod
    def device_action(device, current, desired):
        domain = device["target"].split(".")[0]
        attrs, wanted = desired["attributes"], desired["state"]
        real = current.attributes
        if domain == "cover":
            position = attrs.get("current_position", 0 if wanted == "closed" else 100)
            actual = real.get("current_position")
            if position == 0:
                action, values = "close_cover", {}
            elif position == 100:
                action, values = "open_cover", {}
            elif int(real.get("supported_features", 0)) & 4:
                action, values = "set_cover_position", {"position": round(position)}
            else:
                raise ValueError("This cover supports open/closed only; choose 0 or 100%")
            matches = (actual is not None and abs(float(actual) - position) <= 1) or (actual is None and current.state == wanted and position in (0, 100))
            return domain, action, values, matches
        values, matches = {}, current.state == wanted
        if wanted == "on" and domain == "fan" and int(real.get("supported_features", 0)) & 1:
            percentage = attrs.get("percentage", 50)
            values["percentage"] = percentage
            matches = matches and real.get("percentage") == percentage
        if wanted == "on" and domain == "light":
            modes = set(real.get("supported_color_modes", []))
            if real.get("brightness") is not None or modes - {"onoff"}:
                brightness = attrs.get("brightness", 255)
                values["brightness"] = brightness
                matches = matches and abs(real.get("brightness", 0) - brightness) <= 1
            if modes & {"rgb", "rgbw", "rgbww", "hs", "xy"} and attrs.get("rgb_color"):
                color = list(attrs["rgb_color"])
                values["rgb_color"] = color
                matches = matches and list(real.get("rgb_color", [])) == color
        return domain, "turn_on" if wanted == "on" else "turn_off", values, matches

    async def apply_activation(self, profile, day):
        scene = profile.get("scene", "")
        if not scene:
            return
        device = next((d for d in self.devices if d["entity"] == scene), None)
        target = device["target"] if device else scene
        if not target:
            return
        key = f"activation|{profile['id']}|{day.isoformat()}|{target}"
        if key in self.data["fired_events"]:
            return
        current = self.hass.states.get(target)
        if current is None or current.state == "unavailable":
            self.errors.append(f"Scene unavailable: {target}")
            return
        self.data["fired_events"][key] = day.toordinal() * 1440
        await self.store.async_save(copy.deepcopy(self.data))
        try:
            await self.hass.services.async_call("scene", "turn_on", {"entity_id": target}, blocking=False)
        except Exception as err:
            self.errors.append(f"Scene: {err}")

    async def apply_events(self, profile, day, minute, advance):
        cursor = (profile["id"], day.toordinal() * 1440 + minute)
        previous = self.event_cursor
        self.event_cursor = cursor
        # Arming, scrubbing, editing and restarting never replay past scenes.
        if not advance or previous is None or previous[0] != cursor[0] or not 0 < cursor[1] - previous[1] <= 2:
            return
        for device in self.devices:
            if device["kind"] != "scene" or not device["target"]:
                continue
            row = profile["rows"][device["entity"]]
            if not row["use"]:
                continue
            jitter = self.data["jitter"] if self.data["random"][device["entity"]] else 0
            # Include yesterday for the midnight tick.
            for offset in (-1, 0):
                event_day = date.fromordinal(day.toordinal() + offset)
                for at in scene_markers(row, device["entity"], event_day, self.data["seed"], jitter):
                    stamp = event_day.toordinal() * 1440 + at
                    if not previous[1] < stamp <= cursor[1]:
                        continue
                    key = f"{profile['id']}|{device['entity']}|{stamp}"
                    if key in self.data["fired_events"]:
                        continue
                    current = self.hass.states.get(device["target"])
                    if current is None or current.state == "unavailable":
                        self.errors.append(f"Scene unavailable: {device['target']}")
                        continue
                    # Persist the claim before the call: no duplicate activation after an error.
                    self.data["fired_events"][key] = stamp
                    self.data["fired_events"] = {k: v for k, v in self.data["fired_events"].items() if v >= stamp - 14 * 1440}
                    await self.store.async_save(copy.deepcopy(self.data))
                    try:
                        await self.hass.services.async_call("scene", "turn_on", {"entity_id": device["target"]}, blocking=False)
                    except Exception as err:
                        self.errors.append(f"Scene {device['name']}: {err}")

    async def command(self, call):
        async with self.lock:
            prior = (self.data, self.playing, copy.deepcopy(self.requests), copy.deepcopy(self.restore), self.event_cursor)
            self.data = copy.deepcopy(self.data)
            try:
                await self.execute(dict(call.data))
            except Exception as err:
                self.data, self.playing, self.requests, self.restore, self.event_cursor = prior
                self.cache.clear()
                if isinstance(err, ValueError):
                    raise HomeAssistantError(str(err)) from err
                raise

    def populate_model(self, config, metadata, source_plan=None, replace=True):
        memory = self.data["device_memory"]
        for device in self.devices:
            memory[device["entity"]] = copy.deepcopy(device)
        if not replace:
            metadata = {**metadata, "devices":[*self.devices,*metadata.get("devices",[])]}
        devices, renderer, lookup, report = import_bindings(config, metadata, list(memory.values()), self.hass.states)
        devices = self.validate_catalog(devices)
        previous_rows = {p["id"]:set(p["rows"]) for p in self.data["profiles"]}
        key = hashlib.sha256((config["path"].rstrip("/")+"/"+config["objfile"]).encode()).hexdigest()[:16]
        first = key not in self.data["imported_models"]
        if first:
            self.data["imported_models"] = [*self.data["imported_models"],key][-32:]
        self.data["devices"] = devices
        for device in devices:
            entity = device["entity"]
            self.data["watts"].setdefault(entity,device["watts"])
            self.data["random"].setdefault(entity,False)
            for profile in self.data["profiles"]:
                profile["rows"].setdefault(entity,self.fresh_row(device))
                # The built-in demo metadata supplies its example time blocks.
                if entity not in previous_rows.get(profile["id"],set()) and device.get("slots"):
                    mask = ZERO
                    for start,end in device["slots"]:
                        if not 0 <= int(start) <= int(end) <= 96:
                            raise ValueError("Invalid imported demo time blocks")
                        for slot in range(int(start),int(end)):
                            mask = put(mask,slot,True)
                    profile["rows"][entity]["days"] = [mask]*7
        copied = 0
        if source_plan is not None:
            if not isinstance(source_plan,dict) or not isinstance(source_plan.get("profiles",[]),list):
                raise ValueError("Imported schedules must contain a profiles list")
            if any(not isinstance(source_plan.get(k,{}),dict) for k in ("watts","random")):
                raise ValueError("Imported wattages and variation flags must be objects")
            if len(source_plan.get("profiles",[])) > 12:
                raise ValueError("Maximum of 12 imported schedules")
            for source_profile in source_plan.get("profiles",[]):
                pid = source_profile.get("id") if isinstance(source_profile,dict) else None
                if not isinstance(pid,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",pid):
                    raise ValueError("Invalid imported schedule ID")
                profile = next((p for p in self.data["profiles"] if p["id"]==pid),None)
                if profile is None:
                    if len(self.data["profiles"]) >= 12:
                        raise ValueError("Maximum of 12 schedules")
                    profile = self.fresh_profile(pid,"Imported schedule")
                    self.data["profiles"].append(profile)
                if first:
                    for name in ("name","condition_entity","condition_state","scene"):
                        value = str(source_profile.get(name,profile[name])).strip()
                        if len(value)>100 or (name=="name" and not value):
                            raise ValueError("Invalid imported schedule name/condition")
                        if name in ("condition_entity","scene") and value and not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+",value):
                            raise ValueError("Imported conditions must use entity IDs")
                        if name=="scene" and value and not value.startswith("scene."):
                            raise ValueError("Scene on activation must use a scene ID")
                        profile[name] = value
                rows = source_profile.get("rows",{})
                if not isinstance(rows,dict):
                    raise ValueError("Imported schedule rows must be an object")
                for source,row in rows.items():
                    entity = lookup.get(source)
                    if entity is None or entity in previous_rows.get(pid,set()):
                        continue
                    if not isinstance(row,dict) or not isinstance(row.get("days"),list) or len(row["days"])!=7 or any(not isinstance(m,str) or not re.fullmatch(r"[0-9a-fA-F]{24}",m) for m in row["days"]):
                        raise ValueError("Imported schedules need seven 96-block masks per row")
                    profile["rows"][entity].update(use=boolean(row.get("use",False)),days=[m.lower() for m in row["days"]])
                    copied += 1
            for source,entity in lookup.items():
                if entity in set().union(*previous_rows.values()):
                    continue
                if source in source_plan.get("watts",{}):
                    self.data["watts"][entity] = number(source_plan["watts"][source],0,20000,"Imported watts")
                if source in source_plan.get("random",{}):
                    self.data["random"][entity] = boolean(source_plan["random"][source])
            if first:
                if source_plan.get("profile") in {p["id"] for p in self.data["profiles"]}:
                    self.data["profile"] = source_plan["profile"]
                if "date" in source_plan:
                    self.data["date"] = date.fromisoformat(source_plan["date"]).isoformat()
                if "jitter" in source_plan:
                    self.data["jitter"] = int(number(source_plan["jitter"],0,60,"Imported variation"))
                if "seed" in source_plan:
                    self.data["seed"] = int(source_plan["seed"])
        self.data["renderer"] = renderer
        self.data["model_imported"] = True
        self.data["renderer_revision"] += 1
        self.data["hidden_devices"] = [e for e in self.data["hidden_devices"] if e in self.ids]
        if replace:
            self.data.update(physical=False,clock=False,model_imported=True)
            self.playing = False
            self.requests.clear()
            self.restore.clear()
            self.event_cursor = None
            self.data["shown_types"] = ["light"] if any(d["kind"]=="light" for d in devices) else [devices[0]["kind"]]
        report["schedule_rows_copied"] = copied
        self.data["last_import"] = report

    async def execute(self, data):
        op = data.get("op")
        presentation_only = op in ("renderer", "import_model", "view", "device", "add_device", "remove_device")
        if op in ("renderer","import_model"):
            revision = self.data["renderer_revision"]
            expected = data.get("expected_revision", revision)
            if type(expected) is not int or expected != revision:
                raise HomeAssistantError("Model changed in another card. Discard the draft and edit the current model.")
            if op == "import_model":
                config, metadata = parse_source(data.get("source",data.get("config")))
                if data.get("demo"):
                    if config["path"] not in (ASSET_PATH,"/local/home-scheduler/") or config["objfile"]!="demo-home.glb":
                        raise ValueError("Use the supplied demo configuration")
                    metadata = {"devices":DEFAULT_DEVICES}
                self.populate_model(config,metadata,data.get("source_plan",metadata.get("source_plan")))
            else:
                self.populate_model(validate_model(data.get("config")),{},replace=False)
        elif op == "view":
            if "shown_types" in data:
                values = data["shown_types"]
                if not isinstance(values, list) or any(v not in KINDS for v in values):
                    raise ValueError("Choose supported device types")
                self.data["shown_types"] = list(dict.fromkeys(values))
            if "hidden_devices" in data:
                values = data["hidden_devices"]
                if not isinstance(values, list) or any(v not in self.ids for v in values):
                    raise ValueError("Choose devices in this scheduler")
                self.data["hidden_devices"] = list(dict.fromkeys(values))
        elif op == "add_device":
            kind, name = data.get("kind"), str(data.get("name", "")).strip()
            if kind not in KINDS:
                raise ValueError("Choose a supported device type")
            identity = hashlib.sha256(f"{name}|{time.time_ns()}".encode()).hexdigest()[:10]
            device = normalize_device({"kind": kind, "name": name, "entity": f"{kind}.hs_user_{identity}",
                                       "target": data.get("target", "")})
            self.data["devices"] = self.validate_catalog([*self.devices, device])
            self.data["watts"][device["entity"]] = device["watts"]
            self.data["random"][device["entity"]] = False
            if kind not in self.data["shown_types"]:
                self.data["shown_types"].append(kind)
            for profile in self.data["profiles"]:
                profile["rows"][device["entity"]] = self.fresh_row(device)
        elif op == "device":
            device = self.device(data.get("entity"))
            if "target" in data:
                device["target"] = validate_target(device["kind"], data["target"])
            if "name" in data:
                device["name"] = str(data["name"]).strip()
            if "travel_seconds" in data:
                device["travel_seconds"] = data["travel_seconds"]
            if "effects" in data:
                device["effects"] = data["effects"]
            self.data["devices"] = self.validate_catalog(self.devices)
            self.requests.pop(device["entity"], None)
            self.restore.pop(device["entity"], None)
        elif op == "remove_device":
            entity = self.device(data.get("entity"))["entity"]
            for d in self.devices:
                if entity in d.get("effects", {}):
                    raise ValueError("Remove this device from preview scene effects first")
            self.data["devices"] = self.validate_catalog([d for d in self.devices if d["entity"] != entity])
            for profile in self.data["profiles"]:
                profile["rows"].pop(entity, None)
            self.data["watts"].pop(entity, None)
            self.data["random"].pop(entity, None)
            self.data["hidden_devices"] = [e for e in self.data["hidden_devices"] if e != entity]
            self.requests.pop(entity, None)
            self.restore.pop(entity, None)
        else:
            profile = self.profile(data.get("profile"))
            entity = data.get("entity")
            if entity is not None:
                device = self.device(entity)
            if op in ("cell", "range", "row") and entity is None:
                raise ValueError("Choose a device")
            if op in ("cell", "range"):
                day = int(data["day"])
                start, end = sorted((int(data.get("start", data.get("slot", -1))), int(data.get("end", data.get("slot", -1)))))
                if not 0 <= day < 7 or not 0 <= start <= end < 96:
                    raise ValueError("Invalid day or time range")
                value = boolean(data["value"])
                row = profile["rows"][entity]
                for slot in range(start, end + 1):
                    row["days"][day] = put(row["days"][day], slot, value)
                if value:
                    row["use"] = True
            elif op == "fill":
                day, value = int(data["day"]), boolean(data["value"])
                selected = data.get("entities", [entity] if entity is not None else sorted(self.ids))
                if not 0 <= day < 7 or not isinstance(selected, list) or any(e not in self.ids for e in selected):
                    raise ValueError("Invalid day or device selection")
                for e in selected:
                    if value and self.device(e)["kind"] == "scene":
                        continue
                    row = profile["rows"][e]
                    row["days"][day] = "f" * 24 if value else ZERO
                    if value:
                        row["use"] = True
            elif op == "row":
                row = profile["rows"][entity]
                if "use" in data:
                    row["use"] = boolean(data["use"])
                    if not row["use"]:
                        self.restore.pop(entity, None)
                        self.requests.pop(entity, None)
                if "watts" in data:
                    if device["kind"] == "scene":
                        raise ValueError("Scenes have no independent wattage")
                    self.data["watts"][entity] = number(data["watts"], 0, 20000, "Watts")
                if "random" in data:
                    self.data["random"][entity] = boolean(data["random"])
                if "outside" in data:
                    row["outside"] = validate_outside(data["outside"])
                if "off_position" in data:
                    row["off_position"] = number(data["off_position"], 0, 100, "Outside position")
                if "on" in data:
                    row["on"] = validate_on(device["kind"], {**row["on"], **data["on"]})
            elif op == "copy_day":
                day = int(data["day"])
                if not 0 <= day < 7:
                    raise ValueError("Invalid day")
                for row in profile["rows"].values():
                    row["days"] = [row["days"][day]] * 7
            elif op == "profile":
                for key in ("name", "condition_entity", "condition_state", "scene"):
                    if key not in data:
                        continue
                    value = str(data[key]).strip()
                    if len(value) > 100 or (key == "name" and not value):
                        raise ValueError("Schedule values must be at most 100 characters; name is required")
                    if key in ("scene", "condition_entity") and value and not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value):
                        raise ValueError("Use an entity ID")
                    if key == "scene" and value and not value.startswith("scene."):
                        raise ValueError("Use a scene entity ID")
                    profile[key] = value
            elif op == "clone":
                if len(self.data["profiles"]) >= 12:
                    raise ValueError("Maximum of 12 schedules")
                new = copy.deepcopy(profile)
                new["id"] = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]
                new["name"] = (str(data.get("name", profile["name"] + " copy")).strip() or "Schedule")[:100]
                new["condition_entity"] = new["condition_state"] = new["scene"] = ""
                self.data["profiles"].append(new)
                self.data["profile"] = new["id"]
            elif op == "play":
                if self.data["clock"]:
                    raise ValueError("Turn off Follow clock before playback")
                self.playing = not self.playing
            elif op == "settings":
                if "profile" in data:
                    self.profile(data["profile"])
                    self.data["profile"] = data["profile"]
                    self.restore.clear()
                if "date" in data:
                    self.data["date"] = date.fromisoformat(str(data["date"])).isoformat()
                for key in ("physical", "clock", "auto", "repeat"):
                    if key in data:
                        self.data[key] = boolean(data[key])
                if "physical" in data or "clock" in data:
                    self.requests.clear()
                    self.restore.clear()
                    self.event_cursor = None
                if self.data["clock"]:
                    self.playing = False
                if "minute" in data:
                    self.data["minute"] = int(number(data["minute"], 0, 1439, "Time"))
                if "jitter" in data:
                    self.data["jitter"] = int(number(data["jitter"], 0, 60, "Variation minutes"))
                if "seed" in data:
                    self.data["seed"] = int(data["seed"])
                if "speed" in data:
                    speed = float(data["speed"])
                    if speed not in (0.25, 0.5, 1, 2, 4):
                        raise ValueError("Invalid speed")
                    self.data["speed"] = speed
            else:
                raise ValueError("Unknown operation")
        self.cache.clear()
        self.last_clock = None
        if presentation_only or (op == "settings" and ("physical" in data or "clock" in data)):
            await self.store.async_save(copy.deepcopy(self.data))
        else:
            self.store.async_delay_save(lambda: copy.deepcopy(self.data), 1)
        await self.apply(control=not presentation_only)

    async def run(self):
        while not self.stopping:
            try:
                async with self.lock:
                    if self.playing:
                        minute = self.data["minute"] + 5
                        if minute >= 1440:
                            self.data["minute"] = 0 if self.data["repeat"] else 1435
                            self.playing = self.data["repeat"]
                        else:
                            self.data["minute"] = minute
                        await self.apply(advance=True)
                    elif self.data["clock"]:
                        profile, day, minute = self.context()
                        key = (profile["id"], day.isoformat(), minute)
                        if key != self.last_clock:
                            await self.apply(advance=True)
                            self.last_clock = key
                    delay = (5 / 60) / self.data["speed"] if self.playing else 1
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            except Exception:
                LOG.exception("Home scheduler tick failed")
                await asyncio.sleep(1)

    async def start(self, _event=None):
        if self.task is not None:
            return
        async with self.lock:
            await self.apply()
        self.task = self.hass.async_create_background_task(self.run(), DOMAIN)

    async def stop(self, _event=None):
        self.stopping = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await self.store.async_save(copy.deepcopy(self.data))


async def async_setup(hass, config):
    """Keep YAML compatible; the config entry owns the running scheduler."""
    runtime = hass.data.setdefault(DOMAIN,{})
    if DOMAIN in config:
        runtime["configured_devices"] = (config[DOMAIN] or {}).get("devices")
        hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={"source":config_entries.SOURCE_IMPORT}, data={}))
    return True


async def async_setup_entry(hass, entry):
    """Serve self-contained HACS assets and start the single scheduler."""
    runtime = hass.data.setdefault(DOMAIN,{})
    if runtime.get("scheduler"):
        return True
    if not runtime.get("assets_registered"):
        folder=Path(__file__).parent/"frontend"
        preset_index=Path(hass.config.path("www/home-scheduler/models.json"))
        has_presets=await hass.async_add_executor_job(preset_index.is_file)
        paths=[]
        if has_presets:
            runtime["model_presets_url"]=ASSET_PATH+"user-models.json"
            paths.append(StaticPathConfig(runtime["model_presets_url"],str(preset_index),False))
        paths.append(StaticPathConfig(ASSET_PATH.rstrip("/"),str(folder),True))
        await hass.http.async_register_static_paths(paths)
        runtime["assets_registered"]=True
    try:
        scheduler = Scheduler(hass,runtime.get("configured_devices"),runtime.get("model_presets_url"))
        await scheduler.load()
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err
    runtime["scheduler"] = scheduler
    async_register_admin_service(hass, DOMAIN, "command", scheduler.command,
        schema=vol.Schema({vol.Required("op"): str}, extra=vol.ALLOW_EXTRA))
    module_url=ASSET_PATH+"home-scheduler-card.js?v="+VERSION
    frontend.add_extra_js_url(hass,module_url)
    runtime["module_url"]=module_url
    await scheduler.apply(control=False)
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, scheduler.stop))
    if hass.is_running:
        await scheduler.start()
    else:
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, scheduler.start))
    return True


async def async_unload_entry(hass, entry):
    """Stop scheduling; preserve saved plans and leave real devices as they are."""
    runtime=hass.data.get(DOMAIN,{})
    scheduler=runtime.pop("scheduler",None)
    if scheduler:
        await scheduler.stop()
    hass.services.async_remove(DOMAIN,"command")
    if url:=runtime.pop("module_url",None):
        frontend.remove_extra_js_url(hass,url)
    for entity in ("sensor.home_scheduler","sensor.home_scheduler_frame"):
        hass.states.async_remove(entity)
    return True
