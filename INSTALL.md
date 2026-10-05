# Install Home Scheduler & Simulator 0.3.0

Requires Home Assistant 2026.3+. The fictional demo is unlinked from real devices. For the 3D view/editor, install [FortranFour/floor3dx-card](https://github.com/FortranFour/floor3dx-card) 1.4.0+ separately.

## HACS

1. Add `https://github.com/FortranFour/home-scheduler` under **HACS → Custom repositories**, category **Integration**.
2. Download **Home Scheduler & Simulator**, then restart Home Assistant.
3. In **Settings → Devices & services → Add integration**, add **Home Scheduler & Simulator**. Existing YAML setup imports automatically.
4. Add a Manual dashboard card:

   ```yaml
   type: custom:home-scheduler-card
   model_editor: false
   ```

5. Reload the browser. No extra scheduler module/resource is needed. The separately installed floor3dx companion needs its own resource.

For operation without 3D, set `show_model: false` in the card. Use `home_scheduler_view.yaml` for a full-width panel view.

## Manual copy

Copy `custom_components/home_scheduler/` and all of its contents to `/config/custom_components/home_scheduler/`. Restart HA and add the integration through Settings as above. This route requires no YAML setup.

For the optional package/compatibility installer, copy the extracted `home-scheduler` folder into `/config`, then run in HA's Terminal & SSH app:

```sh
sh /config/home-scheduler/install.sh /config
```

Use your existing package include. If necessary, merge the following into `configuration.yaml` without duplicating its `homeassistant:` block:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

On HA OS/Supervised, check configuration and restart:

```sh
ha core check
ha core restart
```

The optional package includes YAML integration setup, the demo mode helper, and Recorder exclusions. The installer does not change `configuration.yaml`. It backs up replaced files and preserves saved schedules/private model files.

## Upgrade from 0.2.x

Preserve `.storage/home_scheduler` and your private model assets. Install the new component, remove the old scheduler's `frontend.extra_module_url` and any manual scheduler resource, keep the floor3dx resource, restart, and reload. Retained `home_scheduler:` YAML imports the integration entry automatically. The old `lighting_scheduler` remains independent.

See [README.md](README.md) for complete installation, migration, model import, grid editing, scheduling, scenes, physical control, and troubleshooting. See [PUBLISH_GIT_BASH.md](PUBLISH_GIT_BASH.md) for uploading this source repository from your PC.
