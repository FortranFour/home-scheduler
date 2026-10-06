"""Duration-based observations and weekday consensus; no Home Assistant calls."""
from datetime import date, datetime, timedelta

from .schedule import ZERO, bits, put

LEARNING_KINDS = ("light", "switch", "fan")
RETENTION_DAYS = 56
MIN_SAMPLES = 3
MIN_COVERAGE = 810  # At least 90% of a 900-second block must be known.


def empty_bucket():
    return {"known": [0.0] * 96, "on": [0.0] * 96, "blocked": [0.0] * 96}


def add_interval(records, target, start, end, state, zone, *, source="live",
                 mode="", blocked=False):
    """Split an observed UTC interval into local 15-minute cells.

    Repeated DST clock times are omitted. Missing spring-forward cells have no
    observations. Unknown states never become OFF, and controlled time records
    an exclusion even if the device is currently unavailable.
    """
    if end <= start or (mode is None and not blocked) or (state not in ("on", "off") and not blocked):
        return
    stamp = start
    while stamp < end:
        local = datetime.fromtimestamp(stamp, zone)
        seconds = (local.minute % 15) * 60 + local.second + local.microsecond / 1e6
        stop = min(end, stamp + 900 - seconds)
        ambiguous = local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset()
        if not ambiguous:
            day = records.setdefault(target, {}).setdefault(local.date().isoformat(), {})
            slot, duration = local.hour * 4 + local.minute // 15, stop - stamp
            if blocked:
                day["excluded"] = put(day.get("excluded", ZERO), slot, True)
            if mode is None:
                stamp = stop
                continue
            modes = day.setdefault(source, {})
            # Discrete household modes only; bound even a misconfigured helper.
            if mode in modes or len(modes) < 16:
                bucket = modes.setdefault(mode, empty_bucket())
                field = "blocked" if blocked else "known"
                bucket[field][slot] = round(bucket[field][slot] + duration, 3)
                if not blocked and state == "on":
                    bucket["on"][slot] = round(bucket["on"][slot] + duration, 3)
        stamp = stop


def prune(records, today):
    # Full rolling days plus today's partial day (at most 57 date buckets).
    cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
    for target in list(records):
        records[target] = {day: values for day, values in records[target].items()
                           if cutoff <= day <= today.isoformat()}
        if not records[target]:
            del records[target]


def completed_slot(day, slot, now):
    """Reject unfinished, missing, or ambiguous local blocks."""
    start = datetime.combine(day, datetime.min.time(), now.tzinfo) + timedelta(minutes=15 * slot)
    end = start + timedelta(minutes=15)
    if start.replace(fold=0).utcoffset() != start.replace(fold=1).utcoffset():
        return False
    if datetime.fromtimestamp(start.timestamp(), now.tzinfo).replace(tzinfo=None) != start.replace(tzinfo=None):
        return False
    return abs(end.timestamp() - start.timestamp() - 900) < .01 and end.timestamp() <= now.timestamp()


def consensus(records, target, base_days, now, *, lookback=42, threshold=60,
              include_history=False, mode_state=""):
    """Each usable date casts one duration-based vote, never one per event.

    Unknown cells retain the base schedule. Evidence counts use one hex digit
    per cell (the eight-week retention window permits at most eight samples).
    """
    samples = [[0] * 96 for _ in range(7)]
    votes = [[0] * 96 for _ in range(7)]
    brief = excluded = 0
    window_start = now - timedelta(days=lookback)
    cutoff = window_start.date()
    for iso, sources in records.get(target, {}).items():
        day = date.fromisoformat(iso)
        if not cutoff <= day <= now.date():
            continue
        selected = []
        for source, modes in sources.items():
            if source not in ("live", "history"):
                continue
            if source == "history" and not include_history:
                continue
            selected.extend(value for mode, value in modes.items()
                            if not mode_state or mode == mode_state)
        excluded_mask = bits(sources.get("excluded", ZERO))
        for slot in range(96):
            slot_start = datetime.combine(day, datetime.min.time(), now.tzinfo) + timedelta(minutes=slot * 15)
            if slot_start.timestamp() < window_start.timestamp():
                continue
            known = sum(b["known"][slot] for b in selected)
            on = sum(b["on"][slot] for b in selected)
            blocked = excluded_mask[slot] or sum(b["blocked"][slot] for b in selected)
            if blocked:
                excluded += 1
            if blocked or not MIN_COVERAGE <= known <= 900.01 or not completed_slot(day, slot, now):
                continue
            samples[day.weekday()][slot] += 1
            votes[day.weekday()][slot] += int(on >= 450)
            brief += int(0 < on < 450)
    days, known_masks = list(base_days), [ZERO] * 7
    for weekday in range(7):
        for slot in range(96):
            count, on_count = samples[weekday][slot], votes[weekday][slot]
            if count >= MIN_SAMPLES:
                known_masks[weekday] = put(known_masks[weekday], slot, True)
                days[weekday] = put(days[weekday], slot, on_count * 100 >= threshold * count)
    return {"days": days, "known": known_masks,
            "samples": ["".join(format(n, "x") for n in row) for row in samples],
            "votes": ["".join(format(n, "x") for n in row) for row in votes],
            "usable_cells": sum(sum(bits(mask)) for mask in known_masks),
            "brief_samples": brief, "excluded_samples": excluded}


def state_segments(states, start, end):
    """Carry only explicitly recorded states forward from their timestamps."""
    events = sorted((state.last_updated.timestamp(), state.state) for state in states)
    result, current, at = [], None, start
    for stamp, value in events:
        if stamp > end:
            break
        if stamp <= start:
            current = value
            continue
        if current is not None and stamp > at:
            result.append((at, stamp, current))
        current, at = value, stamp
    if current is not None and at < end:
        result.append((at, end, current))
    return result


def record_history(records, target, states, start, end, zone, *, mode_states=None):
    """Join the device's state with the household mode at that historical time."""
    modes = [(start, end, "")] if mode_states is None else state_segments(mode_states, start, end)
    for lo, hi, state in state_segments(states, start, end):
        for a, b, mode in modes:
            if mode in ("unknown", "unavailable") or len(mode) > 64:
                continue
            if max(lo, a) < min(hi, b):
                add_interval(records, target, max(lo, a), min(hi, b), state, zone,
                             source="history", mode=mode)
