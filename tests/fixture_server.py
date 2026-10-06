"""Local browser-test bridge into the real backend; never installed in HA."""
import asyncio
import json
import types
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from ha_stubs import hass_fixture, target
from ha_stubs import dt

loop = asyncio.new_event_loop()
hass = hass_fixture()
for entity,attrs in {
    "light.fixture_living":{"friendly_name":"Imported living lamp","supported_color_modes":["rgb"],"brightness":0},
    "switch.fixture_wall":{"friendly_name":"Imported kitchen lamps"},
    "fan.fixture_ceiling":{"friendly_name":"Imported fan","supported_features":1,"percentage":0},
    "cover.fixture_blind":{"friendly_name":"Imported blind","device_class":"blind","current_position":0},
    "binary_sensor.fixture_door":{"friendly_name":"Door"},
    "climate.fixture_room":{"friendly_name":"Thermostat"},
}.items():
    hass.states.async_set(entity,"off",attrs)
scheduler = target.Scheduler(hass)
loop.run_until_complete(scheduler.load())
scheduler.data.update(date="2026-10-05", minute=720)
loop.run_until_complete(scheduler.apply())


def snapshot():
    return {"states": {entity: {"entity_id": entity, "state": value.state,
                               "attributes": value.attributes}
                       for entity, value in hass.states.values.items()},
            "calls": hass.services.calls}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(snapshot())

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try:
            if self.path == "/reset":
                scheduler.store.saved = None
                scheduler.learning.store.saved = None
                scheduler.cache.clear()
                loop.run_until_complete(scheduler.load())
                scheduler.data.update(date="2026-10-05", minute=720)
                loop.run_until_complete(scheduler.apply())
                hass.services.calls.clear()
            elif self.path == "/legacy":
                hass.states.async_set("sensor.lighting_scheduler","Lighting scheduler",data)
            elif self.path == "/learning":
                response=loop.run_until_complete(scheduler.learning.command(types.SimpleNamespace(data=data)))
                self.reply({**snapshot(),"response":response})
                return
            elif self.path == "/learning-fixture":
                # Fictional six-week actual-use observations for browser checks.
                from importlib import import_module
                learning=import_module(target.__name__+".learning")
                selected=[d for d in scheduler.devices if d["kind"] in ("light","switch","fan")]
                for index,d in enumerate(selected):
                    d["target"]=d["kind"]+".fixture_observed_"+str(index)
                    hass.states.async_set(d["target"],"off",{"friendly_name":d["name"]})
                    for delta in range(1,43):
                        day=dt.now().date()-timedelta(days=delta)
                        start=dt.now().replace(year=day.year,month=day.month,day=day.day,hour=0,minute=0)
                        # Five Mondays ON, one OFF; only two Tuesdays for first lamp.
                        if index==0 and day.weekday()==1 and delta>14: continue
                        for slot in range(96):
                            on=72<=slot<84 and not (day.weekday()==0 and delta>35)
                            at=start.timestamp()+slot*900
                            learning.add_interval(scheduler.learning.data["records"],d["target"],at,at+900,
                                                  "on" if on else "off",dt.now().tzinfo)
                scheduler.learning.data.update(entities=[d["entity"] for d in selected if d["kind"]=="light"])
                if data.get("arm"):
                    scheduler.data.update(physical=True,clock=True)
                loop.run_until_complete(scheduler.apply(control=False))
            else:
                loop.run_until_complete(scheduler.command(types.SimpleNamespace(data=data)))
            self.reply(snapshot())
        except Exception as error:
            self.reply({"error": str(error)}, 400)


server = HTTPServer(("127.0.0.1", 0), Handler)
print(json.dumps({"port": server.server_port}), flush=True)
server.serve_forever()
