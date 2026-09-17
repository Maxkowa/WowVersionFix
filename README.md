# WoW Version Fix

Two separate tools for pulling historical World of Warcraft client files straight from Blizzard's CDN — one for Windows, one for macOS.

They are independent apps with their own downloads, their own releases and their own docs. Pick the one for your platform.

## The apps

| App | Platform | What it does | Download | Source |
|---|---|---|---|---|
| **WoW Version Fix** | Windows 10/11 x64 | Extracts individual files (`Wow.exe`, `Wow_loader.dll`, …) from any historical build into a folder of your choice | [WowVersionFix.exe](https://github.com/Maxkowa/WowVersionFix/releases/latest/download/WowVersionFix.exe) — always the newest Windows build | [`windows/`](windows/) |
| **WoW Build Switcher** | macOS 14+ | Downloads a whole historical client `.app` bundle and swaps it into your game folder | [WoW-Build-Switcher-macos.zip](https://github.com/Maxkowa/WowVersionFix/releases/download/macos-v1.0.1/WoW-Build-Switcher-macos.zip) — currently `macos-v1.0.1` | [`macos/`](macos/) |

Details, usage and build instructions live in [`windows/README.md`](windows/README.md) and [`macos/README.md`](macos/README.md).

## Releases

Each app releases on its own tag, so every tag produces its own release with only that app's asset:

| Tag | Builds | Publishes |
|---|---|---|
| `windows-v*` | the C# / WinForms app | `WowVersionFix.exe` (self-contained, single file) |
| `macos-v*` | the SwiftUI app | `WoW-Build-Switcher-macos.zip` — a zipped `WoW Build Switcher.app` (universal — arm64 + Intel) |

Every tag is listed at [**/tags**](https://github.com/Maxkowa/WowVersionFix/tags) — the prefix tells you which app it is, the one exception being the original `v1.0.0` below. Each one links to its own release page and assets.

The unprefixed `v1.0.0` release predates the split and holds the Windows `.exe`, along with that app's download count. Windows releases from here on are tagged `windows-v*`, and the download link above follows whichever release holds the **Latest** marker — naming one here would only be something else to keep current.

Because the two apps share one repo, the **Latest** marker belongs to the Windows app: Windows releases are published with `--latest`, macOS ones with `--latest=false`. Two different things hang off that, and only one of them is a trap:

- The `/releases/latest` **page** is pinned to the Windows release, so it is useless for finding a macOS build — it will never show you one.
- The asset-scoped `/releases/latest/download/<asset>` **URL** is safe, because the asset name is part of the request. `…/latest/download/WowVersionFix.exe` resolves to the newest Windows release's exe and keeps doing so without anyone editing a link. `…/latest/download/WoW-Build-Switcher-macos.zip` 404s by design — the worst case is a dead link, never an `.exe` handed to a Mac user. That is why the macOS row above is pinned to a tag.

Don't use `/releases?q=…` at all: that box is a full-text search over release notes, so a Windows release whose changelog mentions macOS shows up under `q=macos`.

### Maintaining the download links

The Windows row maintains itself. Its link is asset-scoped `/releases/latest/download/`, so publishing a `windows-v*` release as **Latest** repoints it with no edit. That cuts both ways: anything that moves the **Latest** marker off a Windows release breaks every Windows download link at once. Publish macOS releases only by pushing a `macos-v*` tag, which passes `--latest=false` — the web UI's *Draft a new release* form does not, and will take the marker.

The macOS row cannot work that way — macOS releases are deliberately not **Latest**, so its link is pinned to a tag and has to be moved by hand: when a `macos-v*` release ships, repoint this row and the matching one in [`macos/README.md`](macos/README.md) at the new tag's asset URL, version literals included.

A hand-maintained pin goes stale, and this one did within the hour, so [`.github/workflows/links.yml`](.github/workflows/links.yml) checks the docs against the live releases — on every push and pull request, within seconds of a release being published, edited or deleted, and weekly in case something moved without any of those:

| check | goes red when |
|---|---|
| every `/releases` and `/tags` URL in every README resolves | a link 404s |
| every `<app>-v*` tag a README names — in a link **or** in the prose beside it — is that app's newest release | the macOS pin, or a version written next to it, is left behind |
| `/releases/latest/download/<exe>` resolves, and names the exe the `.csproj` actually builds | a macOS release takes the **Latest** marker, or the assembly is renamed on one side only |
| the newest release of every app is reachable from a README | a release ships and no doc mentions it |

The last check exempts whichever app holds the **Latest** marker, since its asset-scoped link already follows it — so the Windows row stays self-maintaining instead of being dragged back into a hand-written pin.

## License

MIT — see [LICENSE](LICENSE).

`windows/Resources/TACTTool.exe` is a redistributed third-party binary and is not covered by that license; its notices are in [`windows/Resources/THIRD-PARTY.md`](windows/Resources/THIRD-PARTY.md).
