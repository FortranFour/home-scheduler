"""Deterministic virtual device states, scene events, and daily energy estimates."""
import copy
import hashlib
from datetime import timedelta

from .devices import effect_state, state_for
from .schedule import bits, effective


def scene_markers(row, entity, day, seed, jitter):
    events = []
    # Adjacent days permit a randomized marker to cross midnight consistently.
    for delta in (-1, 0, 1):
        origin = day + timedelta(days=delta)
        for slot, checked in enumerate(bits(row["days"][origin.weekday()])):
            if not checked:
                continue
            shift = 0
            if jitter:
                digest = hashlib.sha256(f"event|{seed}|{entity}|{origin.isoformat()}|{slot}".encode()).digest()
                shift = int.from_bytes(digest[:4], "big") % (2 * jitter + 1) - jitter
            minute = delta * 1440 + slot * 15 + shift
            if 0 <= minute < 1440:
                events.append(minute)
    return sorted(set(events))


def spans_for(row, entity, day, seed, jitter):
    return effective(row["days"], entity, day - timedelta(days=day.weekday()), day.weekday(), seed, jitter)


def build_timeline(devices, profile, data, day):
    """Look back one full weekly cycle; keep preview independent of HA states."""
    catalog = {d["entity"]: d for d in devices}
    rows, seed = profile["rows"], data["seed"]
    states = {e: state_for(d, rows[e], False) for e, d in catalog.items() if d["kind"] != "scene"}
    activation = catalog.get(profile.get("scene"))
    events, markers = [], []
    if activation and activation["kind"] == "scene":
        # Reapply the profile baseline at the start of this preview day.
        # Previous-day scene events must not erase a newly selected baseline.
        events.append((0, 2, activation["entity"], "scene"))
    first = day - timedelta(days=8)
    for delta in range(-8, 1):
        current = day + timedelta(days=delta)
        offset = delta * 1440
        for entity, device in catalog.items():
            row = rows[entity]
            if not row["use"]:
                continue
            jitter = data["jitter"] if data["random"].get(entity) else 0
            if device["kind"] == "scene":
                for minute in scene_markers(row, entity, current, seed, jitter):
                    events.append((offset + minute, 2, entity, "scene"))
                    if delta == 0:
                        markers.append({"entity": entity, "name": device["name"], "minute": minute})
                continue
            spans = spans_for(row, entity, current, seed, jitter)
            previous = spans_for(row, entity, current - timedelta(days=1), seed, jitter)
            following = spans_for(row, entity, current + timedelta(days=1), seed, jitter)
            for start, end in spans:
                if start > 0 or current == first or not previous or previous[-1][1] != 1440:
                    events.append((offset + start, 1, entity, "start"))
                if end < 1440 or not following or following[0][0] != 0:
                    events.append((offset + end, 0, entity, "end"))
    trace = {e: [] for e in states}
    cover_moves = {e: [] for e, d in catalog.items() if d["kind"] == "cover"}
    snapshots = {}
    started = False
    for minute, _, entity, action in sorted(events):
        if minute >= 1440:
            break
        if minute >= 0 and not started:
            for e in trace:
                trace[e].append((0, copy.deepcopy(states[e])))
            started = True
        device, row = catalog[entity], rows[entity]
        changes = {}
        if action == "scene":
            for affected, effect in device.get("effects", {}).items():
                changes[affected] = effect_state(catalog[affected], effect, states[affected])
        elif action == "start":
            snapshots[entity] = copy.deepcopy(states[entity])
            changes[entity] = state_for(device, row, True)
        elif row["outside"] == "off":
            changes[entity] = state_for(device, row, False)
        elif row["outside"] == "restore" and entity in snapshots:
            changes[entity] = snapshots.pop(entity)
        for e, value in changes.items():
            if states[e] == value:
                continue
            if e in cover_moves:
                difference = abs(value["attributes"]["current_position"] -
                                 states[e]["attributes"]["current_position"]) / 100
                seconds = catalog[e]["travel_seconds"] * difference
                if seconds:
                    cover_moves[e].append((minute, seconds))
            states[e] = value
            if minute >= 0:
                trace[e].append((minute, copy.deepcopy(value)))
    if not started:
        for e in trace:
            trace[e].append((0, copy.deepcopy(states[e])))
    energy = {}
    movements = {}
    for entity, device in catalog.items():
        if device["kind"] == "scene":
            energy[entity] = {"minutes": 0, "kwh": None, "events": sum(m["entity"] == entity for m in markers)}
            continue
        points = trace[entity]
        minutes, wh = 0, 0.0
        watts = data["watts"][entity]
        if device["kind"] == "cover":
            moves = []
            for t, duration in cover_moves[entity]:
                start = max(0, t * 60)
                end = min(1440 * 60, t * 60 + duration)
                seconds = max(0, end - start)
                if seconds:
                    wh += watts * seconds / 3600
                    moves.append({"minute": start / 60, "seconds": seconds})
            movements[entity] = moves
        else:
            for i, (t, value) in enumerate(points):
                end = points[i + 1][0] if i + 1 < len(points) else 1440
                if value["state"] == "on":
                    minutes += end - t
            wh = watts * minutes / 60
        energy[entity] = {"minutes": minutes, "kwh": round(wh / 1000, 6), "events": 0}
    return {"trace": trace, "energy": energy, "events": sorted(markers, key=lambda x: (x["minute"], x["entity"])), "movements": movements}


def frame_at(timeline, devices, minute, day):
    states = {}
    for entity, points in timeline["trace"].items():
        states[entity] = copy.deepcopy(next(value for t, value in reversed(points) if t <= minute))
    for device in devices:
        if device["kind"] != "scene":
            continue
        past = [m for m in timeline["events"] if m["entity"] == device["entity"] and m["minute"] <= minute]
        stamp = f"{day.isoformat()}T{past[-1]['minute']//60:02}:{past[-1]['minute']%60:02}:00" if past else "unknown"
        states[device["entity"]] = {"state": stamp, "attributes": {"friendly_name": device["name"], "last_triggered": stamp if past else None}}
    return states
