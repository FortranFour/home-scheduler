# Publish from Windows Git Bash

**Already publishing FortranFour/home-scheduler?** Use [UPDATE_0_4_0.md](UPDATE_0_4_0.md) for this update. It preserves your checkout/history and covers testing, a release branch, PR, CI and version 0.4.0. The first-time setup below is for a new repository.

These commands publish the supplied source as **FortranFour/home-scheduler**, a dedicated public repository. The repository name matches the documentation and issue URLs in the integration manifest. It is separate from `FortranFour/floor3dx-card`; do not copy this project into that renderer repository.

Run the commands below **on your PC in Git Bash**. Home Assistant terminal commands in the README are for installing the integration on HA, not publishing to GitHub. No Python, Node, or build step is needed to upload the supplied package: the demo and branding are already built.

## 1. Install/check GitHub CLI

Git Bash provides `git`. The separate GitHub CLI, `gh`, creates repositories and releases from the command line. Your existing Git authentication may work for pushing, but does not necessarily authenticate `gh`.

```bash
git --version
gh --version
```

If `gh` is not found, install it with Windows Package Manager:

```bash
winget install --id GitHub.cli --exact
```

Close and reopen Git Bash so the new PATH takes effect. If WinGet is unavailable, use the Windows installer linked from [GitHub CLI](https://cli.github.com/), then reopen Git Bash.

Check authentication:

```bash
gh auth status
```

If you are not authenticated, run:

```bash
gh auth login --hostname github.com --git-protocol https --web
```

Complete the browser/device-code login using your **FortranFour** account. Verify the active account:

```bash
gh api user --jq .login
```

The result should be `FortranFour`. If another already-authenticated account is active, use `gh auth switch --hostname github.com --user FortranFour`, or log in to FortranFour first.

## 2. Extract the prepared source

Download `home_scheduler_github_0_4_0.zip` to your Windows Downloads folder. Then:

```bash
cd ~/Downloads
unzip home_scheduler_github_0_4_0.zip
cd home-scheduler
```

If your Downloads folder is elsewhere, adjust the `cd`. If `unzip` is unavailable, Windows PowerShell can extract it from the same Git Bash directory:

```bash
powershell.exe -NoProfile -Command 'Expand-Archive -LiteralPath home_scheduler_github_0_4_0.zip -DestinationPath .'
cd home-scheduler
```

The extracted directory should contain `README.md`, `LICENSE`, `hacs.json`, `.github`, and `custom_components/home_scheduler`. If `home-scheduler` already exists from an earlier download, extract this version into a new directory instead of merging it over your work.

## 3. Make the first commit

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Initial Home Scheduler & Simulator 0.4.0"
```

Review the staged file list before the commit. This distribution includes only fictional model/device data. Do not add your actual house preset, geometry, HA configuration, secrets, or `.storage` files. `.gitignore` excludes common private configuration/preset filenames, but cannot identify every arbitrarily named personal file.

If Git asks for an author name/email, configure them for this repository, then retry the commit:

```bash
git config user.name "FortranFour"
git config user.email "YOUR_VERIFIED_OR_GITHUB_NOREPLY_EMAIL"
git commit -m "Initial Home Scheduler & Simulator 0.4.0"
```

Replace the email placeholder with your verified email or the exact no-reply address shown in **GitHub → Settings → Emails**. Commit author settings and authentication are separate.

## 4. Create the repository and push

For a **new** repository:

```bash
gh repo create FortranFour/home-scheduler --public --source=. --remote=origin --description "Home Assistant device scheduling and isolated 3D home simulation."
gh repo edit FortranFour/home-scheduler --add-topic home-assistant --add-topic hacs --add-topic scheduling --add-topic simulation --add-topic floor3dx
git push -u origin main
```

The topic/description step comes before the first push so HACS's workflow can validate repository metadata. The repository must be public for HACS users to download it.

If HTTPS pushing prompts for authentication and your existing Git credentials do not work, let the authenticated GitHub CLI configure Git:

```bash
gh auth setup-git
git push -u origin main
```

Do not enter a GitHub account password as a Git HTTPS password.

### If `FortranFour/home-scheduler` already exists

Do not force-push over an existing repository. If it is completely empty, use the already-created repository instead of `gh repo create`:

```bash
git remote add origin https://github.com/FortranFour/home-scheduler.git
gh repo edit FortranFour/home-scheduler --description "Home Assistant device scheduling and isolated 3D home simulation." --add-topic home-assistant --add-topic hacs --add-topic scheduling --add-topic simulation --add-topic floor3dx
git push -u origin main
```

If it already has commits, use a fresh clone and a review branch. Run this from Downloads after the package was extracted; `home-scheduler-publish` must be a new directory:

```bash
cd ~/Downloads
gh repo clone FortranFour/home-scheduler home-scheduler-publish
cd home-scheduler-publish
git switch -c release-0.4.0
git -C ../home-scheduler archive HEAD | tar -x
git add .
git diff --cached --stat
git commit -m "Prepare Home Scheduler & Simulator 0.4.0"
git push -u origin release-0.4.0
gh pr create --repo FortranFour/home-scheduler --title "Prepare Home Scheduler & Simulator 0.4.0" --body-file RELEASE_NOTES.md
```

The archive copies only committed source files and excludes `.git`, preserving the clone's history. Review the diff for obsolete files or conflicts with the existing project, set the description/topics as above, and merge the PR after checks pass. Then switch to the repository's default branch and `git pull --ff-only` before creating the release tag. Do not tag the review branch before merging.

## 5. Check the GitHub workflow

The first push triggers **Validate**, with jobs for backend/layout tests, **hassfest**, and **HACS**:

```bash
gh run list --repo FortranFour/home-scheduler --workflow validate.yml --limit 5
```

Copy the run's numeric ID from that output and replace `RUN_ID`:

```bash
gh run watch RUN_ID --repo FortranFour/home-scheduler --exit-status
```

All three jobs should pass before publishing the release. For a failed run:

```bash
gh run view RUN_ID --repo FortranFour/home-scheduler --log-failed
```

These official validators cannot be represented as already passed before the repository exists on GitHub. Fix a failure, commit, push, and recheck; do not disable the validator to make the release appear ready.

## 6. Publish version 0.4.0

From the checked-out release commit on `main` (or the existing repository's default branch), create the matching tag and a standard GitHub release:

```bash
git tag -a v0.4.0 -m "Home Scheduler & Simulator 0.4.0"
git push origin v0.4.0
gh release create v0.4.0 --repo FortranFour/home-scheduler --verify-tag --title "Home Scheduler & Simulator 0.4.0" --notes-file RELEASE_NOTES.md
gh release view v0.4.0 --repo FortranFour/home-scheduler
```

HACS downloads the integration folder from the tagged repository. An additional ZIP release asset is not required. GitHub automatically provides source archives. Keep `manifest.json` version `0.4.0` aligned with release `v0.4.0`.

Users can now add this URL to **HACS → Custom repositories**, category **Integration**:

```text
https://github.com/FortranFour/home-scheduler
```

They restart HA, add **Home Scheduler & Simulator** through Devices & services, and follow the README. The optional floor3dx renderer remains a separate Dashboard installation.

Publishing a custom repository does not automatically add it to HACS's default search catalog. A later catalog submission must meet the current [HACS publication requirements](https://www.hacs.dev/docs/publish/start/) and pass its review.

## Later updates

Update source, the README/changelog/release notes, and every release-version location listed in [CONTRIBUTING.md](CONTRIBUTING.md). Commit and push, wait for checks, then create a **new** matching tag and release. Do not move an already-published tag. Users' saved schedules/private model files live in their HA configuration and are not uploaded with your repository updates.

## If you prefer to use only `git`

`git` can upload commits/tags to an existing remote, but cannot create a GitHub repository or GitHub Release by itself. Without `gh`, create an empty public `FortranFour/home-scheduler` repository on github.com (do not initialize a README/license), add its HTTPS remote, and push as shown above. Publish the release through GitHub's web interface after checks pass. The `gh` route keeps repository and release creation on the command line.

References: [GitHub CLI installation](https://cli.github.com/), [gh auth login](https://cli.github.com/manual/gh_auth_login), [gh repo create](https://cli.github.com/manual/gh_repo_create), [gh release create](https://cli.github.com/manual/gh_release_create), and [HACS integration requirements](https://www.hacs.dev/docs/publish/integration/).
