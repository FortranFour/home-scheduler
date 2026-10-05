"""Validate public repository layout, bundled assets, and release metadata."""
import json
import re
import struct
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[1]
COMPONENT=ROOT/"custom_components/home_scheduler"
manifest=json.loads((COMPONENT/"manifest.json").read_text())
assert list(manifest)==["domain","name",*sorted(set(manifest)-{"domain","name"})],"Use hassfest manifest key order"
version=manifest["version"]
assert re.fullmatch(r"\d+\.\d+\.\d+",version),"Use a matching three-part release version"
assert [p.name for p in (ROOT/"custom_components").iterdir() if p.is_dir()]==["home_scheduler"]
for key in ("domain","documentation","issue_tracker","codeowners","name","version"):
    assert manifest.get(key),f"Missing HACS manifest field: {key}"
assert manifest["config_flow"] and manifest["single_config_entry"]
assert set(manifest["dependencies"]) >= {"http","frontend"}
assert (COMPONENT/"config_flow.py").is_file()
hacs=json.loads((ROOT/"hacs.json").read_text())
assert hacs["render_readme"] and hacs["homeassistant"]=="2026.3.0"
assert json.loads((COMPONENT/"strings.json").read_text())==json.loads((COMPONENT/"translations/en.json").read_text())
for name in ("README.md","LICENSE","CHANGELOG.md","RELEASE_NOTES.md","PUBLISH_GIT_BASH.md"):
    assert (ROOT/name).is_file(),f"Missing release document: {name}"
for name in ("icon.png","icon@2x.png","dark_icon.png","dark_icon@2x.png","logo.png","logo@2x.png","dark_logo.png","dark_logo@2x.png"):
    raw=(COMPONENT/"brand"/name).read_bytes()
    assert raw[:8]==b"\x89PNG\r\n\x1a\n",f"Not a PNG: {name}"
    width,height=struct.unpack(">II",raw[16:24])
    if "icon" in name: assert width==height==(512 if "@2x" in name else 256)
frontend=COMPONENT/"frontend"
for name in ("home-scheduler-card.js","demo-home.glb","demo-home.json","models.json","icon.svg"):
    assert (frontend/name).is_file(),f"Asset must live inside the integration: {name}"
assert json.loads((frontend/"models.json").read_text())=={"models":[]},"Do not ship personal presets"
demo=json.loads((frontend/"demo-home.json").read_text())
assert demo["path"]=="/home_scheduler/" and demo["objfile"]=="demo-home.glb"
for name in ("const.py","manifest.json","frontend/home-scheduler-card.js"):
    assert version in (COMPONENT/name).read_text(),f"Version mismatch: {name}"
for name in ("home_scheduler_view.yaml","install.sh","tools/build_demo.py"):
    assert version in (ROOT/name).read_text(),f"Version mismatch: {name}"
for p in ROOT.rglob("*.json"):
    if "node_modules" not in p.parts: json.loads(p.read_text())
for p in [*ROOT.rglob("*.yaml"),*ROOT.rglob("*.yml")]:
    if "node_modules" not in p.parts: yaml.load(p.read_text(),Loader=yaml.BaseLoader)
package=yaml.load((ROOT/"packages/home_scheduler.yaml").read_text(),Loader=yaml.BaseLoader)
assert "frontend" not in package,"The integration registers its own module; avoid duplicate preview resources"
assert not any(p.name in ("home_scheduler_my_house.json","my-house.json","secrets.yaml") for p in ROOT.rglob("*") if p.is_file())
print(f"Release {version} checks passed: one HACS integration, metadata, bundled assets, branding, documents, and public demo.")
