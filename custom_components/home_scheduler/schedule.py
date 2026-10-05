"""Pure scheduling math: Monday-first weeks and reproducible boundary variation."""
import hashlib
from datetime import timedelta

ZERO = "0" * 24
SLOTS = 96
WEEK = 10080


def bits(mask):
    return [bool(int(mask[i // 4], 16) & (8 >> (i % 4))) for i in range(SLOTS)]


def put(mask, slot, value):
    chars = list(mask)
    nibble, flag = int(chars[slot // 4], 16), 8 >> (slot % 4)
    chars[slot // 4] = format(nibble | flag if value else nibble & ~flag, "x")
    return "".join(chars)


def windows(masks):
    """Return contiguous spans, joining Sunday night to Monday morning."""
    values = [value for mask in masks for value in bits(mask)]
    if not any(values):
        return []
    if all(values):
        return [(0, WEEK)]
    spans, start = [], None
    for i, value in enumerate(values + [False]):
        if value and start is None:
            start = i * 15
        elif not value and start is not None:
            spans.append((start, i * 15))
            start = None
    if values[0] and values[-1] and len(spans) > 1:
        first, last = spans[0], spans[-1]
        spans = spans[1:-1] + [(last[0], WEEK + first[1])]
    return spans


def effective(masks, entity, monday, selected_day, seed, jitter):
    """Randomize each contiguous window once, then clip it to a calendar day."""
    spans = windows(masks)
    if spans == [(0, WEEK)]:
        return [(0, 1440)]
    result, offset = [], selected_day * 1440
    for week in (-1, 0, 1):
        anchor = monday + timedelta(days=7 * week)
        for start, end in spans:
            a = b = 0
            if jitter:
                key = f"{seed}|{entity}|{anchor.isoformat()}|{start}"
                digest = hashlib.sha256(key.encode()).digest()
                a = int.from_bytes(digest[:4], "big") % (2 * jitter + 1) - jitter
                b = int.from_bytes(digest[4:8], "big") % (2 * jitter + 1) - jitter
            lo = week * WEEK + start + a - offset
            hi = max(lo + 1, week * WEEK + end + b - offset)
            lo, hi = max(0, lo), min(1440, hi)
            if hi > lo:
                result.append((lo, hi))
    merged = []
    for lo, hi in sorted(result):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged
