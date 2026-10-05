# Contributing

Use a branch and a pull request. Keep model fixtures fictional, preserve saved schedule compatibility, and verify that view/model edits never operate physical devices. Add a regression check when changing scheduling, control, storage, or the integration lifecycle.

Run:

```sh
python -m pip install PyYAML Pillow
python -m unittest discover -s tests -v
python tools/check_release.py
node --check custom_components/home_scheduler/frontend/home-scheduler-card.js
sh -n install.sh
```

For the integrated browser check, install Playwright/Chromium and obtain a local floor3dx-card 1.4.0 bundle:

```sh
npm install --no-save playwright
npx playwright install chromium
FLOOR3DX_BUNDLE=/absolute/path/to/floor3dx-card/dist/floor3dx-card.js node tests/test_ui.cjs
```

The browser test uses the real scheduler and renderer/demo. Its Home Assistant APIs and native form widgets are doubles. HACS and hassfest are separate GitHub jobs; they need the published repository. Do not bypass failed validators when submitting to the HACS default catalog.

Set the release version in `const.py`, `manifest.json`, the card's versioned asset URLs, `home_scheduler_view.yaml`, `install.sh`, and the model build script. Update the changelog and release notes, run all required checks, then publish a matching GitHub tag and release. `tools/check_release.py` checks version consistency.

The package uses MIT for its own code and original assets. floor3dx-card is a separately maintained dependency and is not bundled.
