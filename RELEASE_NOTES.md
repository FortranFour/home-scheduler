# Home Scheduler & Simulator 0.4.2

**The preview clock now drives the daylight of any model.** A house imported from a dashboard usually leaves floor3dx-card's `daylight` on its default `sun.sun`, so inside the scheduler it followed the real sun and its lighting stood still while the day played. The embedded card now gets the simulated hour as its `daylight.time_entity` (unless the configuration names one), and a fixed `daylight.time` is dropped for the preview. A model without a `daylight` block keeps its plain lighting; add one for day and night.

**Rooms Card models.** A floor3dx **Rooms Card** (2.5 and later) keeps the 3D card as `card:` or, with several models, as `models[].card`, usually without a `type`. **Find models** now lists each of them (*House · Overview*, *Garage · Overview*), inside a wrapper card too, and **Import configuration…** accepts a Rooms Card's block (asking you to choose when it holds several models).

Version 0.4.2 appears in the integration, the card and the demo URLs (cache-busting). Existing schedules, private models, dashboard cards and resources continue to work; no YAML change is needed. Earlier notes are in [CHANGELOG.md](CHANGELOG.md).
