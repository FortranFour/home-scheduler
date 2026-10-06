"""Learning math, live gaps, persistence and armed-runner review isolation."""
import copy
import importlib
import types
import sys
from contextlib import nullcontext
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import ha_stubs as ha
from ha_stubs import target, mathmod, mask, hass_fixture

learning = importlib.import_module(target.__name__ + ".learning")
UTC = timezone.utc
NOW = datetime(2026, 10, 5, 18, tzinfo=UTC)


def sample(records, day, on_seconds=900, *, known=900, blocked=False, source="live", mode="", slot=72):
    at = datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(minutes=slot * 15)
    learning.add_interval(records, "light.real", at.timestamp(), at.timestamp() + min(on_seconds, known), "on", UTC,
                          source=source, mode=mode, blocked=blocked)
    learning.add_interval(records, "light.real", at.timestamp() + on_seconds, at.timestamp() + known, "off", UTC,
                          source=source, mode=mode, blocked=blocked)


class ConsensusTests(unittest.TestCase):
    def propose(self, records, **kw):
        return learning.consensus(records, "light.real", [mathmod.ZERO] * 7, NOW, **kw)

    def test_duration_vote_threshold_and_three_weekday_minimum(self):
        records = {}
        for day in ("2026-08-31", "2026-09-07", "2026-09-14"):
            sample(records, day, 450)
        for day in ("2026-09-21", "2026-09-28"):
            sample(records, day, 449)
        result = self.propose(records)
        self.assertTrue(mathmod.bits(result["days"][0])[72])
        self.assertEqual(result["samples"][0][72], "5")
        self.assertEqual(result["votes"][0][72], "3")
        self.assertFalse(mathmod.bits(self.propose(records, threshold=61)["days"][0])[72])
        self.assertEqual(result["brief_samples"], 2)

    def test_many_short_toggles_are_one_daily_vote(self):
        records = {}
        for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
            at = datetime.fromisoformat(day).replace(hour=18, tzinfo=UTC).timestamp()
            for minute in range(15):
                learning.add_interval(records, "light.real", at+minute*60, at+minute*60+10, "on", UTC)
                learning.add_interval(records, "light.real", at+minute*60+10, at+(minute+1)*60, "off", UTC)
        result = self.propose(records)
        self.assertTrue(mathmod.bits(result["known"][0])[72])
        self.assertFalse(mathmod.bits(result["days"][0])[72])
        self.assertEqual(result["votes"][0][72], "0")
        self.assertEqual(result["brief_samples"], 3)

    def test_missing_and_unknown_coverage_preserves_existing_blocks(self):
        records = {}
        sample(records, "2026-09-07", 0)
        sample(records, "2026-09-14", 0)
        sample(records, "2026-09-21", 0, known=809)
        at = datetime(2026, 9, 28, 18, tzinfo=UTC).timestamp()
        learning.add_interval(records, "light.real", at, at+900, "unavailable", UTC)
        base = [mask(72,73)] * 7
        result = learning.consensus(records, "light.real", base, NOW)
        self.assertEqual(result["samples"][0][72], "2")
        self.assertEqual(result["days"], base)
        self.assertEqual(result["usable_cells"], 0)

    def test_known_off_is_distinct_from_still_learning(self):
        records = {}
        for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
            sample(records, day, 0)
        result = learning.consensus(records, "light.real", [mask(72,73)]*7, NOW)
        self.assertTrue(mathmod.bits(result["known"][0])[72])
        self.assertFalse(mathmod.bits(result["days"][0])[72])
        self.assertTrue(mathmod.bits(result["days"][1])[72])

    def test_controlled_part_of_a_block_excludes_whole_daily_sample(self):
        records = {}
        for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
            sample(records, day)
            at=datetime.fromisoformat(day).replace(hour=18,tzinfo=UTC).timestamp()
            learning.add_interval(records,"light.real",at,at+1,None,UTC,blocked=True)
        result=self.propose(records)
        self.assertEqual(result["samples"][0][72],"0")
        self.assertEqual(result["excluded_samples"],3)

    def test_control_exclusion_also_applies_when_mode_was_unknown_or_filtered_out(self):
        records={}
        for index,day in enumerate(("2026-09-07","2026-09-14","2026-09-21")):
            sample(records,day,mode="Guest",known=840)
            at=datetime.fromisoformat(day).replace(hour=18,tzinfo=UTC).timestamp()
            learning.add_interval(records,"light.real",at+840,at+900,None,UTC,
                                  mode=None if index==0 else "Home",blocked=True)
        result=self.propose(records,mode_state="Guest")
        self.assertEqual(result["samples"][0][72],"0")
        self.assertEqual(result["excluded_samples"],3)

    def test_older_history_requires_explicit_opt_in_and_does_not_double_count(self):
        records={}
        for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
            sample(records,day,source="history",known=450)
            at=datetime.fromisoformat(day).replace(hour=18,tzinfo=UTC).timestamp()
            learning.add_interval(records,"light.real",at+450,at+900,"on",UTC)
        self.assertEqual(self.propose(records)["usable_cells"],0)
        result=self.propose(records,include_history=True)
        self.assertEqual(result["samples"][0][72],"3")
        self.assertTrue(mathmod.bits(result["days"][0])[72])

    def test_household_mode_filter_uses_observed_mode_not_current_mode(self):
        records={}
        for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
            sample(records,day,mode="Guest")
        for day in ("2026-08-31", "2026-09-28"):
            sample(records,day,0,mode="Away")
        self.assertEqual(self.propose(records,mode_state="Guest")["votes"][0][72],"3")
        self.assertEqual(self.propose(records,mode_state="Away")["usable_cells"],0)

    def test_overnight_and_local_weekday_split(self):
        records={};zone=ZoneInfo("America/Los_Angeles")
        start=datetime(2026,9,27,23,45,tzinfo=zone)
        learning.add_interval(records,"light.real",start.timestamp(),start.timestamp()+1800,"on",zone)
        self.assertEqual(records["light.real"]["2026-09-27"]["live"][""]["on"][95],900)
        self.assertEqual(records["light.real"]["2026-09-28"]["live"][""]["on"][0],900)

    def test_dst_repeated_time_is_rejected_and_missing_time_is_not_off(self):
        records={};zone=ZoneInfo("America/New_York")
        fall=datetime(2026,11,1,0,45,tzinfo=zone)
        learning.add_interval(records,"light.real",fall.timestamp(),fall.timestamp()+9000,"on",zone)
        b=records["light.real"]["2026-11-01"]["live"][""]
        self.assertEqual(b["known"][4:8],[0]*4)
        self.assertFalse(learning.completed_slot(fall.date(),7,fall+timedelta(days=1)))
        spring=datetime(2026,3,8,1,45,tzinfo=zone)
        learning.add_interval(records,"light.real",spring.timestamp(),spring.timestamp()+1800,"on",zone)
        b=records["light.real"]["2026-03-08"]["live"][""]
        self.assertEqual(b["known"][8:12],[0]*4)

    def test_history_has_no_implied_state_before_first_event(self):
        start=datetime(2026,9,7,18,tzinfo=UTC).timestamp()
        values=[types.SimpleNamespace(state="on",last_updated=datetime.fromtimestamp(start+300,UTC)),
                types.SimpleNamespace(state="unavailable",last_updated=datetime.fromtimestamp(start+600,UTC))]
        records={}
        learning.record_history(records,"light.real",values,start,start+900,UTC)
        b=records["light.real"]["2026-09-07"]["history"][""]
        self.assertEqual(b["known"][72],300)
        self.assertEqual(self.propose(records,include_history=True)["usable_cells"],0)

    def test_history_mode_is_joined_at_the_time_it_happened(self):
        start=datetime(2026,9,7,18,tzinfo=UTC).timestamp()
        state=lambda at,value:types.SimpleNamespace(state=value,last_updated=datetime.fromtimestamp(at,UTC))
        records={}
        learning.record_history(records,"light.real",[state(start,"on")],start,start+900,UTC,
                                mode_states=[state(start,"Home"),state(start+450,"Guest")])
        modes=records["light.real"]["2026-09-07"]["history"]
        self.assertEqual(modes["Home"]["on"][72],450)
        self.assertEqual(modes["Guest"]["on"][72],450)

    def test_retention_keeps_56_full_days_and_current_partial_day(self):
        records={}
        for delta in range(100):
            sample(records,(NOW.date()-timedelta(days=delta)).isoformat())
        learning.prune(records,NOW.date())
        self.assertEqual(len(records["light.real"]),57)


class ObserverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now=NOW
        self.clock=patch.object(ha.dt,"now",side_effect=lambda:self.now)
        self.clock.start();self.addCleanup(self.clock.stop)
        self.hass=hass_fixture();self.hass.config=types.SimpleNamespace(components=set())
        self.hass.states.async_set("light.real","on",{})
        self.hass.states.async_set("switch.real","on",{})
        self.scheduler=target.Scheduler(self.hass,[
            {"entity":"light.preview","name":"Lamp","target":"light.real"},
            {"entity":"switch.preview","name":"Plug","target":"switch.real"},
            {"entity":"cover.preview","name":"Blind","target":"cover.real"},
        ])
        await self.scheduler.load()
        self.learner=self.scheduler.learning
        self.learner.start()

    async def command(self,op,**data):
        return await self.learner.command(types.SimpleNamespace(data={"op":op,**data}))

    async def enable(self,**kw):
        await self.command("configure",entities=["light.preview","switch.preview"],enabled=True,**kw)

    def advance(self,minutes=1):
        for _ in range(minutes):
            self.now+=timedelta(minutes=1);self.learner.tick()

    def change(self,entity,state):
        self.hass.states.async_set(entity,state,{})
        event=types.SimpleNamespace(time_fired=self.now,data={"entity_id":entity})
        for ids,callback in list(self.hass.state_listeners):
            if entity in ids: callback(event)

    async def test_opt_in_targets_only_not_virtual_states(self):
        self.advance(15)
        self.assertEqual(self.learner.data["records"],{})
        await self.enable()
        self.change("light.preview","off")
        self.advance(15)
        self.assertEqual(self.learner.data["records"]["light.real"]["2026-10-05"]["live"][""]["on"][73],900)
        self.assertNotIn("light.preview",self.learner.data["records"])
        self.assertEqual(self.hass.services.calls,[])

    async def test_unavailable_time_and_loop_stall_do_not_become_off(self):
        await self.enable();self.advance(5);self.change("light.real","unavailable");self.advance(10)
        b=self.learner.data["records"]["light.real"]["2026-10-05"]["live"][""]
        self.assertEqual(b["known"][72],300)
        self.now+=timedelta(hours=3);self.learner.tick()
        self.assertEqual(sum(b["known"]),300)

    async def test_full_physical_control_interval_excluded_other_row_keeps_learning(self):
        await self.enable()
        self.scheduler.profile()["rows"]["switch.preview"]["use"]=False
        self.scheduler.data["physical"]=True;self.learner.sync()
        self.advance(15)
        dates=self.learner.data["records"]
        self.assertEqual(dates["light.real"]["2026-10-05"]["live"][""]["blocked"][72],900)
        self.assertEqual(dates["switch.real"]["2026-10-05"]["live"][""]["on"][72],900)
        self.assertEqual(self.hass.services.calls,[])

    async def test_physical_ownership_edges_do_not_count_controlled_constant_states(self):
        await self.enable();self.advance(5)
        self.scheduler.data["physical"]=True;self.learner.sync();self.advance(5)
        self.scheduler.data["physical"]=False;self.learner.sync();self.advance(5)
        b=self.learner.data["records"]["light.real"]["2026-10-05"]["live"][""]
        self.assertEqual(b["known"][72],600);self.assertEqual(b["blocked"][72],300)

    async def test_pause_resume_and_restart_preserve_data_without_covering_downtime(self):
        await self.enable();self.advance(15)
        await self.command("configure",enabled=False)
        self.advance(15)
        await self.command("configure",enabled=True)
        self.advance(15)
        await self.learner.stop()
        saved=copy.deepcopy(self.learner.store.saved)
        self.now+=timedelta(days=2)
        new=target.Scheduler(self.hass,self.scheduler.devices)
        new.store.saved=copy.deepcopy(self.scheduler.data)
        new.learning.store.saved=saved
        await new.load();new.learning.start()
        self.assertTrue(new.learning.data["enabled"])
        self.assertEqual(len(new.learning.data["records"]["light.real"]),1)
        self.assertFalse(new.data["physical"])
        self.assertEqual(len(self.hass.state_listeners),1)
        await new.learning.stop();self.assertEqual(self.hass.state_listeners,[])

    async def test_clear_removes_open_interval_and_keeps_profiles(self):
        await self.enable();self.now+=timedelta(seconds=30)
        before=copy.deepcopy(self.scheduler.data)
        await self.command("clear")
        self.assertEqual(self.learner.data["records"],{})
        self.assertEqual(self.learner.data["first_seen"],{})
        self.assertFalse(self.learner.data["enabled"])
        self.assertEqual(self.scheduler.data,before)
        self.assertEqual(self.hass.state_listeners,[])

    async def test_remapping_rebinds_targets_and_rejects_stale_proposal(self):
        await self.enable();self.advance(1)
        proposal=await self.command("propose")
        self.scheduler.device("light.preview")["target"]="light.other"
        self.learner.sync()
        self.assertNotIn("light.real",self.learner.active)
        self.assertIn("light.other",self.learner.active)
        self.assertIn("light.real",self.learner.data["records"])
        fresh=await self.command("propose")
        self.assertEqual(fresh["evidence"]["light.preview"]["usable_cells"],0)
        with self.assertRaisesRegex(Exception,"connections changed"):
            await self.command("save",proposal=proposal["proposal"],name="New")

    async def test_mode_changes_split_real_observations_and_configuration_is_validated(self):
        self.hass.states.async_set("input_select.household","Home")
        await self.enable(mode_entity="input_select.household")
        self.advance(5);self.change("input_select.household","Guest");self.advance(10)
        modes=self.learner.data["records"]["light.real"]["2026-10-05"]["live"]
        self.assertEqual(modes["Home"]["known"][72],300)
        self.assertEqual(modes["Guest"]["known"][72],600)
        with self.assertRaisesRegex(Exception,"Clear learning data"):
            await self.command("configure",mode_entity="person.someone")
        with self.assertRaises(Exception):
            await self.command("configure",entities=["cover.preview"])
        with self.assertRaises(Exception):
            await self.command("propose",threshold=True)

    async def test_proposal_preview_edit_save_do_not_change_armed_runner_or_real_entities(self):
        await self.enable()
        for day in ("2026-09-07","2026-09-14","2026-09-21"):
            sample(self.learner.data["records"],day)
        self.scheduler.data.update(physical=True,clock=True,auto=True)
        before=copy.deepcopy(self.scheduler.data)
        states=copy.deepcopy(self.hass.states.values)
        proposal=await self.command("propose",entities=["light.preview"])
        frame=await self.command("preview",proposal=proposal["proposal"],date="2026-10-05",minute=1080)
        self.assertEqual(frame["states"]["light.preview"]["state"],"on")
        self.assertFalse(frame["physical"])
        days=[mask(72,74)]+[mathmod.ZERO]*6
        saved=await self.command("save",proposal=proposal["proposal"],days={"light.preview":days},name="Observed routine")
        self.assertFalse(saved["selected"])
        self.assertEqual(self.scheduler.data["profile"],before["profile"])
        self.assertTrue(self.scheduler.data["physical"] and self.scheduler.data["clock"])
        self.assertEqual(self.scheduler.data["profiles"][:-1],before["profiles"])
        new=self.scheduler.data["profiles"][-1]
        self.assertEqual(new["rows"]["light.preview"]["days"],days)
        self.assertFalse(new["rows"]["cover.preview"]["use"])
        self.assertEqual(new["condition_entity"],"")
        self.assertEqual(self.hass.states.get("light.real").state,states["light.real"].state)
        self.assertEqual(self.hass.services.calls,[])
        self.assertEqual(self.scheduler.store.saved["profiles"][-1]["name"],"Observed routine")
        self.assertNotIn("records",self.hass.states.get("sensor.home_scheduler").attributes["learning"])

    async def test_save_failure_rolls_back_new_profile_and_invalid_edits_are_rejected(self):
        await self.enable();proposal=await self.command("propose")
        count=len(self.scheduler.data["profiles"])
        with self.assertRaises(Exception):
            await self.command("save",proposal=proposal["proposal"],days={"cover.preview":[mathmod.ZERO]*7},name="Bad")
        async def fail(_): raise RuntimeError("Disk full")
        with patch.object(self.scheduler.store,"async_save",side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,"Disk full"):
                await self.command("save",proposal=proposal["proposal"],name="Not saved")
        self.assertEqual(len(self.scheduler.data["profiles"]),count)

    async def test_no_recorder_is_a_reported_fallback_not_an_error(self):
        await self.enable();result=await self.command("history")
        self.assertEqual(result["status"]["history_state"],"unavailable")
        self.assertTrue(self.learner.data["enabled"])

    async def test_timezone_change_discards_incompatible_cell_dates(self):
        await self.enable();self.advance(1)
        self.now=self.now.astimezone(ZoneInfo("America/Los_Angeles"))
        self.learner.sync()
        self.assertEqual(self.learner.data["records"],{})
        self.assertEqual(self.learner.data["timezone"],"America/Los_Angeles")

    async def test_backfill_is_idempotent_and_retains_data_after_recorder_purge(self):
        await self.enable()
        class Reader:
            empty=False
            def __init__(self,*args): pass
            def read(self,start,end,targets,mode,first,zone,records):
                if not self.empty and start.weekday()==0 and start.date()<NOW.date():
                    sample(records,start.date().isoformat(),source="history")
        async def executor(fn,*args): return fn(*args)
        recorder=types.ModuleType("homeassistant.components.recorder")
        recorder.get_instance=lambda hass:types.SimpleNamespace(async_add_executor_job=executor)
        history=importlib.import_module(target.__name__+".learning_history")
        with patch.dict(sys.modules,{"homeassistant.components.recorder":recorder}),patch.object(history,"RecorderReader",Reader):
            await self.learner.backfill()
            before=copy.deepcopy(self.learner.data["records"])
            await self.learner.backfill()
            self.assertEqual(self.learner.data["records"],before)
            Reader.empty=True
            await self.learner.backfill()
            self.assertEqual(self.learner.data["records"],before)
        self.assertEqual(self.learner.data["history_state"],"ready")
        self.assertEqual(self.hass.services.calls,[])


class RecorderReaderTests(unittest.TestCase):
    def test_unclean_runs_are_not_used_as_coverage(self):
        reader_module=importlib.import_module(target.__name__+".learning_history")
        class Expr:
            def __lt__(self,other): return self
            def __gt__(self,other): return self
            def is_(self,other): return self
            def where(self,*args): return self
        sql=types.ModuleType("sqlalchemy");sql.select=lambda model:Expr();sql.or_=lambda *args:Expr()
        db=types.ModuleType("homeassistant.components.recorder.db_schema")
        db.RecorderRuns=types.SimpleNamespace(start=Expr(),end=Expr())
        runs=[types.SimpleNamespace(run_id=1,start=NOW-timedelta(days=5),end=NOW-timedelta(days=4),closed_incorrect=False),
              types.SimpleNamespace(run_id=2,start=NOW-timedelta(days=4),end=NOW,closed_incorrect=True)]
        util=types.ModuleType("homeassistant.components.recorder.util")
        session=types.SimpleNamespace(execute=lambda statement:types.SimpleNamespace(scalars=lambda:runs))
        util.session_scope=lambda **kw:nullcontext(session)
        with patch.dict(sys.modules,{"sqlalchemy":sql,"homeassistant.components.recorder.db_schema":db,
                                     "homeassistant.components.recorder.util":util}):
            reader=reader_module.RecorderReader(object(),NOW-timedelta(days=6),NOW)
        self.assertEqual([r[0] for r in reader.runs],[1])

    def test_carry_is_confined_to_each_clean_run_and_clipped_at_live_start(self):
        reader_module=importlib.import_module(target.__name__+".learning_history")
        start=datetime(2026,9,7,18,tzinfo=UTC)
        # A five-minute shutdown gap splits one cell into only 600 known seconds.
        reader=object.__new__(reader_module.RecorderReader)
        reader.hass=object();reader.carry={}
        reader.runs=[(1,start,start+timedelta(minutes=5)),
                     (2,start+timedelta(minutes=10),start+timedelta(hours=1))]
        queries=[]
        def changes(hass,lo,hi,ids,**kw):
            queries.append((lo,hi,ids,kw))
            states=[]
            if lo==start: states=[types.SimpleNamespace(state="on",last_updated=start)]
            if lo==start+timedelta(minutes=10): states=[types.SimpleNamespace(state="off",last_updated=lo)]
            return {"light.real":states}
        recorder=types.ModuleType("homeassistant.components.recorder")
        recorder.get_instance=lambda hass:types.SimpleNamespace(entity_filter=lambda entity:True)
        recorder.history=types.SimpleNamespace(get_significant_states=changes)
        records={};first={"light.real":(start+timedelta(minutes=30)).timestamp()}
        with patch.dict(sys.modules,{"homeassistant.components.recorder":recorder}):
            reader.read(start,start+timedelta(minutes=15),["light.real"],"",first,UTC,records)
            reader.read(start+timedelta(minutes=15),start+timedelta(hours=1),["light.real"],"",first,UTC,records)
        bucket=records["light.real"]["2026-09-07"]["history"][""]
        self.assertEqual(bucket["known"][72],600)
        self.assertEqual(bucket["on"][72],300)
        self.assertEqual(bucket["known"][73],900)
        self.assertEqual(bucket["known"][74],0)
        self.assertTrue(all(not q[3]["include_start_time_state"] for q in queries))

    def test_no_events_or_excluded_entities_never_create_off_votes(self):
        reader_module=importlib.import_module(target.__name__+".learning_history")
        start=NOW-timedelta(days=1)
        reader=object.__new__(reader_module.RecorderReader)
        reader.hass=object();reader.carry={};reader.runs=[(1,start,NOW)]
        recorder=types.ModuleType("homeassistant.components.recorder")
        recorder.get_instance=lambda hass:types.SimpleNamespace(entity_filter=lambda entity:True)
        recorder.history=types.SimpleNamespace(get_significant_states=lambda *args,**kw:{})
        records={}
        with patch.dict(sys.modules,{"homeassistant.components.recorder":recorder}):
            reader.read(start,NOW,["light.real"],"",{"light.real":NOW.timestamp()},UTC,records)
            recorder.get_instance=lambda hass:types.SimpleNamespace(entity_filter=lambda entity:False)
            reader.read(start,NOW,["light.real"],"",{"light.real":NOW.timestamp()},UTC,records)
        self.assertEqual(records,{})


class LearningStorageTests(unittest.TestCase):
    def test_compressed_checkpoint_round_trip_is_separate_and_small(self):
        storage=importlib.import_module(target.__name__+".learning_storage")
        records={}
        for delta in range(1,43):
            day=NOW.date()-timedelta(days=delta)
            sample(records,day.isoformat())
        original={"records":records,"entities":["light.preview"],"enabled":True}
        saved=storage.pack(original)
        self.assertEqual(storage.unpack(saved),original)
        self.assertLess(len(saved["records"]),2000)
        self.assertIsInstance(original["records"],dict)
