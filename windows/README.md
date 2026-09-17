# WoW Version Fix (Windows)

A tiny Windows app that downloads specific files (`Wow.exe`, `Wow_loader.dll`, etc.) from any historical World of Warcraft build — straight from Blizzard's CDN.

No install. No setup. Double-click and go.

> This is the Windows app in a two-app repo — see the [root README](../README.md). For macOS, the [`macos/`](../macos/) folder has **WoW Build Switcher**, which swaps whole client bundles instead.

## Download

> **[⬇ Download WowVersionFix.exe](https://github.com/Maxkowa/WowVersionFix/releases/download/v1.0.0/WowVersionFix.exe)** — `v1.0.0`, the newest Windows build.

Windows 10/11 x64. ~75 MB (self-contained — no .NET install needed).

`v1.0.0` predates the two-app split; Windows builds from here on are tagged `windows-v*`. Every tag is listed at [/tags](https://github.com/Maxkowa/WowVersionFix/tags) — if a `windows-v*` tag is there and this link still says `v1.0.0`, the tag is newer.

Don't use `/releases/latest`, and don't trust `/releases?q=windows`: this repo also ships a macOS app, and `q=` is a full-text search over release notes, not a tag filter. A tagged link is the only one that can't hand you the wrong platform's binary.

On first launch, Windows SmartScreen may warn that the app is unrecognized (it's unsigned). Click **More info → Run anyway**.

## How it works

- Fetches the live build list from [wago.tools](https://wago.tools/builds).
- Uses the build's config hashes to talk to Blizzard's CDN (same as the Battle.net client).
- Invokes an embedded copy of [TACTTool](https://github.com/wowdev/TACTSharp) to pull just the files you selected.
- Drops them into `Desktop\WowVersionFix\{product}_{version}\` (the output folder is editable).

Blizzard prunes old builds from the CDN eventually, so a build that wago.tools still lists is not guaranteed to still be downloadable. When that happens TACTTool exits non-zero and the app reports the exit code — it isn't a bug in the extraction.

## Usage

1. Launch `WowVersionFix.exe`.
2. Pick a **Product** (wow / wowt / wow_beta / wow_classic / …).
3. Pick a **Version** from the dropdown.
4. Tick the files you want (`Wow.exe`, `Wow_loader.dll`) or type others comma-separated.
5. Click **Extract**. Done.

## Build from source

Requires [.NET 8 SDK](https://dotnet.microsoft.com/download) on Windows.

From the repo root:

```bash
dotnet publish windows/WowVersionFix.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

Output lands in `windows/bin/Release/net8.0-windows/win-x64/publish/WowVersionFix.exe`.

Or `cd windows` first and drop the project path:

```bash
cd windows
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

The build has no `<Version>`: a local publish gets MSBuild's default, and CI passes `-p:Version=` from the tag, so a released exe reports the version it was tagged with.

## Releasing

Pushing a `windows-v*` tag triggers a CI build on a Windows runner that runs the publish command above and attaches the resulting `WowVersionFix.exe` to a release for that tag. `macos-v*` tags are the macOS app and build nothing here.

Windows releases are marked as the repo's **Latest**; macOS ones explicitly are not, so `/releases/latest` always resolves to a Windows `.exe`.

Every push to `main` and every pull request builds both apps without releasing anything, so a tag only ever runs code that already compiled.

## Credits

- [TACTSharp / TACTTool](https://github.com/wowdev/TACTSharp) by Marlamin — does all the heavy lifting. Its license and the notice for the zlib-ng it links are in [`Resources/THIRD-PARTY.md`](Resources/THIRD-PARTY.md).
- [wago.tools](https://wago.tools) — build index.

## License

MIT for this app's own source. The redistributed `Resources/TACTTool.exe` is covered by [`Resources/THIRD-PARTY.md`](Resources/THIRD-PARTY.md) instead.
