"""Device validation and desired states. No Home Assistant or device calls here."""
import copy
import math
import re

KINDS = ("light", "switch", "fan", "cover", "scene")
ENTITY_RE = re.compile(r"^(light|switch|fan|cover|scene)\.[a-z0-9_]+$")
TARGET_DOMAINS = {"light": {"light", "switch"}, "switch": {"switch"},
                  "fan": {"fan", "switch"}, "cover": {"cover"}, "scene": {"scene"}}
DEFAULT_ON = {"light": {"brightness": 100, "color": "#ffb830"}, "switch": {},
              "fan": {"percentage": 50}, "cover": {"position": 100}, "scene": {}}


def number(value, low, high, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}")
    return value


def normalize_device(value):
    if not isinstance(value, dict) or not ENTITY_RE.fullmatch(str(value.get("entity", ""))):
        raise ValueError("Choose a light, switch, fan, cover or scene entity ID")
    device = copy.deepcopy(value)
    kind = device.get("kind", device["entity"].split(".")[0])
    if kind not in KINDS:
        raise ValueError("Unsupported device type")
    name = str(device.get("name", "")).strip()
    if not name or len(name) > 100:
        raise ValueError("Device needs a name of at most 100 characters")
    device.update(kind=kind, name=name)
    device["target"] = validate_target(kind, device.get("target", ""))
    device["watts"] = number(device.get("watts", 0), 0, 20000, "Watts")
    device["travel_seconds"] = number(device.get("travel_seconds", 12), 1, 600, "Cover travel seconds")
    device["on"] = validate_on(kind, device.get("on", {}))
    device["off_position"] = number(device.get("off_position", 0), 0, 100, "Outside position")
    device["outside"] = validate_outside(device.get("outside", "off"))
    return device


def validate_target(kind, value):
    value = str(value).strip()
    if value and (not ENTITY_RE.fullmatch(value) or value.split(".")[0] not in TARGET_DOMAINS[kind]):
        raise ValueError(f"Target for {kind} must be in: {', '.join(sorted(TARGET_DOMAINS[kind]))}")
    return value


def validate_outside(value):
    if value not in ("off", "unchanged", "restore"):
        raise ValueError("Outside periods: off/closed, leave unchanged, or restore previous")
    return value


def validate_on(kind, value):
    if not isinstance(value, dict):
        raise ValueError("Inside-period settings must be an object")
    result = copy.deepcopy(DEFAULT_ON[kind])
    if set(value) - set(result):
        raise ValueError(f"Unsupported inside-period setting for {kind}")
    result.update(value)
    if kind == "light":
        result["brightness"] = number(result["brightness"], 1, 100, "Brightness")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(result["color"])):
            raise ValueError("Choose a six-digit color")
    elif kind == "fan":
        result["percentage"] = number(result["percentage"], 1, 100, "Fan speed")
    elif kind == "cover":
        result["position"] = number(result["position"], 0, 100, "Inside position")
    return result


def state_for(device, row, active):
    kind = device["kind"]
    settings = row.get("on", device["on"])
    attrs = {"friendly_name": device["name"]}
    if kind == "light":
        color = settings["color"].lstrip("#")
        attrs.update(brightness=round(settings["brightness"] * 255 / 100), color_mode="rgb",
                     rgb_color=[int(color[i:i+2], 16) for i in (0, 2, 4)])
    elif kind == "fan":
        attrs["percentage"] = settings["percentage"] if active else 0
    elif kind == "cover":
        pos = settings["position"] if active else row.get("off_position", device["off_position"])
        attrs.update(current_position=pos, device_class=device.get("device_class", "blind"))
        return {"state": "closed" if pos == 0 else "open", "attributes": attrs}
    return {"state": "on" if active else "off", "attributes": attrs}


def effect_state(device, effect, old):
    """Explicit virtual scene effects; never infer or execute a real scene."""
    kind = device["kind"]
    effect = copy.deepcopy(effect)
    if not isinstance(effect, dict):
        raise ValueError("Scene effect must be an object")
    if kind == "scene":
        raise ValueError("A preview scene cannot activate another scene")
    state = effect.pop("state", "open" if kind == "cover" else "on")
    if state not in (("open", "closed") if kind == "cover" else ("on", "off")):
        raise ValueError("Invalid preview scene state")
    if kind == "cover":
        pos = number(effect.pop("position", 100 if state == "open" else 0), 0, 100, "Scene position")
        settings = {"position": pos}
        active = True
    else:
        active = state == "on"
        settings = validate_on(kind, effect)
        effect.clear()
    if effect:
        raise ValueError("Unsupported preview scene effect")
    result = state_for(device, {"on": settings}, active)
    result["attributes"] = {**old.get("attributes", {}), **result["attributes"]}
    return result
