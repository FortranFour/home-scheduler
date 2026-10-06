"""Exercise the installed HACS entry lifecycle and YAML upgrade path."""
import asyncio
import importlib
import tempfile
import types
import unittest
from pathlib import Path

from ha_stubs import target,hass_fixture


class Entry:
    def __init__(self):
        self.unsub=[]
    def async_on_unload(self,callback):
        self.unsub.append(callback)


def lifecycle_hass(config_dir):
    hass=hass_fixture()
    hass.data={};hass.modules=set();hass.is_running=False
    hass.config=types.SimpleNamespace(path=lambda rel:str(Path(config_dir)/rel))
    hass.paths=[];hass.listeners=[];hass.flows=[];hass.pending=[]
    async def register(paths): hass.paths.extend(paths)
    hass.http=types.SimpleNamespace(async_register_static_paths=register)
    async def executor(fn,*args): return fn(*args)
    hass.async_add_executor_job=executor
    async def init(domain,**kw): hass.flows.append((domain,kw))
    hass.config_entries=types.SimpleNamespace(flow=types.SimpleNamespace(async_init=init))
    def task(coro):
        value=asyncio.create_task(coro);hass.pending.append(value);return value
    hass.async_create_task=task
    hass.async_create_background_task=lambda coro,name:asyncio.create_task(coro,name=name)
    def listen(event,handler):
        token=(event,handler);hass.listeners.append(token)
        return lambda:hass.listeners.remove(token) if token in hass.listeners else None
    hass.bus=types.SimpleNamespace(async_listen_once=listen)
    return hass


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_hacs_entry_serves_assets_registers_card_and_unloads_without_device_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            hass=lifecycle_hass(directory);entry=Entry()
            self.assertTrue(await target.async_setup(hass,{}))
            self.assertEqual(hass.flows,[])
            self.assertTrue(await target.async_setup_entry(hass,entry))
            scheduler=hass.data[target.DOMAIN]["scheduler"]
            self.assertIn("/home_scheduler/home-scheduler-card.js?v=0.4.0",hass.modules)
            self.assertEqual(hass.paths[0].url_path,"/home_scheduler")
            self.assertTrue((Path(hass.paths[0].path)/"demo-home.glb").is_file())
            self.assertIn((target.DOMAIN,"command"),hass.services.registered)
            self.assertIn((target.DOMAIN,"learning"),hass.services.registered)
            self.assertFalse(scheduler.data["physical"])
            self.assertIsNotNone(hass.states.get("sensor.home_scheduler_frame"))
            self.assertTrue(await target.async_setup_entry(hass,entry))
            self.assertIs(hass.data[target.DOMAIN]["scheduler"],scheduler)
            self.assertEqual(len(hass.paths),1)
            self.assertTrue(await target.async_unload_entry(hass,entry))
            for callback in entry.unsub: callback()
            self.assertEqual(hass.modules,set())
            self.assertEqual(hass.listeners,[])
            self.assertNotIn((target.DOMAIN,"command"),hass.services.registered)
            self.assertNotIn((target.DOMAIN,"learning"),hass.services.registered)
            self.assertIsNone(hass.states.get("sensor.home_scheduler"))
            self.assertEqual(hass.services.calls,[])
            self.assertIsNotNone(scheduler.store.saved)
            # Static routes survive unload/reload and are not registered twice.
            await target.async_setup_entry(hass,Entry())
            self.assertEqual(len(hass.paths),1)
            await target.async_unload_entry(hass,entry)

    async def test_existing_yaml_imports_config_entry_and_preserves_custom_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            hass=lifecycle_hass(directory)
            devices=[{"entity":"switch.custom_pump","name":"Pump","kind":"switch"}]
            await target.async_setup(hass,{target.DOMAIN:{"devices":devices}})
            await asyncio.gather(*hass.pending)
            self.assertEqual(hass.flows,[(target.DOMAIN,{"context":{"source":"import"},"data":{}})])
            await target.async_setup_entry(hass,Entry())
            self.assertEqual([d["entity"] for d in hass.data[target.DOMAIN]["scheduler"].devices],["switch.custom_pump"])
            await target.async_unload_entry(hass,Entry())

    async def test_legacy_personal_index_gets_a_specific_route_before_bundled_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            index=Path(directory)/"www/home-scheduler/models.json"
            index.parent.mkdir(parents=True);index.write_text('{"models":[]}')
            hass=lifecycle_hass(directory)
            await target.async_setup_entry(hass,Entry())
            self.assertEqual([p.url_path for p in hass.paths],["/home_scheduler/user-models.json","/home_scheduler"])
            self.assertEqual(Path(hass.paths[0].path),index)
            self.assertFalse(hass.paths[0].cache_headers)
            self.assertEqual(hass.states.get("sensor.home_scheduler").attributes["model_presets_url"],"/home_scheduler/user-models.json")
            await target.async_unload_entry(hass,Entry())

    async def test_running_entry_starts_one_loop_and_unload_awaits_its_cancellation(self):
        with tempfile.TemporaryDirectory() as directory:
            hass=lifecycle_hass(directory);hass.is_running=True
            await target.async_setup_entry(hass,Entry())
            scheduler=hass.data[target.DOMAIN]["scheduler"]
            task=scheduler.task
            self.assertIsNotNone(task)
            await scheduler.start()
            self.assertIs(scheduler.task,task)
            await target.async_unload_entry(hass,Entry())
            self.assertTrue(task.done())
            self.assertEqual(hass.services.calls,[])

    async def test_ui_flow_confirmation_creation_yaml_import_and_duplicate_abort(self):
        cls=importlib.import_module(target.__name__+".config_flow").HomeSchedulerConfigFlow
        flow=cls()
        self.assertEqual((await flow.async_step_user())["type"],"form")
        result=await flow.async_step_user({})
        self.assertEqual(result,{"type":"create_entry","title":"Home Scheduler & Simulator","data":{}})
        self.assertEqual(flow.unique_id,"home_scheduler")
        flow.entries=[object()]
        self.assertEqual(await flow.async_step_user(),{"type":"abort","reason":"already_configured"})
        self.assertEqual(await flow.async_step_import({}),{"type":"abort","reason":"already_configured"})
        self.assertEqual((await cls().async_step_import({}))["type"],"create_entry")
