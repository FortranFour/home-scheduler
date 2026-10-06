"""Exercise the installer against an isolated HA-like configuration."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_upgrade_preserves_custom_package_and_learning_store(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)
            (config/"configuration.yaml").write_text("homeassistant:\n")
            package=config/"packages/home_scheduler.yaml"
            package.parent.mkdir()
            package.write_text("home_scheduler:\nautomation:\n  - alias: Resume my schedules\n    mode: single\n")
            store=config/".storage/home_scheduler_learning"
            store.parent.mkdir()
            store.write_text('{"observations":"private fixture"}')
            prior=(package.read_bytes(),store.read_bytes())
            subprocess.run(["sh",str(ROOT/"install.sh"),str(config)],check=True,capture_output=True)
            self.assertEqual((package.read_bytes(),store.read_bytes()),prior)

    def test_install_and_reinstall_preserve_unrelated_files_and_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config with spaces"
            originals = {
                "configuration.yaml": "homeassistant:\n  packages: !include_dir_named packages\n",
                "packages/lighting_scheduler.yaml": "lighting_scheduler:\n",
                "custom_components/lighting_scheduler/__init__.py": "original integration\n",
                "www/my_house.glb": "private model bytes",
                ".storage/lighting_scheduler": '{"old":true}',
                ".storage/home_scheduler": '{"saved":"keep preview settings"}',
            }
            for relative, contents in originals.items():
                filename = config / relative
                filename.parent.mkdir(parents=True, exist_ok=True)
                filename.write_text(contents)
            def hashes():
                return {relative:hashlib.sha256((config/relative).read_bytes()).hexdigest()
                        for relative in originals}
            before = hashes()
            for _ in range(2):
                subprocess.run(["sh", str(ROOT/"install.sh"), str(config)], check=True, capture_output=True)
                self.assertEqual(hashes(), before)
                self.assertTrue((config/"www/home-scheduler/demo-home.glb").is_file())
                self.assertTrue((config/"custom_components/home_scheduler/manifest.json").is_file())
                for name in ("icon.png","icon@2x.png","dark_icon.png","dark_icon@2x.png",
                             "logo.png","logo@2x.png","dark_logo.png","dark_logo@2x.png"):
                    self.assertEqual((config/"custom_components/home_scheduler/brand"/name).read_bytes(),
                                     (ROOT/"custom_components/home_scheduler/brand"/name).read_bytes())
                self.assertEqual((config/"packages/home_scheduler.yaml").read_bytes(),
                                 (ROOT/"packages/home_scheduler.yaml").read_bytes())
            backups = list((config/"home_scheduler_backups").iterdir())
            self.assertEqual(len(backups), 1)
            self.assertTrue((backups[0]/"component/manifest.json").is_file())
            self.assertTrue((backups[0]/"frontend/demo-home.glb").is_file())
            self.assertTrue((backups[0]/"package.yaml").is_file())

    def test_wrong_directory_is_rejected_without_creating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(["sh", str(ROOT/"install.sh"), directory], capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_multi_model_index_and_private_assets_survive_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)
            (config/"configuration.yaml").write_text("homeassistant:\n")
            frontend=config/"www/home-scheduler"
            frontend.mkdir(parents=True)
            models={"models":[
                {"name":"Example A","url":"/local/example-a/model.json"},
                {"name":"Example B","url":"/local/example-b/model.json"}]}
            index=frontend/"models.json"
            index.write_text(json.dumps(models,indent=2))
            original=index.read_bytes()
            private=frontend/"my-house.json"
            private.write_text('{"renderer":{"name":"Private fixture"}}')
            for _ in range(2):
                subprocess.run(["sh",str(ROOT/"install.sh"),str(config)],check=True,capture_output=True)
                self.assertEqual(index.read_bytes(),original)
                self.assertEqual(private.read_text(),'{"renderer":{"name":"Private fixture"}}')

    def test_optional_personal_preset_is_indexed_and_preserved_on_update(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)
            (config/"configuration.yaml").write_text("homeassistant:\n")
            preset={"renderer":{"name":"Private home","path":"/local/my-house/","objfile":"home.glb"},"devices":[]}
            (config/"home_scheduler_my_house.json").write_text(json.dumps(preset))
            subprocess.run(["sh",str(ROOT/"install.sh"),str(config)],check=True,capture_output=True)
            installed=config/"www/home-scheduler/my-house.json"
            self.assertEqual(json.loads(installed.read_text()),preset)
            index=config/"www/home-scheduler/models.json"
            self.assertEqual(json.loads(index.read_text())["models"][0]["url"],"/local/home-scheduler/my-house.json")
            (config/"home_scheduler_my_house.json").unlink()
            subprocess.run(["sh",str(ROOT/"install.sh"),str(config)],check=True,capture_output=True)
            self.assertEqual(json.loads(installed.read_text()),preset)
            self.assertEqual(len(json.loads(index.read_text())["models"]),1)
