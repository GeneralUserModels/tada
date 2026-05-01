# Testing the auto-updater locally

`updater.ts` ships updates from GitHub Releases via `electron-updater`. Real channel separation, install handoff, and feature-flag refresh are tricky to verify on the live `GeneralUserModels/tada` repo without affecting other alpha users. This doc covers how to test end-to-end against a local feed.

## What's tested

1. **Channel siloing** — alpha builds only accept alpha releases, beta only beta, stable only stable. Enforced client-side in the `update-available` handler regardless of what the GitHub provider's cascade serves up.
2. **Feature-flag refresh on update** — `tada-config.json`'s `feature_flags` block is overwritten from `tada-config.defaults.json` whenever `app.getVersion()` differs from the stored `_app_version`.
3. **Install handoff** — clicking "Install Now" should quit the app, hand off to ShipIt, and relaunch into the new version without manual intervention.

## Local feed override

`updater.ts` reads `TADA_UPDATE_FEED_URL` at startup. When set, it calls `autoUpdater.setFeedURL({ provider: "generic", url, channel })` instead of using the configured GitHub provider. This lets you point an installed build at a `python -m http.server` over `release/` and exercise the full Squirrel.Mac install path with no GitHub side effects.

## Procedure

### 1. Build and install version A

From the repo root, with `package.json` at the version you want to install first:

```bash
npm run dist                                  # builds release/Tada-<v>.dmg, no publish
open release/Tada-<v>.dmg                     # drag Tada to /Applications
xattr -cr /Applications/Tada.app              # only if Gatekeeper blocks
open /Applications/Tada.app                   # one-time normal launch to verify
```

`npm run dist` uses `--publish never`, so nothing is uploaded. Notarization is skipped if `APPLE_ID` is unset (see `scripts/notarize.cjs`); code signing still happens via your Developer ID keychain entry.

### 2. Bump the version and build version B

Edit `package.json` to a higher prerelease in the same channel (e.g. `0.0.7-alpha` → `0.0.8-alpha`). Then:

```bash
npm run dist
ls release/                                   # alpha-mac.yml + Tada-<v>-arm64-mac.zip
```

`release/` is wiped on each build — that's fine, version A is already installed in `/Applications`.

### 3. Serve the build dir

```bash
cd release && python3 -m http.server 8765
```

Leave it running in one terminal; you'll see GET requests as the app polls.

### 4. Launch the installed app pointed at the local feed

```bash
TADA_UPDATE_FEED_URL=http://127.0.0.1:8765 \
  /Applications/Tada.app/Contents/MacOS/Tada
```

Watch for, in order:

- **HTTP server terminal:** `GET /alpha-mac.yml`, then `GET /Tada-<v>-arm64-mac.zip`.
- **App's electron log** (path from `getLogDir()`, typically `~/Library/Application Support/tada/logs/electron.log`):
  - `[updater] using local feed: http://127.0.0.1:8765`
  - `[updater] update available: <new version>`
  - `[updater] update downloaded: <new version>`
- **App UI:** "Version X is ready to install" banner.

### 5. Click "Install Now"

App should quit and relaunch into the new version within ~10s. Verify:

```bash
defaults read /Applications/Tada.app/Contents/Info CFBundleShortVersionString
# → new version

jq '._app_version, .feature_flags' \
  ~/Library/Application\ Support/tada/tada-config.json
# _app_version matches new version, feature_flags matches tada-config.defaults.json
```

### 6. Channel-filter sanity check (optional)

To prove cross-channel updates are rejected, edit `release/alpha-mac.yml` and change `version:` to a different channel (e.g. `0.0.9-beta`). Restart the app the same way. The log should show:

```
[updater] skipping cross-channel update 0.0.9-beta (beta != alpha)
```

…and no banner. Revert the yml when done.

## Diagnostics when install hangs

ShipIt's logs are the single most useful signal. The `ShipIt_stderr.log` is a running history of every install attempt — each install starts with `Detected this as an install request`. A successful install reads:

```
Detected this as an install request
Beginning installation
Moving bundle from file:///Applications/Tada.app/ to ...
Moved bundle contents from ... to file:///Applications/Tada.app/
Installation completed successfully
ShipIt quitting
```

If the log stops at `Detected this as an install request`, ShipIt is hung waiting for the parent app to fully exit. Diagnostic commands:

```bash
# Did the binary get replaced?
defaults read /Applications/Tada.app/Contents/Info CFBundleShortVersionString

# Code signatures must match for ShipIt to apply the update.
codesign -dvv /Applications/Tada.app 2>&1 | grep -E "Authority|TeamIdentifier"
codesign -dvv release/mac-arm64/Tada.app 2>&1 | grep -E "Authority|TeamIdentifier"

# Is anything still running?
ps -ef | grep -iE "Tada|ShipIt|python.*server" | grep -v grep

# ShipIt's own log
cat ~/Library/Caches/com.generalusermodels.tada.ShipIt/ShipIt_stderr.log | tail -40

# Unified log around the install
log show --predicate 'process == "ShipIt" OR processImagePath CONTAINS "Tada"' \
  --last 5m --style compact | tail -60
```

Wipe ShipIt state between attempts so logs aren't ambiguous:

```bash
rm -rf ~/Library/Caches/com.generalusermodels.tada.ShipIt/*
```

## Known caveats

- **Code signing is mandatory for Squirrel.Mac.** Both versions A and B must be signed with the same Developer ID Team Identifier. If `codesign -dvv` shows different `TeamIdentifier` values, ShipIt will install the new bundle but macOS will refuse to launch it (or it'll be quarantined).
- **The env var only works on the first launch.** When ShipIt relaunches the new app after install, it does so via `open` / LaunchServices, which doesn't inherit the terminal's environment. The relaunched app falls back to the GitHub feed. That's expected — the local-feed override is just for the initial update check.
- **Direct-binary launch vs `open`.** Launching `/Applications/Tada.app/Contents/MacOS/Tada` from a shell is supported but quirkier than `open -a Tada`: the parent is your shell, not launchd, and ShipIt's PID-watch sees the shell's child rather than a launchd-managed process. If you hit relaunch problems specifically (install completes, doesn't reopen), switch to:
  ```bash
  launchctl setenv TADA_UPDATE_FEED_URL http://127.0.0.1:8765
  open /Applications/Tada.app
  # ...test...
  launchctl unsetenv TADA_UPDATE_FEED_URL
  ```
- **Don't run `npm run release:publish` for testing.** It uploads to the production GitHub repo and rolls out to every alpha user on autoupdate. `npm run dist` is the test command; `release:publish` is reserved for actual releases.
