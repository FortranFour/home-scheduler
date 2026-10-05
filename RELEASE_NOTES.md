# Home Scheduler & Simulator 0.3.0

Plan a week's lights, switches, plugs, fans, blinds, curtains, other covers, and scene activations in a quarter-hour grid. Play the day in a fictional 3D home, import your own configured floor3dx model, or use the simulated device indicators without 3D.

The integration bundles its scheduler card, original demo, and branding. Install through HACS as a custom **Integration**, restart Home Assistant, and add **Home Scheduler & Simulator** in Settings → Devices & services. For 3D, install **FortranFour/floor3dx-card 1.4.0 or later** separately.

Selecting a configured model automatically populates device rows and object bindings, retains camera settings, and can copy an existing Lighting Scheduler's plans. Geometry files alone do not contain Home Assistant entity bindings.

Physical control starts off after every restart and model import. Scenes operate real devices only as the real clock advances. Thermostats are excluded.

Upgrading from the manual preview: retain `.storage/home_scheduler` and your model files, remove the old scheduler `frontend.extra_module_url` entry, and follow the migration section in the README. No extra scheduler module resource is needed.

This early public release has scheduler, installation, integration lifecycle, model-import, and real-renderer browser checks. Home Assistant APIs/form widgets used test doubles locally; GitHub runs the supplied HACS and hassfest workflows after upload. Hardware-specific behavior should be checked on the user's own installation before relying on physical scheduling.
