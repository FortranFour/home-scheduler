# Home Scheduler & Simulator

Plan lights, switches and plugs, fans, blinds, curtains, other covers, and scene activations in a weekly quarter-hour grid. Play a day in an original fictional 3D home, select your own configured house model, or watch the simulated device indicators without 3D. Connect real devices when you want the same schedules to operate your home.

Version **0.3.0** · Home Assistant custom integration · MIT license

![Fictional demo home at night](previews/demo-night.png)

The scheduler card, demo model, and cyan house branding are included. The 3D renderer and its visual editor come from **[FortranFour/floor3dx-card](https://github.com/FortranFour/floor3dx-card)**, installed separately. Thermostats are not scheduled.

- [Install through HACS](#install-through-hacs)
- [Manual installation](#manual-installation)
- [Upgrade an existing manual installation](#upgrade-an-existing-manual-installation)
- [Add the dashboard card](#add-the-dashboard-card)
- [Preview and physical operation](#preview-and-physical-operation)
- [Edit the grid](#edit-the-grid)
- [Device settings and energy](#device-settings-and-energy)
- [Select or import your own model](#select-or-import-your-own-model)
- [Use the visual model editor](#use-the-visual-model-editor)
- [Schedules, conditions, and presence variation](#schedules-conditions-and-presence-variation)
- [Scenes](#scenes)
- [Storage, updates, and removal](#storage-updates-and-removal)
- [Troubleshooting](#troubleshooting)
- [Development and publishing](#development-and-publishing)

## Requirements

| Requirement | Purpose |
| --- | --- |
| Home Assistant **2026.3.0 or later** | Integration, scheduling, and local integration branding |
| An administrator account | Installation and scheduler commands |
| HACS, or access to `/config/custom_components` | Installation |
| floor3dx-card **1.4.0 or later** | Optional 3D view and native visual editor |
| A browser with WebGL | Optional 3D rendering |

Home Assistant is required even for simulation. The demo has no real device targets. A card with `show_model: false` uses the schedule grid and changing state indicators without loading floor3dx.

## Install through HACS

This repository can be installed as a **custom repository**. It is not automatically included in HACS's default catalog.

1. Open **HACS → menu → Custom repositories**.
2. Add `https://github.com/FortranFour/home-scheduler` with category **Integration**.
3. Find **Home Scheduler & Simulator** and download it.
4. **Restart Home Assistant**, then open **Settings → Devices & services → Add integration**.
5. Search for **Home Scheduler & Simulator** and confirm setup. An existing YAML installation imports its setup automatically; do not create a second instance.
6. For 3D, add `https://github.com/FortranFour/floor3dx-card` to HACS with category **Dashboard**, install version 1.4.0 or later, and follow that project's resource instructions. Keep an existing floor3dx resource rather than adding a duplicate.
7. Add the scheduler card as described below and reload the browser.

**No additional scheduler JavaScript/module resource is required.** The integration registers its own card and serves its files at `/home_scheduler/`. The floor3dx companion still needs its own installation/resource.

The icon and light/dark logos live in `custom_components/home_scheduler/brand/`. Home Assistant 2026.3+ supports these local custom-integration brand images. See the [official branding documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/).

## Manual installation

Copy the repository's `custom_components/home_scheduler` directory, including its `frontend`, `brand`, and `translations` subdirectories, to:

```text
/config/custom_components/home_scheduler/
```

Restart Home Assistant, add the integration in **Settings → Devices & services**, and add a dashboard card. A fresh UI installation does not require changes to `configuration.yaml`, a package include, or a scheduler resource entry.

For a terminal installation with the optional demo mode helper and Recorder exclusions, extract the distribution into `/config/home-scheduler` and run this **in Home Assistant's Terminal & SSH app**, not in your PC's Git Bash:

```sh
sh /config/home-scheduler/install.sh /config
```

The helper copies the integration and `packages/home_scheduler.yaml`. It also copies compatible assets to `www/home-scheduler/` for older installations and preserves a separate personal preset if present. It never edits `configuration.yaml`.

To load that optional package, add `packages:` under your existing `homeassistant:` block:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

If that include already exists, add nothing. Do not create duplicate `homeassistant:` or `packages:` keys. If your package directory uses a different name, put `home_scheduler.yaml` there. Do not paste the package contents into `configuration.yaml` as well. With packages enabled, YAML setup imports the integration entry automatically.

On Home Assistant OS/Supervised:

```sh
ha core check
ha core restart
```

Resolve configuration errors before restart. On a first custom-integration install, a warning that says only `Integration 'home_scheduler' not found` can reflect cached integration discovery: verify the component folder exists, restart fully, and check again. Container/Core users should use their normal configuration check and restart procedure.

See [INSTALL.md](INSTALL.md) for a short checklist. Repository upload commands are in [PUBLISH_GIT_BASH.md](PUBLISH_GIT_BASH.md).

## Upgrade an existing manual installation

Back up Home Assistant before replacing files. Preserve **`.storage/home_scheduler`** and your private GLB/OBJ, textures, and preset files.

1. Install the new component through HACS or replace `custom_components/home_scheduler` with this version.
2. Remove the old scheduler line under `frontend.extra_module_url`, such as `/local/home-scheduler/home-scheduler-card.js?v=0.2.1`. Remove any manually added Lovelace resource for that scheduler script too. **Keep the floor3dx resource.** The supplied optional package now contains no frontend resource.
3. Keep `home_scheduler:` YAML setup if you use it. It creates the same single integration entry automatically. Otherwise, add the integration through Settings after restarting.
4. Restart Home Assistant and hard-refresh the dashboard. Existing schedules, connections, and saved model configuration load from the same storage key.

An old dashboard `renderer_url` can be removed to use the bundled demo as the initial fallback. A previously saved model takes precedence over that fallback. User model files under `/local/` keep their URLs. A legacy `www/home-scheduler/models.json` preset index is made available to the new card at `/home_scheduler/user-models.json`; it is kept separate from the bundled empty index.

The independent `lighting_scheduler` integration remains separate. Its model and plans can be imported without changing its storage. If both integrations are installed, choose which one controls any overlapping physical devices.

## Add the dashboard card

Add a **Manual** card with:

```yaml
type: custom:home-scheduler-card
model_editor: false
```

Use a panel view for more room. The included `home_scheduler_view.yaml` is one complete view definition, suitable as an item under a dashboard's `views:` list:

```yaml
title: Home Simulator
path: home-simulator
icon: mdi:home-clock-outline
type: panel
cards:
  - type: custom:home-scheduler-card
    model_editor: false
```

For a grid and device indicators without 3D:

```yaml
type: custom:home-scheduler-card
show_model: false
```

| Card option | Default | Meaning |
| --- | --- | --- |
| `show_model` | `true` | Show the model, model selector, and optional editor |
| `model_editor` | `true` | Open the editor initially; the toolbar can toggle it |
| `renderer_url` | Bundled demo JSON | Initial model configuration URL; a saved model takes precedence |
| `renderer` | Unset | Initial inline floor3dx configuration; a saved model takes precedence |

All cards share one backend, selected model, device catalog, and schedules. They are not separate scheduler instances.

## Preview and physical operation

The first launch is paused at **6:30 PM**, with six light rows visible and a populated demo week. The sixteen fictional devices have blank real-entity connections and **Physical devices** is off.

Move the slider or press **Play** to run the day. At **1×**, one simulated hour passes per real second. Speeds range from ¼× to 4×. **Repeat preview** repeats the selected day. **Preview date** selects the weekday and seeds that day's presence variation. **Follow clock** uses Home Assistant's local date/time and takes over from playback.

| Physical devices | Follow clock | Behavior |
| --- | --- | --- |
| Off | Off | Slider/playback changes virtual device states only |
| Off | On | Simulate the current local day's schedule in real time |
| On | Off | Slider/playback also operates linked non-scene devices |
| On | On | Operate linked devices on the local clock; dispatch timed real scenes |

**Physical devices resets to off after every Home Assistant restart.** Model import pauses playback and turns both master controls off. Turning physical control off leaves actual devices at their current state. Blank connections stay virtual even when the master is on.

Simulation passes an isolated state object to the renderer. It does not overwrite actual entity states through Developer Tools. Read-only sensor/lock references in an imported model can still show their real state; they are not scheduled.

Try these demo times:

| Time | What to look for |
| --- | --- |
| 06:30 | Kitchen lighting and extractor fan on |
| 08:00 | Study blind raised, bedroom curtain retracted, garage open |
| 10:00 | Fountain running, study light on, garage closed |
| 14:00 | Ceiling fan spinning and patio shutter partly raised |
| 18:30 | Evening scene changes the accent light to purple |
| 20:30 | Bedroom light on, curtains closed, living fan running |
| 23:00 | Goodnight scene turns the accent light off |

The original demo has six lights, two switches, two fans, four covers, two scenes, and 79 named meshes. Label textures are embedded in its GLB. It contains no actual household entity IDs, private floorplan, address, photos, or credentials.

## Edit the grid

Each row has **96 checkboxes per day**, one for each 15-minute block. They are split into **AM and PM bands** so a row does not require 96 columns. A checked non-scene block applies that row's inside-period settings for the entire block; an unchecked block applies its outside-period behavior.

- **Enabled** determines whether a row's schedule runs in the selected profile.
- **Select all blocks** / **Clear all** above the grid affect the visible rows on the selected day. Each row also has its own select/clear buttons.
- Drag across a row: start on an unchecked cell to select a range, or a checked cell to clear it. Reverse dragging works too. Space toggles a focused checkbox.
- On touch screens, enable **Touch paint** to draw a range; disable it to scroll normally.
- Scene boxes are activation markers at the start of a block. Adjacent checked scene cells are separate events. Bulk select is disabled for scenes; clear still works.
- Click weekday buttons to edit other days. **Copy day to week** copies the selected day's cells to every weekday in the current profile, including hidden rows.

Lights appear by default. Toggle the **Lights**, **Switches / plugs**, **Fans**, **Covers**, and **Scenes** category checkboxes to control the list's length. In **Devices, connections & row visibility**, uncheck **Include row** to hide an individual device.

**Hiding a row does not disable its schedule.** Hidden devices continue to run and appear in the model. Use **Enabled** to suspend their schedule. Wattage and randomization flags belong to the device across profiles; enabled flags, cells, and behavior settings belong to each profile.

## Device settings and energy

Open a row's **Settings & connection**:

| Type | Inside checked periods | Outside checked periods | Daily estimate |
| --- | --- | --- | --- |
| Light | On, brightness, color | Off, leave unchanged, or restore prior state | Watts × simulated on-hours ÷ 1000 |
| Switch/plug | On | Off, leave unchanged, or restore prior state | Watts × simulated on-hours ÷ 1000 |
| Fan | On, speed percentage | Off, leave unchanged, or restore prior state | Watts × simulated on-hours ÷ 1000 |
| Cover | Position from 0% closed to 100% open | Outside position, leave unchanged, or restore prior position | Motor watts × estimated motion-hours ÷ 1000 |
| Scene | Activate at each marker | No off state | Event count; no separate energy consumption |

Enter the device's wattage at the end of its row. For covers, enter **Full travel seconds** for a complete 0–100% movement (1–600 seconds). Estimated motor energy scales with distance moved and apportions travel across midnight. A stationary open cover does not consume estimated motor energy. Light/fan estimates use the entered watts without automatically scaling for brightness/speed. These are planning estimates rather than meter readings.

**Leave unchanged** retains the preceding simulated state until a later schedule edge or preview scene changes it. **Restore prior state** returns to the state captured at entry to a checked period. Simulation resolves the preceding weekly cycle deterministically and does not read real devices to establish its baseline. Captured physical restore states are held in memory and do not survive a restart.

Imported models automatically connect entities that exist in Home Assistant. For a new or unlinked row, enter **Real entity (optional)**. A real entity can be connected to only one row:

| Row type | Accepted real entity domains |
| --- | --- |
| Light | `light`, or `switch` for a switched lamp |
| Switch/plug | `switch` |
| Fan | `fan`, or `switch` for on/off control |
| Cover | `cover`, including blinds, curtains, shutters, and garage doors |
| Scene | `scene` |

Brightness/color, fan speed, and intermediate cover positions are sent only when supported by the real entity. Switch targets receive on/off commands. For a cover without position support, use 0% or 100%. Unknown/unavailable targets are skipped and reported.

Use **Add device** in the device manager for an additional supported type. It creates a preview ID and blank schedules in every profile; its category becomes visible. Bind that preview ID to a model object in the visual editor if desired. Thermostats and sensor-only devices do not become schedulable rows.

## Select or import your own model

Choose a configuration from **Model**, or use **Import configuration…** to select one floor3dx card as JSON or plain YAML. Selection automatically:

1. Creates device rows from supported entity references and retains useful names/types.
2. Connects entities already present in Home Assistant; missing entities remain virtual.
3. Rewrites schedulable renderer bindings to independent preview IDs.
4. Retains mesh/object bindings, groups, camera, colors, and other renderer settings.
5. Shares one row for repeated references to the same device; optional aliases can merge differently named references.

New rows start disabled with blank schedules. Existing Lighting Scheduler rows can bring their saved schedules and enabled flags across. Reimport preserves edits already made in Home Scheduler. Switching between the demo and a previously imported house restores each model's catalog and schedule cells. Up to **128** schedulable devices are supported.

![Automatic model import](previews/model-import.png)

**Find models** refreshes configured floor3dx cards in saved Home Assistant dashboards, installed presets, and an existing `sensor.lighting_scheduler`. Finding does not select/import a model or scan every file on disk.

A GLB/OBJ is geometry: it does not by itself contain Home Assistant entity bindings. Any model supported by floor3dx can be used when its card configuration and model/texture URLs are accessible. Selecting that configured card removes the need to reenter its bindings. A new bare geometry file needs its initial object bindings created once in the visual editor. This integration does not upload or convert geometry.

Sensors, locks, and other display-only model references remain read-only. Thermostats are excluded from the grid. Missing devices in another person's model can still be simulated, but its geometry must be available and actual scene contents are not inferred.

Plain YAML must describe one card or preset; resolve `!include` and `!secret` tags first. A preset can supply optional device metadata, scene effects, and aliases:

```json
{
  "renderer": {
    "type": "custom:floor3dx-card",
    "name": "Example home",
    "path": "/local/example-home/",
    "objfile": "home.glb",
    "entities": [
      {"entity": "switch.example_lamp", "type3d": "light", "object_id": "Lamp"}
    ]
  },
  "devices": [
    {"entity": "switch.example_lamp", "name": "Example lamp", "kind": "light", "watts": 9}
  ],
  "aliases": {"switch.example_lamp_alias": "switch.example_lamp"}
}
```

For a legacy Lighting Scheduler, the current model and available plans are read from `sensor.lighting_scheduler`; a supplied preset is the fallback. The old scheduler's storage is unchanged. A private preset/index already in `www/home-scheduler/` remains available after upgrading. Keep personal models and entity lists outside this public repository.

## Use the visual model editor

Click **Show model editor**. On a desktop it sits left of the house; on a phone it sits above it. The native floor3dx editor offers object bindings, camera settings, colors, and renderer options. Changes preview immediately.

**Save model** persists the configuration. New supported entity references create their rows automatically. **Discard** restores the saved configuration. Before switching models, a valid draft is saved; an invalid draft stays available until fixed/discarded. Concurrent saves are checked against a configuration revision so another card's changes are not silently overwritten.

The editor changes renderer configuration, not the underlying GLB/OBJ mesh bytes. Geometry changes still require a modeling tool. Keep one model editor active per browser window because floor3dx uses a shared preview-message channel.

![Native editor beside the demo](previews/demo-editor.png)

## Schedules, conditions, and presence variation

Choose a profile from **Schedule**. **Duplicate schedule** creates a named copy, up to 12 profiles. Edit its name, condition, and variation under **Names, conditions & presence variation**.

With **Conditional schedules** and **Follow clock** enabled, the first profile whose configured entity/state condition matches wins. The first profile is the fallback. With Follow clock off, preview the manually selected profile.

The demo includes Weekly demo, Guest, Worker, and Away. Guest/Worker/Away conditions reference `input_select.home_scheduler_mode`. For a HACS/UI install, create a Dropdown helper with that entity ID and options **Home, Guest, Worker, Away**, or change the conditions to an existing helper/entity. The optional YAML package creates the demo helper. Worker starts blank; Guest and Away contain editable examples.

Tick **Random** per device to shift the start/end of its checked periods within **Variation ± minutes** (0–60). Variation is repeatable for a date, device, and seed. **New variation** changes the seed. Adjacent checked non-scene blocks form a continuous period; overnight and week-boundary periods remain joined. Scene markers are shifted individually.

**Scene on activation** accepts a real scene ID, or a preview scene mapped to a real scene. In physical clock mode, it is dispatched once per selected profile/date/scene. A catalog scene's explicitly configured effects provide the preview baseline at midnight; a scene outside the catalog has no inferred preview effects.

## Scenes

A scene row is a list of timed activations, not an on/off device. Define its simulated effects explicitly using other device **preview IDs**:

```json
{
  "light.hs_demo_accent": {"state": "on", "brightness": 55, "color": "#bb75ff"},
  "cover.hs_demo_blind": {"position": 50}
}
```

The simulator applies these effects without executing a real Home Assistant scene. It does not infer a real scene's members or settings. Remove effect references before removing a device they mention.

Timed **real scenes require both Physical devices and Follow clock**. Scrubbing and playback apply scene effects virtually. Enabling physical control, editing a schedule, selecting a profile, or restarting does not replay earlier markers. A clock gap longer than two minutes does not trigger catch-up. Scene attempts are saved before dispatch and are not automatically retried after a service failure.

A real scene can affect devices outside the grid. Enabled linked rows continue enforcing their own configured periods on subsequent updates. Disable a row if a scene should own it, as the demo does for the accent lamp. A disabled mapped row can still display its actual state.

## Storage, updates, and removal

Settings, device connections, profiles, visibility, saved model configuration, and model catalogs are stored under Home Assistant's **`.storage/home_scheduler`** key. Model selection archives/restores each model's device catalog and schedule rows. The geometry bytes stay at their existing URLs; this storage contains configuration, not copied model files.

Two frequently updated states drive the card: `sensor.home_scheduler` and `sensor.home_scheduler_frame`. To avoid recording every simulation update, merge these exclusions into your existing Recorder configuration, or load the supplied package:

```yaml
recorder:
  exclude:
    entities:
      - sensor.home_scheduler
      - sensor.home_scheduler_frame
```

Do not create a second top-level `recorder:` block. HACS updates replace integration files, while saved settings and private `/local/` models remain in your HA configuration. Restart after an update and reload the dashboard. The manual installer backs up replaced component, compatibility assets, and package files under `home_scheduler_backups/`.

To stop scheduling, disable/remove the integration entry. This stops its loop and leaves real devices at their current state. If `home_scheduler:` is still loaded through YAML, remove it before deleting the entry or it will be imported again. Remove the dashboard card and uninstall the integration through HACS or delete its component folder, then restart. Delete `.storage/home_scheduler` with HA stopped only if intentionally discarding saved settings. An independent old `lighting_scheduler` installation is unaffected.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Custom card does not exist / integration missing | Confirm the component directory, restart HA, add/enable the integration, reload the browser, and remove the old scheduler resource |
| First-install `Integration 'home_scheduler' not found` warning | Confirm `manifest.json` is present; a full restart refreshes custom-integration discovery |
| Model/editor fails to load | Confirm floor3dx 1.4.0+ is installed and its resource loads; check browser console and model/texture URLs |
| No entities after choosing only a GLB/OBJ | Import its floor3dx configuration, or create initial object bindings in the editor |
| Device remains virtual | Check its real entity connection and that the entity exists |
| A hidden device still runs | Row/category visibility is separate from Enabled |
| Linked device does not change | Check Physical devices, row Enabled, entity availability, and supported capabilities |
| Cover moves only fully open/closed | Its integration may not support intermediate positions; use 0% or 100% |
| Real scene does not run during playback | Real scene dispatch uses Physical devices + Follow clock and forward clock markers |
| Guest/Worker/Away never selects | Enable conditional mode and Follow clock, and create/change the condition helper |
| Integration icon missing | Use HA 2026.3+, confirm the `brand` folder was copied, restart and reload |
| Model-save revision conflict | Discard/reload to see the newer saved model before applying your edit again |

For debug logs, merge this into your existing logger configuration:

```yaml
logger:
  logs:
    custom_components.home_scheduler: debug
```

Report reproducible issues using the fictional demo when possible. Remove personal entity IDs, model URLs, credentials, and private floorplans from logs/attachments.

## Development and publishing

| Directory/file | Contents |
| --- | --- |
| `custom_components/home_scheduler/` | Complete HACS runtime: backend, card, model, branding, translations |
| `packages/home_scheduler.yaml` | Optional YAML setup, demo helper, Recorder exclusions |
| `home_scheduler_view.yaml` | Example panel view |
| `brand/`, `previews/` | Original branding exports and browser screenshots |
| `tools/` | Reproducible demo/branding builders and release layout checks |
| `tests/` | Scheduler, installer, model-import, integration-lifecycle, and browser checks |
| `.github/workflows/validate.yml` | Tests, HACS validation, and hassfest after upload |

See [CONTRIBUTING.md](CONTRIBUTING.md) for local tests and [PUBLISH_GIT_BASH.md](PUBLISH_GIT_BASH.md) for repository/tag/release commands. The HACS runtime is entirely inside the component folder; consumers do not need the build tools or tests.

This early public release was checked with backend/lifecycle/installation tests and an integrated browser run using the actual scheduler, demo GLB, and floor3dx 1.4.0 renderer. Home Assistant service/storage APIs and native form widgets were test doubles. A real HA restart and hardware-specific behavior should be checked on the installation where physical scheduling will be used. The supplied GitHub validators run after publication; local checks do not claim official HACS catalog acceptance.

Original code and demo/branding assets use [MIT](LICENSE). Home Assistant, HACS, and floor3dx remain separate projects under their own licenses. Thanks to the floor3dx project and its original floor3d-card lineage for the renderer/editor foundation.
