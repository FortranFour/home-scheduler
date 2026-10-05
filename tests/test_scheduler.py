"""Run: python3 -m unittest discover -s tests -v. HA APIs are test doubles."""
import copy
import importlib
import json
import struct
import types
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import ha_stubs as ha
from ha_stubs import target, mathmod, mask, hass_fixture


class MathTests(unittest.TestCase):
    def test_each_quarter_hour_round_trips(self):
        for slot in range(96):
            saved = mathmod.put(mathmod.ZERO, slot, True)
            self.assertEqual([i for i, b in enumerate(mathmod.bits(saved)) if b], [slot])
            self.assertEqual(mathmod.put(saved, slot, False), mathmod.ZERO)

    def test_overnight_and_week_boundary(self):
        masks = [mathmod.ZERO] * 7
        masks[6], masks[0] = mask(92,96), mask(0,4)
        sun = mathmod.effective(masks,"light.x",date(2026,9,28),6,31,15)
        mon = mathmod.effective(masks,"light.x",date(2026,10,5),0,31,15)
        self.assertEqual(sun[-1][1],1440)
        self.assertEqual(mon[0][0],0)
        self.assertTrue(1365 <= sun[0][0] <= 1395)
        self.assertTrue(45 <= mon[-1][1] <= 75)

    def test_repeatable_variation_and_full_week(self):
        masks=[mathmod.ZERO]*7; masks[0]=mask(72,88)
        for seed in range(100):
            a=mathmod.effective(masks,"light.x",date(2026,10,5),0,seed,15)
            self.assertEqual(a,mathmod.effective(masks,"light.x",date(2026,10,5),0,seed,15))
            self.assertTrue(1065 <= a[0][0] <= 1095)
            self.assertTrue(1305 <= a[0][1] <= 1335)
        self.assertEqual(mathmod.effective(["f"*24]*7,"light.x",date(2026,10,5),0,1,60),[(0,1440)])


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass = hass_fixture()
        self.s = target.Scheduler(self.hass)
        await self.s.load()
        self.s.data.update(date="2026-10-05", minute=1080)
        self.day = date(2026,10,5)

    async def command(self, **data):
        await self.s.command(types.SimpleNamespace(data=data))

    def frame(self):
        return self.hass.states.get("sensor.home_scheduler_frame").attributes

    async def bind(self, preview, real, state="off", attrs=None):
        self.hass.states.async_set(real,state,attrs)
        await self.command(op="device",entity=preview,target=real)

    async def test_demo_has_all_requested_types_and_no_thermostats(self):
        self.assertEqual({d["kind"] for d in self.s.devices}, {"light","switch","fan","cover","scene"})
        self.assertTrue(all(not d["target"] for d in self.s.devices))
        self.assertEqual(self.s.data["shown_types"],["light"])
        self.assertTrue({d.get("device_class") for d in self.s.devices if d["kind"]=="cover"} >= {"blind","curtain","garage","shutter"})

    async def test_simulation_does_not_call_or_change_real_devices(self):
        await self.bind("light.hs_demo_living","light.real",attrs={"brightness":80,"supported_color_modes":["rgb"]})
        await self.s.apply()
        self.assertEqual(self.hass.services.calls,[])
        self.assertEqual(self.hass.states.get("light.real").state,"off")
        self.assertEqual(self.frame()["states"]["light.hs_demo_living"]["state"],"on")

    async def test_unlinked_demo_never_operates_real_devices(self):
        await self.command(op="settings",physical=True)
        self.assertEqual(self.hass.services.calls,[])

    async def test_real_light_brightness_and_color(self):
        await self.bind("light.hs_demo_living","light.real",attrs={"brightness":0,"rgb_color":[255,255,255],"supported_color_modes":["rgb"]})
        await self.command(op="row",entity="light.hs_demo_living",on={"brightness":40,"color":"#123456"})
        await self.command(op="settings",physical=True)
        domain,action,data,_=self.hass.services.calls[-1]
        self.assertEqual((domain,action),("light","turn_on"))
        self.assertEqual(data["brightness"],102)
        self.assertEqual(data["rgb_color"],[18,52,86])
        count=len(self.hass.services.calls)
        await self.s.apply()
        self.assertEqual(len(self.hass.services.calls),count)

    async def test_light_can_bind_to_a_wall_switch(self):
        await self.bind("light.hs_demo_living","switch.wall")
        await self.command(op="settings",physical=True)
        self.assertEqual(self.hass.services.calls[-1][:3],("switch","turn_on",{"entity_id":"switch.wall"}))

    async def test_fan_percentage_and_on_off_only_fan(self):
        await self.bind("fan.hs_demo_ceiling","fan.real",attrs={"supported_features":1,"percentage":0})
        await self.command(op="settings",physical=True)
        self.assertEqual(self.hass.services.calls[-1][:3],("fan","turn_on",{"entity_id":"fan.real","percentage":60.0}))
        await self.command(op="settings",physical=False)
        self.hass.states.async_set("fan.real","off",{"supported_features":0})
        await self.command(op="settings",physical=True)
        self.assertEqual(self.hass.services.calls[-1][2],{"entity_id":"fan.real"})

    async def test_cover_position_endpoint_and_unsupported_partial(self):
        await self.bind("cover.hs_demo_blind","cover.real",state="closed",attrs={"current_position":0,"supported_features":15})
        await self.command(op="settings",physical=True,minute=540)
        self.assertEqual(self.hass.services.calls[-1][:3],("cover","set_cover_position",{"entity_id":"cover.real","position":85}))
        await self.command(op="settings",minute=1200)
        self.assertEqual(self.hass.services.calls[-1][1],"close_cover")
        await self.command(op="settings",physical=False)
        self.hass.states.async_set("cover.real","closed",{"supported_features":3})
        before=len(self.hass.services.calls)
        await self.command(op="settings",physical=True,minute=540)
        self.assertEqual(len(self.hass.services.calls),before)
        self.assertIn("open/closed only"," ".join(self.s.errors))

    async def test_leave_unchanged_outside_periods(self):
        await self.bind("switch.hs_demo_fountain","switch.real",state="on")
        await self.command(op="row",entity="switch.hs_demo_fountain",outside="unchanged")
        await self.command(op="settings",physical=True,minute=1380)
        self.assertEqual(self.hass.services.calls,[])

    async def test_restore_real_state_once_after_period(self):
        await self.bind("fan.hs_demo_ceiling","fan.real",state="on",attrs={"supported_features":1,"percentage":25})
        await self.command(op="row",entity="fan.hs_demo_ceiling",outside="restore")
        await self.command(op="settings",physical=True,minute=1000)
        self.assertEqual(self.hass.states.get("fan.real").attributes["percentage"],60)
        await self.command(op="settings",minute=1400)
        self.assertEqual(self.hass.states.get("fan.real").attributes["percentage"],25)
        count=len(self.hass.services.calls)
        await self.s.apply()
        self.assertEqual(len(self.hass.services.calls),count)
        self.assertNotIn("fan.hs_demo_ceiling",self.s.restore)

    async def test_scene_preview_effects_and_no_fake_energy(self):
        await self.command(op="settings",minute=1110)
        state=self.frame()["states"]["light.hs_demo_accent"]
        self.assertEqual(state["state"],"on")
        self.assertEqual(state["attributes"]["rgb_color"],[187,117,255])
        timeline=self.s.timeline(self.s.profile(),self.day)
        self.assertEqual(timeline["energy"]["scene.hs_demo_evening"]["events"],1)
        self.assertIsNone(timeline["energy"]["scene.hs_demo_evening"]["kwh"])
        self.assertAlmostEqual(timeline["energy"]["light.hs_demo_accent"]["kwh"],.0225)
        await self.command(op="settings",minute=1380)
        self.assertEqual(self.frame()["states"]["light.hs_demo_accent"]["state"],"off")
        self.assertEqual(self.hass.services.calls,[])

    async def test_adjacent_scene_cells_remain_independent_events(self):
        await self.command(op="range",entity="scene.hs_demo_evening",day=0,start=72,end=73,value=True)
        events=self.s.timeline(self.s.profile(),self.day)["events"]
        self.assertEqual([e["minute"] for e in events if e["entity"]=="scene.hs_demo_evening"],[1080,1095,1110])

    async def test_scene_physical_clock_once_and_never_from_scrub(self):
        await self.bind("scene.hs_demo_evening","scene.real",state="unknown")
        await self.command(op="settings",physical=True,minute=1110)
        self.assertEqual(self.hass.services.calls,[])
        with patch.object(ha.dt,"now",return_value=datetime(2026,10,5,18,29,tzinfo=timezone.utc)):
            await self.command(op="settings",clock=True)
        with patch.object(ha.dt,"now",return_value=datetime(2026,10,5,18,30,tzinfo=timezone.utc)):
            await self.s.apply(advance=True)
            await self.s.apply(advance=True)
        self.assertEqual(len(self.hass.services.calls),1)
        self.assertEqual(self.hass.services.calls[0][:3],("scene","turn_on",{"entity_id":"scene.real"}))
        await self.command(op="settings",clock=False,minute=1110)
        self.assertEqual(len(self.hass.services.calls),1)

    async def test_failed_scene_attempt_is_claimed_and_not_repeated(self):
        await self.bind("scene.hs_demo_evening","scene.real",state="unknown")
        with patch.object(ha.dt,"now",return_value=datetime(2026,10,5,18,29,tzinfo=timezone.utc)):
            await self.command(op="settings",physical=True,clock=True)
        self.hass.services.fail=True
        with patch.object(ha.dt,"now",return_value=datetime(2026,10,5,18,30,tzinfo=timezone.utc)):
            await self.s.apply(advance=True)
        self.assertEqual(len(self.hass.services.calls),1)
        self.assertTrue(self.s.store.saved["fired_events"])

    async def test_profile_activation_scene_once(self):
        self.hass.states.async_set("scene.real","unknown")
        await self.command(op="profile",scene="scene.real")
        await self.command(op="settings",physical=True,clock=True)
        await self.s.apply()
        self.assertEqual(len(self.hass.services.calls),1)

    async def test_cover_energy_is_motor_travel_not_open_hours(self):
        value=self.s.timeline(self.s.profile(),self.day)["energy"]["cover.hs_demo_blind"]
        self.assertAlmostEqual(value["kwh"],8*10*2*.85/3600000,places=6)
        self.assertEqual(value["minutes"],0)
        await self.command(op="fill",entities=["cover.hs_demo_blind"],day=0,value=True)
        energy=self.s.timeline(self.s.profile(),self.day)["energy"]["cover.hs_demo_blind"]["kwh"]
        self.assertLess(energy,.001)

    async def test_profile_scene_baseline_is_applied_after_previous_day_events(self):
        await self.command(op="profile",scene="scene.hs_demo_evening")
        await self.command(op="settings",minute=720)
        accent = self.frame()["states"]["light.hs_demo_accent"]
        self.assertEqual(accent["state"],"on")
        self.assertEqual(accent["attributes"]["rgb_color"],[187,117,255])
        self.assertEqual(self.s.timeline(self.s.profile(),self.day)["energy"]["light.hs_demo_accent"]["kwh"],.115)
        self.assertEqual(self.hass.services.calls,[])

    async def test_all_week_cover_does_not_repeat_daily_travel(self):
        self.s.profile()["rows"]["cover.hs_demo_blind"]["days"]=["f"*24]*7
        self.s.cache.clear()
        self.assertEqual(self.s.timeline(self.s.profile(),self.day)["energy"]["cover.hs_demo_blind"]["kwh"],0)

    async def test_cover_motor_energy_crossing_midnight_is_split_between_days(self):
        cover = "cover.hs_demo_blind"
        self.s.device(cover)["travel_seconds"] = 600
        self.s.profile()["rows"][cover]["use"] = False
        self.s.device("scene.hs_demo_evening")["effects"] = {cover:{"position":100}}
        self.s.device("scene.hs_demo_goodnight")["effects"] = {cover:{"position":0}}
        timeline_mod = importlib.import_module(target.__name__ + ".timeline")
        with patch.object(timeline_mod, "scene_markers", side_effect=lambda row, entity, *args:
                          [1439] if entity.endswith("evening") else [360]):
            timeline = self.s.timeline(self.s.profile(),self.day)
        # 540 seconds carried in + 600 seconds closing + 60 carried out.
        self.assertAlmostEqual(timeline["energy"][cover]["kwh"],8*1200/3600000,places=6)
        self.assertEqual(timeline["movements"][cover][0],{"minute":0,"seconds":540})

    async def test_full_day_energy_and_fountain(self):
        energy=self.s.timeline(self.s.profile(),self.day)["energy"]
        self.assertEqual(energy["switch.hs_demo_aquarium"]["kwh"],.144)
        self.assertEqual(energy["switch.hs_demo_fountain"]["kwh"],.21)

    async def test_bulk_actions_are_scoped_and_select_skips_scenes(self):
        old=copy.deepcopy(self.s.profile()["rows"])
        await self.command(op="fill",entities=["light.hs_demo_living","scene.hs_demo_evening"],day=0,value=True)
        self.assertEqual(self.s.profile()["rows"]["light.hs_demo_living"]["days"][0],"f"*24)
        self.assertEqual(self.s.profile()["rows"]["scene.hs_demo_evening"],old["scene.hs_demo_evening"])
        self.assertEqual(self.s.profile()["rows"]["switch.hs_demo_fountain"],old["switch.hs_demo_fountain"])
        await self.command(op="fill",entities=["scene.hs_demo_evening"],day=0,value=False)
        self.assertEqual(self.s.profile()["rows"]["scene.hs_demo_evening"]["days"][0],mathmod.ZERO)

    async def test_view_and_binding_edits_send_no_actions_when_armed(self):
        await self.bind("light.hs_demo_living","light.real")
        await self.command(op="settings",physical=True)
        self.hass.services.calls.clear()
        await self.command(op="view",shown_types=["fan","cover"],hidden_devices=["light.hs_demo_living"])
        await self.command(op="device",entity="light.hs_demo_living",target="")
        self.assertEqual(self.hass.services.calls,[])
        self.assertTrue(self.s.profile()["rows"]["light.hs_demo_living"]["use"])

    async def test_invalid_command_rolls_back_without_operating(self):
        prior=copy.deepcopy(self.s.data)
        for data in ({"op":"settings","physical":"false"},
                     {"op":"settings","physical":True,"speed":3},
                     {"op":"device","entity":"light.hs_demo_living","target":"climate.real"},
                     {"op":"row","entity":"light.hs_demo_living","on":{"brightness":0}},
                     {"op":"row","entity":"light.hs_demo_living","watts":float("nan")},
                     {"op":"view","shown_types":["climate"]}):
            with self.assertRaises(ha.exceptions.HomeAssistantError):
                await self.command(**data)
            self.assertEqual(self.s.data,prior)
        self.assertEqual(self.hass.services.calls,[])

    async def test_binding_validation_and_duplicate_targets(self):
        await self.bind("light.hs_demo_living","switch.real")
        with self.assertRaises(ha.exceptions.HomeAssistantError):
            await self.command(op="device",entity="switch.hs_demo_fountain",target="switch.real")
        self.assertEqual(self.s.device("switch.hs_demo_fountain")["target"],"")

    async def test_preview_scene_effects_cannot_escape_catalog(self):
        with self.assertRaises(ha.exceptions.HomeAssistantError):
            await self.command(op="device",entity="scene.hs_demo_evening",effects={"light.somewhere_else":{"state":"on"}})
        with self.assertRaises(ha.exceptions.HomeAssistantError):
            await self.command(op="device",entity="scene.hs_demo_evening",effects={"scene.hs_demo_goodnight":{"state":"on"}})

    async def test_model_save_persists_revision_without_device_calls(self):
        await self.bind("light.hs_demo_living","light.real")
        await self.command(op="settings",physical=True)
        self.hass.services.calls.clear()
        config={"type":"custom:floor3dx-card","path":"/local/demo/","objfile":"demo.glb"}
        await self.command(op="renderer",config=config,expected_revision=0)
        self.assertEqual(self.s.store.saved["renderer_revision"],1)
        self.assertEqual(self.hass.services.calls,[])
        with self.assertRaises(ha.exceptions.HomeAssistantError):
            await self.command(op="renderer",config=config,expected_revision=0)

    async def test_add_remove_devices_and_preserve_other_rows(self):
        old=copy.deepcopy(self.s.profile()["rows"]["light.hs_demo_living"])
        await self.command(op="add_device",kind="fan",name="New fan")
        device=self.s.devices[-1]
        self.assertIn(device["entity"],self.s.profile()["rows"])
        self.assertEqual(self.s.profile()["rows"]["light.hs_demo_living"],old)
        await self.command(op="remove_device",entity=device["entity"])
        self.assertNotIn(device["entity"],self.s.ids)
        self.assertEqual(self.hass.services.calls,[])

    async def test_scene_referenced_device_cannot_be_removed(self):
        with self.assertRaises(ha.exceptions.HomeAssistantError):
            await self.command(op="remove_device",entity="light.hs_demo_accent")

    async def test_restart_preserves_settings_and_disarms_physical(self):
        await self.command(op="view",shown_types=["cover"])
        await self.command(op="row",entity="fan.hs_demo_ceiling",on={"percentage":37})
        await self.command(op="settings",physical=True,clock=True)
        saved=copy.deepcopy(self.s.store.saved)
        new=target.Scheduler(self.hass)
        new.store.saved=saved
        await new.load()
        self.assertEqual(new.data["shown_types"],["cover"])
        self.assertEqual(new.profile()["rows"]["fan.hs_demo_ceiling"]["on"]["percentage"],37)
        self.assertFalse(new.data["physical"])

    async def test_conditional_profiles_and_copy_clone(self):
        self.hass.states.async_set("input_select.home_scheduler_mode","Guest")
        await self.command(op="settings",clock=True,auto=True)
        self.assertEqual(self.s.context()[0]["id"],"guest")
        await self.command(op="settings",clock=False)
        await self.command(op="clone")
        self.assertEqual(len(self.s.data["profiles"]),5)
        self.assertEqual(self.s.profile()["condition_entity"],"")
        await self.command(op="cell",entity="light.hs_demo_living",day=0,slot=3,value=True)
        await self.command(op="copy_day",day=0)
        self.assertEqual(len(set(self.s.profile()["rows"]["light.hs_demo_living"]["days"])),1)


class AssetTests(unittest.TestCase):
    def test_glb_is_self_contained_and_every_model_mapping_exists(self):
        folder=ha.ROOT/"custom_components/home_scheduler/frontend"
        raw=(folder/"demo-home.glb").read_bytes()
        magic,version,size=struct.unpack_from("<III",raw)
        self.assertEqual((magic,version,size),(0x46546c67,2,len(raw)))
        length,tag=struct.unpack_from("<II",raw,12)
        model=json.loads(raw[20:20+length])
        self.assertTrue(all("uri" not in b for b in model["buffers"]))
        self.assertTrue(all("uri" not in image for image in model["images"]))
        self.assertTrue(all(not set(n)&{"translation","scale","rotation","matrix"} for n in model["nodes"]))
        names={n["name"] for n in model["nodes"]}
        config=json.loads((folder/"demo-home.json").read_text())
        for entry in config["entities"]:
            self.assertIn(entry["object_id"],names)
        self.assertGreater(len(names),40)


if __name__ == "__main__":
    unittest.main()
