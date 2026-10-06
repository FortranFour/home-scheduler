# Home Scheduler & Simulator 0.4.0

**Learn from actual use** can prepopulate a weekly routine from linked lights, switches/plugs and fans. Observe real devices, optionally backfill suitable Recorder history, then compare matching weekdays in 15-minute blocks. The default is six weeks, a 60% ON consensus and at least three usable samples. Unknown data stays **Still learning**, retaining existing blocks.

Review frequency shading and sample counts, edit the proposal and play it in your house model using a separate virtual player. Saving creates a new named schedule without selecting it, changing the running profile or operating real devices. Proposal playback remains virtual even when the normal physical runner is armed.

Live learning excludes Home Scheduler's full physical-control intervals. Optional household-mode filtering uses the mode at the time of observation. Older Recorder activity has uncertain source and is excluded until explicitly included. Compressed observations are stored separately, retained for eight rolling weeks and preserved across restarts; downtime is not inferred as OFF. Covers and scenes remain schedulable, but are not learned in this release. Thermostats remain excluded.

The manual installer now preserves existing package YAML, including custom helpers and restart automations. Existing schedules, private models, dashboard cards and resources continue to work. No extra scheduler module resource or mandatory YAML change is needed.

The renderer and visual editor still come from the separately installed floor3d family; **only floor3dx-card 1.4.0 has been tested** with this package. Read [UPDATE_0_4_0.md](UPDATE_0_4_0.md) to test the update before publishing it, and [README.md](README.md#learn-from-actual-use) for operation.

Local checks cover scheduler/integration/installer behavior, learning edge cases and actual floor3dx rendering of an isolated learned proposal while the runner is armed. HA service/storage/Recorder interfaces and native form widgets use test doubles. A live HA Recorder database and hardware behavior still need verification on your installation; GitHub HACS/hassfest validation runs after publication.
