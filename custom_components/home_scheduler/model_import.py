"""Import floor3dx bindings without inspecting or operating physical devices."""
import copy
import hashlib
import json
import re

from .devices import ENTITY_RE, KINDS, normalize_device

REF_KEYS = {"entity", "color_entity", "top_entity", "state_entity"}
MAX_DEVICES = 128


def validate_model(config):
    if not isinstance(config, dict) or config.get("type") not in ("custom:floor3dx-card", "custom:floor3d-card"):
        raise ValueError("Choose a floor3dx model configuration")
    if any(not isinstance(config.get(k), str) or not config[k].strip() for k in ("path", "objfile")):
        raise ValueError("Model path and file are required")
    if not isinstance(config.get("entities", []), list):
        raise ValueError("Model entities must be a list")
    encoded = json.dumps(config, allow_nan=False)
    if len(encoded.encode()) > 262144:
        raise ValueError("Model configuration exceeds 256 KiB")
    return json.loads(encoded)


def parse_source(source):
    if isinstance(source, str):
        if len(source.encode()) > 524288:
            raise ValueError("Import configuration exceeds 512 KiB")
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            import yaml
            class ModelLoader(yaml.SafeLoader):
                pass
            # Keep floor3dx's yes/no and HA's on/off strings intact.
            ModelLoader.yaml_implicit_resolvers = {
                k:[v for v in values if v[0] != "tag:yaml.org,2002:bool"]
                for k, values in yaml.SafeLoader.yaml_implicit_resolvers.items()}
            ModelLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"), list("tTfF"))
            try:
                source = yaml.load(source, Loader=ModelLoader)
            except yaml.YAMLError as error:
                raise ValueError("Use JSON or plain YAML; include/secret tags are not supported") from error
    try:
        if len(json.dumps(source, allow_nan=False).encode()) > 524288:
            raise ValueError("Import configuration exceeds 512 KiB")
    except (TypeError, ValueError) as error:
        raise ValueError("Model configuration must contain plain JSON/YAML values") from error
    if not isinstance(source, (dict, list)):
        raise ValueError("Choose a model configuration, not the GLB/OBJ geometry file")
    metadata = source if isinstance(source, dict) and "renderer" in source else {}
    root = metadata.get("renderer", source)
    found = []
    def visit(value):
        if isinstance(value, dict):
            if value.get("type") in ("custom:floor3dx-card", "custom:floor3d-card"):
                found.append(value)
                return
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(root)
    if len(found) != 1:
        raise ValueError("Import one floor3dx card configuration; use the model selector for cards in a dashboard")
    return validate_model(found[0]), metadata


def import_bindings(config, metadata, remembered, states):
    """Return devices, rewritten renderer, source lookup, and a short report."""
    aliases = metadata.get("aliases", {})
    if not isinstance(aliases, dict) or len(aliases) > MAX_DEVICES:
        raise ValueError("Model aliases must be an entity-ID object")
    if any(not isinstance(k,str) or not isinstance(v,str) or not ENTITY_RE.fullmatch(k) or not ENTITY_RE.fullmatch(v)
           for k,v in aliases.items()):
        raise ValueError("Model aliases must link supported device entity IDs")
    def canonical(entity):
        seen = set()
        while entity in aliases:
            if entity in seen:
                raise ValueError("Model aliases contain a cycle")
            seen.add(entity)
            entity = aliases[entity]
        return entity
    for entity in aliases:
        canonical(entity)
    specs = metadata.get("devices", [])
    if not isinstance(specs, list) or len(specs) > MAX_DEVICES:
        raise ValueError("Choose at most 128 imported devices")
    hints = {}
    for spec in specs:
        if not isinstance(spec, dict) or not ENTITY_RE.fullmatch(str(spec.get("entity", ""))):
            raise ValueError("Imported device metadata needs a supported entity ID")
        hints[canonical(spec["entity"])] = spec
    references, kinds = [], {}
    def add(entity, kind=None):
        if not isinstance(entity,str) or not ENTITY_RE.fullmatch(entity):
            return
        source = canonical(entity)
        references.append((entity, source))
        domain = source.split(".")[0]
        if source not in kinds or kind == "light":
            kinds[source] = kind or domain
    for source, spec in hints.items():
        add(source, spec.get("kind", source.split(".")[0]))
    readonly, excluded = set(), set()
    for entry in config.get("entities", []):
        entry = {"entity":entry} if isinstance(entry,str) else entry
        if not isinstance(entry,dict):
            raise ValueError("Each model entity must be an entity ID or object")
        main = entry.get("entity")
        if isinstance(main,str) and main.startswith("climate."):
            excluded.add(main)
        elif isinstance(main,str) and not ENTITY_RE.fullmatch(main):
            readonly.add(main)
        semantic_light = entry.get("type3d") == "light" or (
            isinstance(main,str) and main.split(".")[0] in ("light","switch") and
            entry.get("type3d") == "color" and isinstance(entry.get("colorcondition"),list) and
            any(isinstance(c,dict) and c.get("color")=="entity_color" for c in entry["colorcondition"]))
        add(main, "light" if semantic_light else None)
        add(entry.get("color_entity"), "light")
        shade = entry.get("shade", {})
        if isinstance(shade,dict):
            add(shade.get("top_entity"))
    # Metadata determines semantic types for switches used as lamps or fans.
    for source, spec in hints.items():
        if "kind" in spec:
            kinds[source] = spec["kind"]
    if not kinds:
        raise ValueError("The model configuration contains no lights, switches, fans, covers, or scenes")
    if len(kinds) > MAX_DEVICES:
        raise ValueError("This model has more than 128 schedulable devices")
    known = {}
    for device in remembered:
        for source in [device["entity"], device.get("target"), *device.get("source_entities", [])]:
            if source:
                known[source] = device
    devices, lookup = [], {}
    for source, kind in kinds.items():
        if kind not in KINDS:
            raise ValueError("Thermostats are not schedulable")
        spec = hints.get(source, {})
        old = known.get(source)
        if old and kind == "switch" and source not in hints and old["kind"] in ("light", "fan"):
            kind = old["kind"]
        if old and old["kind"] != kind:
            old = None
        current = states.get(source)
        attrs = current.attributes if current else {}
        identity = old["entity"] if old else f"{kind}.hs_model_{hashlib.sha256(source.encode()).hexdigest()[:12]}"
        base = copy.deepcopy(old) if old else {"use":False}
        if not old:
            base.update({k:v for k,v in spec.items() if k not in ("entity", "effects")})
            base["name"] = str(spec.get("name") or attrs.get("friendly_name") or source)[:100]
            base["target"] = spec.get("target", source if current else "")
            if kind == "cover":
                base["device_class"] = spec.get("device_class", attrs.get("device_class", "blind"))
        base.update(entity=identity, kind=kind)
        base["source_entities"] = list(dict.fromkeys([*base.get("source_entities", []), source,
            *(original for original, resolved in references if resolved == source)]))
        if len(base["source_entities"]) > 256:
            raise ValueError("Too many source aliases for one device")
        device = normalize_device(base)
        duplicate = next((d for d in devices if d["entity"] == identity),None)
        if duplicate:
            duplicate["source_entities"] = list(dict.fromkeys([*duplicate["source_entities"],*device["source_entities"]]))
        else:
            devices.append(device)
        lookup[source] = identity
        for original in device["source_entities"]:
            lookup[original] = identity
    catalog = {d["entity"]:d for d in devices}
    for source, spec in hints.items():
        device = catalog[lookup[source]]
        if "effects" in spec:
            if not isinstance(spec["effects"],dict):
                raise ValueError("Scene effects must be an object")
            effects = {lookup.get(canonical(e),e):v for e,v in spec["effects"].items()}
            if any(e not in catalog for e in effects):
                raise ValueError("Preview scene effects must name imported devices")
            device["effects"] = effects
    for device in devices:
        if device["kind"] == "scene":
            device["effects"] = {e:v for e,v in device.get("effects",{}).items() if e in catalog}
    def rewrite(value):
        if isinstance(value,list):
            return [rewrite(v) for v in value]
        if isinstance(value,dict):
            return {k:lookup.get(v,v) if k in REF_KEYS and isinstance(v,str) else rewrite(v) for k,v in value.items()}
        return value
    rewritten = rewrite(config)
    # Shorthand entries are references, too.
    rewritten["entities"] = [lookup.get(e,e) if isinstance(e,str) else e for e in rewritten.get("entities",[])]
    report = {"name":config.get("name") or config["objfile"], "devices":len(devices),
              "kinds":{k:sum(d["kind"]==k for d in devices) for k in KINDS},
              "readonly":len(readonly), "thermostats":len(excluded), "aliases":len(aliases)}
    return devices, rewritten, lookup, report
