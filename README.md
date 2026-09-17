# WoW Version Fix

Two separate tools for pulling historical World of Warcraft client files straight from Blizzard's CDN — one for Windows, one for macOS.

They are independent apps with their own downloads, their own releases and their own docs. Pick the one for your platform.

## The apps

| App | Platform | What it does | Download | Source |
|---|---|---|---|---|
| **WoW Version Fix** | Windows 10/11 x64 | Extracts individual files (`Wow.exe`, `Wow_loader.dll`, …) from any historical build into a folder of your choice | [WowVersionFix.exe](https://github.com/Maxkowa/WowVersionFix/releases/download/v1.0.0/WowVersionFix.exe) — currently `v1.0.0` | [`windows/`](windows/) |
| **WoW Build Switcher** | macOS 14+ | Downloads a whole historical client `.app` bundle and swaps it into your game folder | no release yet — [build from source](macos/README.md#build-from-source) | [`macos/`](macos/) |

Details, usage and build instructions live in [`windows/README.md`](windows/README.md) and [`macos/README.md`](macos/README.md).

## Releases

Each app releases on its own tag, so every tag produces its own release with only that app's asset:

| Tag | Builds | Publishes |
|---|---|---|
| `windows-v*` | the C# / WinForms app | `WowVersionFix.exe` (self-contained, single file) |
| `macos-v*` | the SwiftUI app | a zipped `WoW Build Switcher.app` (universal — arm64 + Intel) |

Every tag is listed at [**/tags**](https://github.com/Maxkowa/WowVersionFix/tags) — the prefix tells you which app it is. Each one links to its own release page and assets.

The original `v1.0.0` release predates the split and holds the Windows `.exe`; its download link above stays valid and is still the newest Windows build. Windows releases from here on are tagged `windows-v*`.

Because the two apps share one repo, `/releases/latest` is meaningless for picking an app — it is pinned to the Windows side so it never hands a Windows user a `.app`, but that also means it never points at a macOS build. Always use a tagged link. Don't use `/releases?q=…` either: that box is a full-text search over release notes, so a Windows release whose changelog mentions macOS shows up under `q=macos`.

### Maintaining the download links

The download cells above point at concrete tags, which is the only kind of link that cannot hand out the wrong platform's binary. That means they are updated by hand: when a `windows-v*` or `macos-v*` release ships, repoint that row (and the matching one in the app's own README) at the new tag's asset URL.

## License

MIT — see [LICENSE](LICENSE).

`windows/Resources/TACTTool.exe` is a redistributed third-party binary and is not covered by that license; its notices are in [`windows/Resources/THIRD-PARTY.md`](windows/Resources/THIRD-PARTY.md).
