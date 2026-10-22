# Home Scheduler & Simulator 0.4.1

A compatibility release for **floor3dx-card 2.x** (three.js r186). The scheduler embeds floor3dx-card's renderer and visual editor; this release has been checked against floor3dx-card 2.3.0 as well as 1.4.0, and the integrated browser test passes unchanged against the new renderer.

The embedded model always runs with floor3dx-card's `merge_static` option off, so the object picker in the visual model editor reaches every object in the imported model. The other 2.x options (`lights`, `color_management`, `exposure`, the look themes) pass through the import as configured, so a model tuned in a floor3dx-card dashboard looks the same inside the scheduler. See [README.md](README.md#floor3dx-card-2x) for what floor3dx-card 2.x means for an imported model.

Version 0.4.1 appears in the integration, the card and the demo URLs (cache-busting). Existing schedules, private models, dashboard cards and resources continue to work; no YAML change is needed. The 0.4.0 notes on **Learn from actual use** are in [CHANGELOG.md](CHANGELOG.md).
