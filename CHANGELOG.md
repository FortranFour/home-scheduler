# Changelog

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
