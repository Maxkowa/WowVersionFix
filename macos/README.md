# WoW Build Switcher (macOS)

A small macOS app that downloads any historical World of Warcraft client build's app bundle — straight from Blizzard's CDN — and swaps it into your game folder.

Pick a flavor, pick a build, click **Switch**.

> This is the macOS app in a two-app repo — see the [root README](../README.md). For the Windows app (`Wow.exe`, `Wow_loader.dll` extraction), see [`windows/`](../windows/).

## Download

**There is no macOS release yet.** The first one lands when `macos-v1.0.0` is tagged; until then, [build from source](#build-from-source) — it takes one command.

Once it exists it will be a zipped, universal binary (Apple Silicon and Intel), macOS 14 or later: unzip and drag **WoW Build Switcher.app** to `/Applications`. Check [/tags](https://github.com/Maxkowa/WowVersionFix/tags) for a `macos-v*` tag, and grab the `.zip` from that tag's release page.

Don't use `/releases/latest` — it is pinned to the Windows app, so it will hand you an `.exe`. Don't use `/releases?q=macos` either: `q=` is a full-text search over release notes, so it can match a Windows release whose changelog happens to mention macOS.

The app is ad-hoc signed, so macOS blocks a downloaded copy on first launch. Open it once, then go to **System Settings → Privacy & Security**, find the message about *WoW Build Switcher* and click **Open Anyway**. (On macOS 14 you can right-click → **Open** instead; Apple removed that shortcut in macOS 15.) A copy you built yourself is not quarantined and just opens.

## Build from source

Requires the Xcode Command Line Tools (`xcode-select --install`), which provide `swiftc`.

```bash
./build.sh
```

Output lands in `build/WoW Build Switcher.app`. Drag it to `/Applications`.

A local `./build.sh` targets the architecture you build on (Apple Silicon or Intel) by default. Set `ARCHS="arm64 x86_64"` to get the universal binary that CI publishes.

Nothing about the bundle is spelled out twice: `build.sh` takes the app's name, its deployment target and its version from `Info.plist`.

The CLI lives at `wowbuild.py` and needs nothing but a system `python3` — no pip packages.

## Usage

1. Launch **WoW Build Switcher**.
2. Pick a **flavor** from the segmented control (`_retail_`, `_ptr_`, `_classic_era_`, …).
3. The list shows builds available on the CDN, newest first. Already-downloaded ones are tagged **Downloaded**; the one Battle.net expects is tagged **Battle.net**.
4. Click **Switch** (or **Download**, if it isn't local yet). Live output appears in the log pane, and **Stop** cancels a command that is still running.
5. **Restore Battle.net Build** puts the expected build back.

The header shows what's installed versus what Battle.net expects. Switch is disabled while that flavor's client is running; Restore is disabled unless the bundle is actually swapped.

## The command line

The app is a front end over the same script — everything it does is available directly. The commands below assume `wowbuild` is on your `PATH`:

From the repo root (`brew --prefix` resolves to `/opt/homebrew` on Apple Silicon and `/usr/local` on Intel):

```bash
ln -s "$(pwd)/macos/wowbuild.py" "$(brew --prefix)/bin/wowbuild"
```

```
wowbuild                        interactive
wowbuild status                 installed vs what Battle.net expects
wowbuild list [-p wowt] [-n 20] builds available on the CDN
wowbuild fetch 12.1.0.69404     download into the local library
wowbuild install 12.1.0.69404   fetch + swap into the game folder
wowbuild revert                 restore the build Battle.net expects
wowbuild library                what's stored locally
wowbuild clean [--library]      drop cached index data (and the library)
```

Global flags: `-p/--product` (default `wow`), `--game-dir`. `install` takes `-y` to skip the prompt and `-f` to re-fetch.

## Nothing is hardcoded

Everything is read from your own install and Blizzard's endpoints:

| value | source |
|---|---|
| game folder | `/Applications/World of Warcraft` (or `--game-dir`) |
| products and folders | each flavor's `.flavor.info` |
| region, locale, arch tags | the `Tags` column of `.build.info` |
| CDN hosts and path | the `CDN Hosts` / `CDN Path` columns of `.build.info` |
| app bundle name | derived from the build's own install manifest |
| current live build | `{region}.version.battle.net` |
| build history | [wago.tools/api/builds](https://wago.tools/api/builds) |

So it works for `wow`, `wowt`, `wow_classic_era`, `wow_anniversary` without being told which is which — including that PTR's bundle is named `World of Warcraft Test.app` and Classic's is `World of Warcraft Classic.app`. The app reads the same JSON, so it has no flavor list of its own either.

## Safety

- Refuses to swap a flavor whose client is running (scoped per flavor, so you can touch PTR while retail is open).
- Verifies `codesign --verify --deep --strict` before a build downloaded from the CDN enters the library, and refuses to keep one that fails. (The bundle already installed in your game folder is archived as-is when you switch away from it.) Files are Blizzard's own, signed with their Developer ID — nothing is patched or re-signed.
- Downloads to a `.partial` directory and only renames into place on success.
- Before swapping, copies whatever is currently installed into the library, so `revert` never depends on the CDN still hosting that build.
- Never touches `.build.info`. That file tells the client which CASC config to read out of `Data/`, so leaving it alone is what lets an older binary run against the data already on disk.

## Layout

```
macos/wowbuild.py                  the tool - the tracked copy, and what build.sh bundles

/Applications/WoW Build Switcher.app
  Contents/MacOS/...               native SwiftUI front end
  Contents/Resources/wowbuild.py   the copy that shipped inside the app

~/wow-build-fetch/
  wowbuild.py                      optional override - if this file exists, the app runs
                                   it INSTEAD of the bundled copy
  library/<product>/<version>/<Name>.app
  cache/                           build configs, install manifests, encoding tables,
                                   archive indices (safe to delete; ~300 MB per build)
```

`library/` and `cache/` are Blizzard's files and are not in this repo.

The app runs `~/wow-build-fetch/wowbuild.py` when it is present and the bundled copy otherwise, and the CLI runs whichever copy you symlinked. Those can be different files: an old `~/wow-build-fetch/wowbuild.py` will shadow a freshly built app. The first line of the log pane is the script path the app actually launched, so you can always tell — if it isn't the one you edited, delete the stale copy or point both at the same file.

`~/wow-build-fetch` is the tool's data directory, not a place to clone this repo: it has its own `README.md` that would collide with the repo's, and its `cache/` and `library/` would sit at the repo root.

## Caveats

- The game data in `Data/` stays at whatever build Battle.net installed. Swapping the binary within the same patch (69465 -> 69404) is normally fine; across patches the older binary may not understand the newer data.
- Battle.net's Scan and Repair restores the expected build. Launch the swapped bundle directly instead of pressing Play.
- If the realm version gate has moved on, an older client is rejected at login with "This version of World of Warcraft is out of date". Nothing client-side changes that.
- Blizzard prunes old builds from the CDN eventually. A build listed on wago.tools is not guaranteed to still be downloadable.

## Releasing

Pushing a `macos-v*` tag triggers a CI build on a macOS runner that produces the universal app bundle and attaches it, zipped, to a release for that tag. `windows-v*` tags are the Windows app and build nothing here.

CI passes the tag's version to `build.sh` as `BUNDLE_VERSION`, so a released bundle reports the version it was tagged with; a local build keeps whatever `Info.plist` says. macOS releases are explicitly *not* marked as the repo's **Latest** — that stays with the Windows app, so `/releases/latest` never serves a `.app`.

Every push to `main` and every pull request builds both apps without releasing anything, so a tag only ever runs code that already compiled.

## Credits

- [wago.tools](https://wago.tools) — build index.

## License

MIT
