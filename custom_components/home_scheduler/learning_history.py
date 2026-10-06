"""Optional Recorder warm start; this entire reader runs on its DB executor."""
from datetime import datetime, timezone

from .learning import record_history


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class RecorderReader:
    def __init__(self, hass, start, end):
        from sqlalchemy import or_, select
        from homeassistant.components.recorder.db_schema import RecorderRuns
        from homeassistant.components.recorder.util import session_scope

        self.hass, self.carry = hass, {}
        with session_scope(hass=hass, read_only=True) as session:
            rows = session.execute(select(RecorderRuns).where(
                RecorderRuns.start < end,
                or_(RecorderRuns.end.is_(None), RecorderRuns.end > start))).scalars()
            # An unclean run's end can actually be the next restart. Do not
            # extend its last known state through a possible multi-day outage.
            self.runs = [(r.run_id, utc(r.start), utc(r.end) if r.end else end)
                         for r in rows if not r.closed_incorrect]

    def read(self, start, end, targets, mode_entity, first_seen, zone, records):
        from homeassistant.components.recorder import get_instance, history

        recorder = get_instance(self.hass)
        entity_filter = getattr(recorder, "entity_filter", None)
        ids = list(targets) + ([mode_entity] if mode_entity else [])
        if callable(entity_filter):
            ids = [e for e in ids if entity_filter(e)]
        if not ids or (mode_entity and mode_entity not in ids):
            return 0
        for run_id, run_start, run_end in self.runs:
            lo, hi = max(start, run_start), min(end, run_end)
            if hi <= lo:
                continue
            changes = history.get_significant_states(
                self.hass, lo, hi, ids, include_start_time_state=False,
                significant_changes_only=True, minimal_response=False, no_attributes=True)
            carried = {}
            for entity in ids:
                values = list(changes.get(entity, []))
                previous = self.carry.get((run_id, entity))
                if previous is not None:
                    values.insert(0, previous)
                if values:
                    self.carry[(run_id, entity)] = values[-1]
                carried[entity] = values
            for target in targets:
                if target in ids:
                    stop = min(hi.timestamp(), first_seen[target])
                    record_history(records, target, carried.get(target, []), lo.timestamp(), stop, zone,
                                   mode_states=carried.get(mode_entity, []) if mode_entity else None)
        return sum(len(values) for values in records.values())
