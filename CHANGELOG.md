# Changelog

## 0.4.0

- Add opt-in learning for linked lights, switches/plugs and fans from actual on/off duration.
- Propose weekday schedules using 4/6/8 rolling weeks, at least three usable dates, 90% known coverage and a configurable consensus threshold (60% default).
- Keep unknown blocks as Still learning and retain the base schedule instead of guessing OFF.
- Add optional historical household-mode filtering and background Recorder backfill; older activity requires explicit source-uncertainty opt-in.
- Exclude whole physical-control intervals and possible indirect scene control from live learning.
- Store compressed daily observations separately, retain eight weeks and resume observation after restart without filling downtime.
- Add a review grid with frequency shading and counts, editable drafts, a separate 3D preview player and simulated On/Off indicators.
- Save learned routines as new named schedules without changing the running profile, real-device settings or existing schedules.
- Preserve custom package YAML and startup automations during manual upgrades.
- Add learning regression/browser checks and a guide for testing and publishing an update from Git Bash.

## 0.3.0

First public repository package.

- Install as one HACS integration; frontend, fictional demo, and branding are bundled inside the integration directory.
- Add Home Scheduler & Simulator through Home Assistant's Integrations page.
- Register the card module and static assets automatically; no separate scheduler frontend resource is required.
- Import existing YAML setup into a single config entry while retaining saved schedules and models.
- Keep existing private model presets outside the public repository and available after upgrades.
- Offer grid-only mode with `show_model: false`.
- Include automatic floor3dx model discovery/import, device row population, alias deduplication, schedule migration, and preserved camera configuration.
- Include lights, switches/plugs, fans, covers, and scenes; exclude thermostat scheduling.
- Include quarter-hour grids, bulk and row selection, drag/touch editing, weekdays, named conditional schedules, presence variation, and estimated energy.
- Start in simulation after every restart; model selection also disarms physical control.
- Include Home Assistant branding, automated repository checks, and detailed operation/publishing instructions.

## 0.2.1

Private preview: model selection/import, automatic bindings, saved model switching, and integration brand images.

## 0.2.0

Private preview: general device scheduling, fictional demo home, selected cyan house icon, and native floor3dx visual editor.
