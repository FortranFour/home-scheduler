"""Opt-in observer, bounded learning store, and isolated review actions."""
import asyncio
import copy
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .learning import LEARNING_KINDS, RETENTION_DAYS, add_interval, consensus, prune
from .learning_storage import pack, unpack
from .timeline import build_timeline, frame_at


class Learner:
    def __init__(self, owner):
        self.owner, self.hass = owner, owner.hass
        self.store = Store(self.hass, 1, DOMAIN + "_learning")
        self.data = {}
        self.active, self.drafts = {}, {}
        self.unsub = self.history_task = None
        self.bind_key = None
        self.running = False
        self.controlled = set()
        self.last_tick = self.last_publish = 0
        self.generation = 0
        self.save_lock = asyncio.Lock()
        self.save_task = None
        self.last_checkpoint = 0

    async def load(self):
        saved = await self.store.async_load()
        if saved:
            saved = await self.hass.async_add_executor_job(unpack, saved)
        self.data = {"enabled": False, "entities": [], "mode_entity": "", "records": {},
                     "first_seen": {}, "timezone": str(dt_util.now().tzinfo),
                     "history_state": "idle", "history_progress": 0,
                     "history_message": "Optional Recorder backfill has not been requested."}
        if isinstance(saved, dict):
            self.data.update(saved)
        if self.data["history_state"] == "reading":
            self.data.update(history_state="interrupted", history_message="Backfill was interrupted; request it again.")
        self.check_timezone()
        prune(self.data["records"], dt_util.now().date())

    def check_timezone(self):
        zone = str(dt_util.now().tzinfo)
        if self.data["timezone"] != zone:
            self.data.update(records={}, first_seen={}, timezone=zone, history_state="idle",
                             history_message="Time zone changed; learning starts again using the new local time.")
            self.active.clear()
            self.bind_key = None
            self.generation += 1

    def selected(self):
        ids = set(self.data["entities"])
        return [d for d in self.owner.devices if d["entity"] in ids and
                d["kind"] in LEARNING_KINDS and d["target"]]

    def status(self):
        targets = {d["target"]: d for d in self.selected()}
        return {**{k: self.data[k] for k in ("enabled", "entities", "mode_entity", "history_state",
                                            "history_progress", "history_message")},
                "retention_days": RETENTION_DAYS,
                "paused_targets": sorted(set(targets) & self.controlled) if self.data["enabled"] else [],
                "observed_days": {d["entity"]: len(self.data["records"].get(t, {})) for t, d in targets.items()}}

    def publish(self):
        self.owner.publish_plan()

    def mode(self):
        entity = self.data["mode_entity"]
        if not entity:
            return ""
        state = self.hass.states.get(entity)
        if state is None or state.state in ("unknown", "unavailable") or len(state.state) > 64:
            return None
        return state.state

    def actual(self, target):
        state = self.hass.states.get(target)
        if state is None or state.state not in ("on", "off") or state.attributes.get("restored"):
            return None
        return state.state

    def flush(self, target, now):
        current = self.active.get(target)
        if not current:
            return
        # A process hang or stopped loop is a coverage gap, not a constant OFF
        # interval. A healthy loop flushes once a minute even without events.
        if 0 <= now - current["at"] <= 120:
            add_interval(self.data["records"], target, current["at"], now, current["state"], dt_util.now().tzinfo,
                         mode=current["mode"], blocked=current["controlled"])
        current["at"] = max(current["at"], now)

    @callback
    def changed(self, event):
        now = event.time_fired.timestamp()
        entity = event.data.get("entity_id")
        for target in (list(self.active) if entity == self.data["mode_entity"] else [entity]):
            if target not in self.active:
                continue
            self.flush(target, now)
            self.active[target].update(state=self.actual(target), mode=self.mode())

    def sync(self):
        """Close old observations before rebinding or changing physical ownership."""
        self.check_timezone()
        now = dt_util.now().timestamp()
        eligible = {d["entity"] for d in self.owner.devices if d["kind"] in LEARNING_KINDS and d["target"]}
        self.data["entities"] = [e for e in self.data["entities"] if e in eligible]
        if not self.data["entities"]:
            self.data["enabled"] = False
        profile, _, _ = self.owner.context()
        controlled = {d["target"] for d in self.owner.devices if self.owner.data["physical"] and
                      profile["rows"][d["entity"]]["use"] and d["target"]}
        # A real scene can affect rows without explicit per-device calls.
        if self.owner.data["physical"] and self.owner.data["clock"] and (
                profile.get("scene") or any(d["kind"] == "scene" and d["target"] and
                                           profile["rows"][d["entity"]]["use"] for d in self.owner.devices)):
            controlled.update(d["target"] for d in self.selected())
        key = (self.data["enabled"] and self.running,
               tuple(sorted(d["target"] for d in self.selected())), self.data["mode_entity"])
        if key != self.bind_key:
            for target in list(self.active):
                self.flush(target, now)
            if self.unsub:
                self.unsub()
                self.unsub = None
            self.active = {}
            self.bind_key = key
            self.generation += 1
            if key[0]:
                for target in key[1]:
                    self.data["first_seen"].setdefault(target, now)
                    self.active[target] = {"at": now, "state": self.actual(target), "mode": self.mode(),
                                           "controlled": target in controlled}
                ids = list(key[1]) + ([key[2]] if key[2] else [])
                if ids:
                    self.unsub = async_track_state_change_event(self.hass, ids, self.changed)
        for target, current in self.active.items():
            if current["controlled"] != (target in controlled):
                self.flush(target, now)
                current.update(controlled=target in controlled, state=self.actual(target), mode=self.mode())
        self.controlled = controlled
        mapped = {d["target"] for d in self.owner.devices if d["target"]}
        prune(self.data["records"], dt_util.now().date())
        # Model changes need not discard useful observations of the same real
        # device. Keep a bounded cache; never attribute it by row name or ID.
        inactive = sorted((t for t in self.data["records"] if t not in mapped),
                          key=lambda t: max(self.data["records"][t]))
        while len(self.data["records"]) > 128 and inactive:
            del self.data["records"][inactive.pop(0)]
        self.data["first_seen"] = {t: v for t, v in self.data["first_seen"].items()
                                   if t in mapped or t in self.data["records"]}

    def tick(self):
        now = dt_util.now().timestamp()
        if now - self.last_tick < 60:
            return
        self.sync()
        for target in list(self.active):
            self.flush(target, now)
        prune(self.data["records"], dt_util.now().date())
        self.last_tick = now
        if self.data["enabled"] and now - self.last_checkpoint >= 300 and (
                self.save_task is None or self.save_task.done()):
            self.last_checkpoint = now
            self.save_task = self.hass.async_create_background_task(self.save(), DOMAIN + " learning checkpoint")
        if now - self.last_publish >= 300:
            self.publish()
            self.last_publish = now

    def start(self):
        self.running = True
        self.sync()
        self.publish()

    async def save(self):
        async with self.save_lock:
            recent = (dt_util.now().date() - timedelta(days=1)).isoformat()
            # Old buckets are immutable: backfill replaces source buckets.
            # Copy the two most recent dates to cover midnight/clock corrections,
            # the small dictionary structure before passing it to a worker.
            records = {target: {day: {source: {mode: copy.deepcopy(bucket) if day >= recent else bucket
                                             for mode, bucket in modes.items()} if isinstance(modes, dict) else modes
                                    for source, modes in sources.items()}
                                for day, sources in dates.items()}
                       for target, dates in self.data["records"].items()}
            snapshot = {**copy.deepcopy({k: v for k, v in self.data.items() if k != "records"}), "records": records}
            saved = await self.hass.async_add_executor_job(pack, snapshot)
            await self.store.async_save(saved)

    async def stop(self):
        self.running = False
        self.sync()
        if self.history_task:
            self.history_task.cancel()
            await asyncio.gather(self.history_task, return_exceptions=True)
            self.history_task = None
        if self.save_task:
            await asyncio.gather(self.save_task, return_exceptions=True)
            self.save_task = None
        await self.save()

    def eligible(self, entities):
        catalog = {d["entity"]: d for d in self.owner.devices}
        if not isinstance(entities, list) or not entities or len(entities) > 128 or len(set(entities)) != len(entities):
            raise ValueError("Choose at least one linked light, switch, or fan")
        for entity in entities:
            device = catalog.get(entity)
            if not device or device["kind"] not in LEARNING_KINDS or not device["target"]:
                raise ValueError("Learning needs a real connection to a light, switch, or fan")
        return entities

    def fingerprint(self):
        return [(d["entity"], d["target"], d["kind"]) for d in self.owner.devices]

    def draft(self, data):
        token = data.get("proposal")
        draft = self.drafts.get(token)
        if not draft or time.monotonic() - draft["created"] > 7200:
            raise ValueError("Proposal expired; generate it again")
        if draft["mapping"] != self.fingerprint():
            raise ValueError("Device connections changed; generate the proposal again")
        profile = copy.deepcopy(draft["profile"])
        edits = data.get("days", {})
        if not isinstance(edits, dict) or any(e not in draft["evidence"] for e in edits):
            raise ValueError("Edit only devices in this proposal")
        for entity, masks in edits.items():
            if not isinstance(masks, list) or len(masks) != 7 or any(
                    not isinstance(m, str) or not re.fullmatch(r"[0-9a-f]{24}", m) for m in masks):
                raise ValueError("Use seven valid 96-block days per device")
            profile["rows"][entity]["days"] = list(masks)
        return draft, profile

    async def command(self, call):
        """Response-capable service, completely separate from the runner's edits."""
        data = dict(call.data)
        try:
            async with self.owner.lock:
                op = data.get("op")
                if op == "configure":
                    entities = self.eligible(data.get("entities", self.data["entities"]))
                    enabled = data.get("enabled", self.data["enabled"])
                    if type(enabled) is not bool:
                        raise ValueError("Use true or false for learning")
                    mode = str(data.get("mode_entity", self.data["mode_entity"])).strip()
                    if len(mode) > 100 or (mode and not re.fullmatch(r"(?:input_select|input_boolean|person|binary_sensor)\.[a-z0-9_]+", mode)):
                        raise ValueError("Choose a discrete household mode or occupancy entity")
                    if mode != self.data["mode_entity"] and self.data["records"]:
                        raise ValueError("Clear learning data before changing the household mode entity")
                    self.data.update(entities=entities, enabled=enabled, mode_entity=mode)
                    self.sync()
                    await self.save()
                    result = {"status": self.status()}
                elif op == "clear":
                    if self.history_task:
                        self.history_task.cancel()
                    self.data["enabled"] = False
                    self.sync()
                    self.generation += 1
                    self.data.update(enabled=False, records={}, first_seen={}, history_state="idle", history_progress=0,
                                     history_message="Learning data cleared. Saved schedules are unchanged.")
                    self.drafts.clear()
                    await self.save()
                    result = {"status": self.status()}
                elif op == "history":
                    if self.history_task and not self.history_task.done():
                        raise ValueError("Recorder backfill is already running")
                    self.eligible(self.data["entities"])
                    components = getattr(self.hass.config, "components", set())
                    if "recorder" not in components:
                        self.data.update(history_state="unavailable", history_message="Recorder is not enabled; live learning works without it.")
                    else:
                        self.data.update(history_state="reading", history_progress=0, history_message="Reading available history in daily chunks…")
                        self.history_task = self.hass.async_create_background_task(self.backfill(), DOMAIN + " learning history")
                    result = {"status": self.status()}
                elif op == "propose":
                    entities = self.eligible(data.get("entities", self.data["entities"]))
                    lookback, threshold = data.get("lookback", 42), data.get("threshold", 60)
                    if type(lookback) is not int or lookback not in (28, 42, 56):
                        raise ValueError("Choose four, six, or eight weeks")
                    if type(threshold) is not int or not 50 <= threshold <= 100:
                        raise ValueError("Consensus must be between 50 and 100%")
                    include_history = data.get("include_history", False)
                    if type(include_history) is not bool:
                        raise ValueError("Choose whether to include older history")
                    mode_state = str(data.get("mode_state", "")).strip()
                    if len(mode_state) > 64 or (mode_state and not self.data["mode_entity"]):
                        raise ValueError("Configure a household mode entity before filtering its history")
                    self.sync()
                    now = dt_util.now()
                    for target in self.active:
                        self.flush(target, now.timestamp())
                    base = self.owner.profile(data.get("profile"))
                    profile = copy.deepcopy(base)
                    token = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:20]
                    profile.update(id=token, name="Learned schedule", condition_entity="", condition_state="", scene="")
                    evidence = {}
                    for device in self.owner.devices:
                        row = profile["rows"][device["entity"]]
                        row["use"] = device["entity"] in entities
                        if not row["use"]:
                            continue
                        value = consensus(self.data["records"], device["target"], row["days"], now,
                                          lookback=lookback, threshold=threshold, include_history=include_history,
                                          mode_state=mode_state)
                        row["days"] = value["days"]
                        evidence[device["entity"]] = value
                    self.drafts = {k: v for k, v in self.drafts.items() if time.monotonic() - v["created"] <= 7200}
                    while len(self.drafts) >= 4:
                        del self.drafts[next(iter(self.drafts))]
                    self.drafts[token] = {"created": time.monotonic(), "mapping": self.fingerprint(),
                                          "profile": profile, "evidence": evidence}
                    result = {"proposal": token, "profile": profile, "evidence": evidence,
                              "lookback": lookback, "threshold": threshold, "include_history": include_history,
                              "base_name": base["name"], "date": now.date().isoformat(), "mode_state": mode_state}
                elif op == "preview":
                    draft, profile = self.draft(data)
                    day = datetime.strptime(str(data["date"]), "%Y-%m-%d").date()
                    minute = data.get("minute", 0)
                    if type(minute) is not int or not 0 <= minute < 1440:
                        raise ValueError("Choose a valid preview time")
                    settings = {**self.owner.data, "random": {e: False for e in self.owner.ids}}
                    key = (day.isoformat(), tuple((e, tuple(profile["rows"][e]["days"])) for e in draft["evidence"]))
                    cache = draft.setdefault("timelines", {})
                    if key not in cache:
                        if len(cache) >= 7:
                            cache.clear()
                        cache[key] = build_timeline(self.owner.devices, profile, settings, day)
                    timeline = cache[key]
                    result = {"minute": minute, "date": day.isoformat(), "physical": False,
                              "states": frame_at(timeline, self.owner.devices, minute, day)}
                elif op == "save":
                    draft, profile = self.draft(data)
                    name = str(data.get("name", "")).strip()
                    if not name or len(name) > 100:
                        raise ValueError("Give the new schedule a name of at most 100 characters")
                    if len(self.owner.data["profiles"]) >= 12:
                        raise ValueError("Maximum of 12 schedules")
                    if any(p["name"].casefold() == name.casefold() for p in self.owner.data["profiles"]):
                        raise ValueError("Choose a new schedule name")
                    profile["id"] = hashlib.sha256(str(time.time_ns()).encode()).hexdigest()[:12]
                    profile["name"] = name
                    # Save without selecting or giving it an automatic condition.
                    self.owner.data["profiles"].append(profile)
                    try:
                        await self.owner.store.async_save(copy.deepcopy(self.owner.data))
                    except Exception:
                        self.owner.data["profiles"].remove(profile)
                        raise
                    result = {"profile": profile["id"], "name": name, "selected": False}
                    del self.drafts[data["proposal"]]
                else:
                    raise ValueError("Unknown learning operation")
                return result
        except (ValueError, KeyError, TypeError) as err:
            raise HomeAssistantError(str(err)) from err
        finally:
            self.publish()

    async def backfill(self):
        """Build into private memory; never hold the scheduling lock across I/O."""
        generation = self.generation
        targets = [d["target"] for d in self.selected()]
        now = dt_util.now()
        start = datetime.combine(now.date() - timedelta(days=RETENTION_DAYS), datetime.min.time(), now.tzinfo)
        start, end = start.astimezone(timezone.utc), now.astimezone(timezone.utc)
        first = {t: self.data["first_seen"].get(t, end.timestamp()) for t in targets}
        mode = self.data["mode_entity"]
        collected = {}
        try:
            from homeassistant.components.recorder import get_instance
            from .learning_history import RecorderReader
            executor = get_instance(self.hass).async_add_executor_job
            reader = await executor(RecorderReader, self.hass, start, end)
            cursor = start
            while cursor < end:
                stop = min(end, cursor + timedelta(days=1))
                await executor(reader.read, cursor, stop, targets, mode, first, now.tzinfo, collected)
                if generation != self.generation:
                    self.data.update(history_state="interrupted", history_message="Learning settings changed; request backfill again.")
                    return
                self.data["history_progress"] = round(100 * (stop - start) / (end - start))
                self.publish()
                cursor = stop
                await asyncio.sleep(0)
            async with self.owner.lock:
                if generation != self.generation:
                    return
                for target, dates in collected.items():
                    for day, sources in dates.items():
                        stored = self.data["records"].setdefault(target, {}).setdefault(day, {})
                        old = stored.get("history", {})
                        new = sources.get("history", {})
                        # Repeated backfills are idempotent. Retain older warm-
                        # start data if Recorder has since purged that period.
                        if sum(sum(b["known"]) for b in new.values()) >= sum(sum(b["known"]) for b in old.values()):
                            stored["history"] = new
                prune(self.data["records"], now.date())
                count = sum(len(dates) for dates in collected.values())
                self.data.update(history_state="ready", history_progress=100,
                                 history_message=f"Backfill complete: {count} device-days with observations. Older activity has uncertain source; include it explicitly when reviewing.")
                await self.save()
        except asyncio.CancelledError:
            if self.data["history_state"] == "reading":
                self.data.update(history_state="interrupted", history_message="Backfill was interrupted; request it again.")
            raise
        except Exception as err:
            self.data.update(history_state="error", history_message=f"Recorder backfill unavailable: {err}. Live learning can continue.")
        finally:
            self.publish()
