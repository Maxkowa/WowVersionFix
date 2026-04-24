# WoW Version Fix

A tiny Windows app that downloads specific files (`Wow.exe`, `Wow_loader.dll`, etc.) from any historical World of Warcraft build — straight from Blizzard's CDN.

No install. No setup. Double-click and go.

## Download

> **[⬇ Download the latest release (.exe)](https://github.com/Maxkowa/WowVersionFix/releases/latest)**

Windows 10/11 x64. ~75 MB (self-contained — no .NET install needed).

On first launch, Windows SmartScreen may warn that the app is unrecognized (it's unsigned). Click **More info → Run anyway**.

## How it works

- Fetches the live build list from [wago.tools](https://wago.tools/builds).
- Uses the build's config hashes to talk to Blizzard's CDN (same as the Battle.net client).
- Invokes an embedded copy of [TACTTool](https://github.com/wowdev/TACTSharp) to pull just the files you selected.
- Drops them into `Desktop\WowVersionFix\{product}_{version}\`.

## Usage

1. Launch `WowVersionFix.exe`.
2. Pick a **Product** (wow / wowt / wow_beta / wow_classic / …).
3. Pick a **Version** from the dropdown.
4. Tick the files you want (`Wow.exe`, `Wow_loader.dll`) or type others comma-separated.
5. Click **Extract**. Done.

## Build from source

Requires [.NET 8 SDK](https://dotnet.microsoft.com/download).

```bash
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

Output lands in `bin/Release/net8.0-windows/win-x64/publish/`.

## Credits

- [TACTSharp / TACTTool](https://github.com/wowdev/TACTSharp) by Marlamin — does all the heavy lifting.
- [wago.tools](https://wago.tools) — build index.

## License

MIT
