# Home Scheduler 0.4.0: try it, then publish from Git Bash

This updates the existing **FortranFour/home-scheduler** integration and adds **Learn from actual use**. Keep your existing Git repository, HA integration entry, saved schedules, personal model and dashboard. Versions 0.3.0 and 0.4.0 use the same integration domain, so they do not run side by side in one HA instance.

## 1. Extract the package on your Windows PC

Download `home_scheduler_github_0_4_0.zip` to Downloads. In **Git Bash on your PC**:

```bash
cd ~/Downloads
mkdir -p home-scheduler-0.4.0-review
unzip home_scheduler_github_0_4_0.zip -d home-scheduler-0.4.0-review
cd home-scheduler-0.4.0-review/home-scheduler
```

This directory is the prepared update. The following HA commands run in **Home Assistant's Terminal & SSH app**, not your PC's Git Bash. Adjust `/config` to your actual HA configuration directory if it is `/homeassistant`.

## 2. Install on your HA instance for review

Create a Home Assistant backup. This replaces the installed component; saved schedules and personal models remain. If you use a startup automation to re-enable physical scheduling, it will continue doing so after restart. Disable physical scheduling while gathering an independent routine if you want those devices to provide usable learning samples.

Copy the extracted `home-scheduler` directory to `/config/home-scheduler-0.4.0-review` using your normal file-transfer method. In HA's terminal:

```sh
sh /config/home-scheduler-0.4.0-review/install.sh /config
ha core check
ha core restart
```

Run the restart after a successful check. Container/Core users should use their normal check/restart procedure. The installer backs up replaced files under `/config/home_scheduler_backups/` and preserves an existing `packages/home_scheduler.yaml`, including custom helpers and restart automations. It does not edit `configuration.yaml` or either `.storage` file. A fresh optional package is copied only if one does not already exist.

Reload the dashboard/browser after HA starts. The version attribute in `sensor.home_scheduler` should be **0.4.0**, and the card should show **Learn from actual use…** beside **Duplicate schedule**. Keep your existing floor3dx resource. **No additional scheduler JavaScript resource is needed.** A separate YAML package is not required for learning.

A later HACS download can replace this local review build. Publish/update HACS after you are satisfied. To revert, copy the backed-up component directory back into `/config/custom_components/home_scheduler`, restart and reload. Retain `.storage/home_scheduler` and `.storage/home_scheduler_learning`; 0.3.0 ignores the latter.

## 3. Check the new feature

1. Open **Learn from actual use…**. Connect any unlinked light to its real entity first. Linked lights are selected by default; select switches/fans if desired.
2. Optionally choose a real household-mode/occupancy entity and save settings. Enable **Observe actual use**. It keeps collecting when the dashboard is closed and resumes after HA restart.
3. Optionally **Read available Recorder history** and wait for completion. To use older activity in a proposal, explicitly tick **Include older activity with uncertain source**. It may include activity from your former scheduler. Existing Recorder retention is unchanged.
4. Generate a proposal with the default **6 weeks / 60%**. Each block needs at least three usable matching weekdays. **Still learning** preserves the current schedule. With short Recorder history, many weekdays may initially lack enough data; keep observing.
5. Hover/focus cells for counts, edit the proposal, then **Preview in model** or **Play proposal**. The model and proposal On/Off indicators use an isolated preview. The main schedule and real states should stay unchanged, including when physical scheduling is active.
6. Enter a unique name and **Save as new schedule**. Confirm that the current schedule remains selected. Select/activate the new profile explicitly when ready.

Live learning excludes a device's whole Home Scheduler physical-control interval. Learn while those rows are not controlled by Home Scheduler, or observe other independent devices. Learning supports on/off lights, switches and fans; it does not yet learn covers, scenes, brightness or fan speed. See the README for coverage, mode filtering, DST, retention and clearing rules.

Local checks use the actual scheduler and floor3dx 1.4.0 renderer with Home Assistant/Recorder test doubles. This installation check lets you verify your live Recorder database and restart behavior.

## 4. Update your existing Git checkout

Back on **your PC in Git Bash**, check `gh` and your checkout:

```bash
gh --version
gh auth status
cd ~/Downloads/home-scheduler
git status --short
git remote -v
git switch main
git pull --ff-only origin main
git switch -c release-0.4.0
```

If the status lists existing edits, preserve or commit them before copying this package. Keep the checkout's existing `.git` directory and `origin` remote; do not reinitialize or recreate the repository. If the branch already exists, switch to it rather than recreating it.

Copy the prepared files and inspect the changes:

```bash
cp -a ~/Downloads/home-scheduler-0.4.0-review/home-scheduler/. .
git diff --stat
git diff --check
git status --short
git add .
git diff --cached --stat
git commit -m "Add actual-use learning and isolated schedule proposals"
git push -u origin release-0.4.0
gh pr create --repo FortranFour/home-scheduler --base main --title "Home Scheduler 0.4.0: learn schedules from actual use" --body-file RELEASE_NOTES.md
```

Review staged files before committing. Keep private model/configuration/history files out of the repository. Source and screenshots are already built; Python/Node are not required on your PC for publishing.

Find the **Validate** workflow run:

```bash
gh run list --repo FortranFour/home-scheduler --branch release-0.4.0 --workflow validate.yml
```

Replace `RUN_ID` with the desired run's numeric ID:

```bash
gh run watch RUN_ID --repo FortranFour/home-scheduler --exit-status
```

Review any HACS/hassfest failures before release. When the PR and checks are ready, replace `PR_NUMBER` with the number returned by `gh pr create` and merge:

```bash
gh pr merge PR_NUMBER --repo FortranFour/home-scheduler --merge
git switch main
git pull --ff-only origin main
```

Also check the Validate run on merged `main` before tagging.

## 5. Create the matching release

After the changes are on `main` and checks pass:

```bash
git tag -a v0.4.0 -m "Home Scheduler & Simulator 0.4.0"
git push origin v0.4.0
gh release create v0.4.0 --repo FortranFour/home-scheduler --verify-tag --title "Home Scheduler & Simulator 0.4.0" --notes-file RELEASE_NOTES.md
gh release view v0.4.0 --repo FortranFour/home-scheduler
```

HACS takes the integration from the tagged repository; an extra ZIP asset is unnecessary. Refresh HACS, update to 0.4.0, restart HA and reload the dashboard. Saved schedules, models and learning data remain in your HA configuration.

If Git Bash cannot find an installed `gh`, reopen it. For the default Windows location you can also use:

```bash
export PATH="$PATH:/c/Program Files/GitHub CLI"
hash -r
gh --version
```

For first-time repository setup instead of updating your existing repo, use [PUBLISH_GIT_BASH.md](PUBLISH_GIT_BASH.md).
