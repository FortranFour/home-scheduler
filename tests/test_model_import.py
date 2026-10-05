"""Automatic imports exercise real bindings, schedules, rollback and isolation."""
import copy
import json
import types
import unittest
from pathlib import Path

from ha_stubs import target, mathmod, mask, hass_fixture, ROOT


def model():
    return {"type":"custom:floor3dx-card", "name":"Test house", "path":"/local/test-house/",
            "objfile":"house.glb", "header":"no", "camera_position":{"x":4,"y":8,"z":12},
            "camera_target":{"x":0,"y":1,"z":2},
            "object_groups":[{"object_group":"lamps","objects":[{"object_id":"LampOne"}]}],
            "entities":[
                {"entity":"light.living", "object_id":"LampOne", "type3d":"light", "light":{"follow_entity":"yes"}},
                {"entity":"light.living", "object_id":"LampOne", "type3d":"color", "color_entity":"light.living"},
                {"entity":"switch.wall", "object_id":"LampTwo", "type3d":"light"},
                {"entity":"switch.wall_alias", "object_id":"LampThree", "type3d":"light"},
                {"entity":"fan.ceiling", "object_id":"FanBlades", "type3d":"rotate"},
                {"entity":"cover.curtain", "object_id":"Curtain", "type3d":"shade", "shade":{"top_entity":"cover.top"}},
                {"entity":"switch.pump", "object_id":"Water", "type3d":"hide"},
                {"entity":"scene.evening", "object_id":"SceneMarker", "type3d":"hide"},
                {"entity":"binary_sensor.door", "object_id":"Door", "type3d":"color"},
                {"entity":"climate.room", "object_id":"Thermostat", "type3d":"text"},
            ]}


def preset():
    return {"renderer":model(), "aliases":{"switch.wall_alias":"switch.wall"}}


class ModelImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hass=hass_fixture()
        for entity,attrs in {
            "light.living":{"friendly_name":"Living lamp","supported_color_modes":["rgb"]},
            "switch.wall":{"friendly_name":"Dining lamps"},
            "fan.ceiling":{"friendly_name":"Ceiling fan","supported_features":1},
            "cover.curtain":{"friendly_name":"Curtain","device_class":"curtain","current_position":0},
            "switch.pump":{"friendly_name":"Pump"},
            "scene.evening":{"friendly_name":"Evening"},
            "binary_sensor.door":{"friendly_name":"Door"},
            "climate.room":{"friendly_name":"Thermostat"},
        }.items():
            self.hass.states.async_set(entity,"off",attrs)
        self.s=target.Scheduler(self.hass)
        await self.s.load()

    async def command(self,**values):
        await self.s.command(types.SimpleNamespace(data=values))

    def imported(self,source):
        return next(d for d in self.s.devices if source in d.get("source_entities",[]))

    async def test_import_deduplicates_aliases_and_rewrites_all_device_references(self):
        original=preset()
        await self.command(op="import_model",source=original)
        self.assertEqual(len(self.s.devices),7)
        self.assertEqual(self.s.data["shown_types"],["light"])
        self.assertEqual(self.imported("switch.wall")["kind"],"light")
        self.assertEqual(self.imported("switch.wall")["entity"],self.imported("switch.wall_alias")["entity"])
        self.assertEqual(self.imported("light.living")["name"],"Living lamp")
        self.assertEqual(self.imported("cover.curtain")["device_class"],"curtain")
        self.assertEqual(self.imported("cover.top")["target"],"","Missing entities stay virtual")
        self.assertTrue(all(not self.s.profile()["rows"][d["entity"]]["use"] for d in self.s.devices))
        renderer=self.s.data["renderer"]
        self.assertEqual(renderer["camera_position"],original["renderer"]["camera_position"])
        self.assertEqual(renderer["object_groups"],original["renderer"]["object_groups"])
        self.assertEqual([e["object_id"] for e in renderer["entities"]],[e["object_id"] for e in original["renderer"]["entities"]])
        living=self.imported("light.living")["entity"]
        self.assertEqual(renderer["entities"][1]["color_entity"],living)
        self.assertEqual(renderer["entities"][5]["shade"]["top_entity"],self.imported("cover.top")["entity"])
        self.assertEqual(renderer["entities"][-2:],[original["renderer"]["entities"][-2],original["renderer"]["entities"][-1]])
        self.assertEqual(self.s.data["last_import"]["readonly"],1)
        self.assertEqual(self.s.data["last_import"]["thermostats"],1)
        self.assertEqual(self.hass.services.calls,[])
        self.assertNotIn("device_memory",self.hass.states.get("sensor.home_scheduler").attributes)

    async def test_armed_import_disarms_pauses_and_never_operates_physical_devices(self):
        await self.command(op="device",entity="light.hs_demo_living",target="light.living")
        await self.command(op="settings",physical=True,clock=True)
        self.s.playing=True
        before={e:(v.state,copy.deepcopy(v.attributes)) for e,v in self.hass.states.values.items() if not e.startswith("sensor.home_scheduler")}
        count=len(self.hass.services.calls)
        await self.command(op="import_model",source=preset())
        self.assertFalse(self.s.data["physical"])
        self.assertFalse(self.s.data["clock"])
        self.assertFalse(self.s.playing)
        self.assertEqual(len(self.hass.services.calls),count)
        for entity,(state,attrs) in before.items():
            self.assertEqual((self.hass.states.get(entity).state,self.hass.states.get(entity).attributes),(state,attrs))
        living=self.imported("light.living")["entity"]
        await self.command(op="fill",entities=[living],day=0,value=True)
        await self.command(op="settings",date="2026-10-05",minute=1080)
        self.assertEqual(self.hass.states.get("sensor.home_scheduler_frame").attributes["states"][living]["state"],"on")
        self.assertEqual(len(self.hass.services.calls),count)

    async def test_existing_lighting_schedules_copy_and_reimport_preserves_user_edits(self):
        source_plan={"profiles":[{"id":"weekly","name":"My weekly schedule","rows":{
            "light.living":{"use":True,"days":[mask(72,80)]*7},
            "switch.wall":{"use":True,"days":[mask(80,84)]*7}}}],
            "watts":{"light.living":12.5},"random":{"light.living":True},
            "profile":"weekly","date":"2026-10-05","jitter":7,"seed":9}
        await self.command(op="import_model",source=preset(),source_plan=source_plan)
        living=self.imported("light.living")["entity"]
        self.assertEqual(self.s.profile()["name"],"My weekly schedule")
        self.assertEqual(self.s.profile()["rows"][living]["days"],[mask(72,80)]*7)
        self.assertEqual(self.s.data["watts"][living],12.5)
        self.assertTrue(self.s.data["random"][living])
        self.assertEqual(self.s.data["last_import"]["schedule_rows_copied"],2)
        await self.command(op="row",entity=living,watts=15)
        await self.command(op="range",entity=living,day=0,start=0,end=95,value=False)
        await self.command(op="profile",profile="weekly",name="Edited here")
        await self.command(op="import_model",source=preset(),source_plan=source_plan)
        self.assertEqual(self.s.profile()["name"],"Edited here")
        self.assertEqual(self.s.profile()["rows"][living]["days"][0],mathmod.ZERO)
        self.assertEqual(self.s.data["watts"][living],15)
        self.assertEqual(self.s.data["last_import"]["schedule_rows_copied"],0)

    async def test_switching_models_restores_catalog_and_masks_after_restart(self):
        await self.command(op="range",entity="light.hs_demo_living",day=0,start=5,end=9,value=True)
        demo_mask=self.s.profile()["rows"]["light.hs_demo_living"]["days"][0]
        await self.command(op="import_model",source=preset())
        living=self.imported("light.living")["entity"]
        await self.command(op="fill",entities=[living],day=0,value=True)
        other=target.Scheduler(self.hass,copy.deepcopy(target.DEFAULT_DEVICES))
        other.store=self.s.store
        await other.load()
        self.assertEqual(other.devices,self.s.devices,"Imported model wins over static device YAML")
        await self.command(op="import_model",source=json.loads((ROOT/"custom_components/home_scheduler/frontend/demo-home.json").read_text()),demo=True)
        self.assertEqual(len(self.s.devices),16)
        self.assertEqual(self.s.profile()["rows"]["light.hs_demo_living"]["days"][0],demo_mask)
        await self.command(op="import_model",source=preset())
        self.assertEqual(self.imported("light.living")["entity"],living)
        self.assertEqual(self.s.profile()["rows"][living]["days"][0],"f"*24)

    async def test_native_editor_save_populates_new_references_without_losing_unmapped_rows(self):
        config=json.loads((ROOT/"custom_components/home_scheduler/frontend/demo-home.json").read_text())
        config["entities"].append({"entity":"light.living","object_id":"ExtraLamp","type3d":"light"})
        await self.command(op="renderer",config=config,expected_revision=0)
        self.assertEqual(len(self.s.devices),17)
        self.assertEqual(self.s.data["renderer"]["entities"][-1]["entity"],self.imported("light.living")["entity"])
        self.assertIn("scene.hs_demo_evening",self.s.ids,"Unmapped scene rows remain")
        self.assertEqual(self.hass.services.calls,[])

    async def test_yaml_import_keeps_renderer_yes_no_and_scene_on_off_as_strings(self):
        text='''renderer:
  type: custom:floor3dx-card
  name: YAML home
  path: /local/test-house/
  objfile: house.glb
  header: no
  entities:
    - entity: light.living
      object_id: Lamp
      type3d: light
      light:
        follow_entity: yes
devices:
  - entity: light.living
    kind: light
    name: Lamp
    use: false
'''
        await self.command(op="import_model",source=text)
        self.assertEqual(self.s.data["renderer"]["header"],"no")
        self.assertEqual(self.s.data["renderer"]["entities"][0]["light"]["follow_entity"],"yes")
        self.assertFalse(self.s.profile()["rows"][self.s.devices[0]["entity"]]["use"])

    async def test_invalid_imports_roll_back_model_rows_and_physical_state(self):
        variants=["house.glb","x: !secret model",{"renderer":model(),"aliases":{"switch.wall":"switch.wall_alias","switch.wall_alias":"switch.wall"}},
                  {"views":[{"cards":[model(),model()]}]},"x"*524289,
                  {"renderer":model(),"source_plan":{"profiles":[{"id":"new","rows":{"light.living":{"days":["bad"]*7}}}]}}]
        for source in variants:
            before=copy.deepcopy(self.s.data)
            with self.assertRaises(Exception):
                await self.command(op="import_model",source=source)
            self.assertEqual(self.s.data,before)
        with self.assertRaisesRegex(Exception,"another card"):
            await self.command(op="import_model",source=preset(),expected_revision=3)
        self.assertEqual(self.hass.services.calls,[])

    async def test_metadata_supplements_unmodeled_lights_and_virtual_scene_effects(self):
        source=preset()
        source["devices"]=[{"entity":"light.unmodeled","name":"Unmodeled lamp","kind":"light"},
                           {"entity":"scene.evening","name":"Evening","kind":"scene","effects":{"light.living":{"state":"on","brightness":45}}}]
        await self.command(op="import_model",source=source)
        self.assertEqual(len(self.s.devices),8)
        self.assertEqual(self.imported("light.unmodeled")["target"],"")
        self.assertEqual(set(self.imported("scene.evening")["effects"]),{self.imported("light.living")["entity"]})
        self.assertEqual(self.hass.services.calls,[])
