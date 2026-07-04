# Glyph Flame

A web-based **font editor** for Snowsky Echo / Echo Mini firmware.
Specialized tool for editing bitmap fonts (SMALL / LARGE) in firmware images.

Fork of [ocean-flame](https://github.com/unitreign/ocean-flame)


<img width="1919" height="945" alt="スクリーンショット " src="https://github.com/user-attachments/assets/f46dd60d-0206-4c3d-8886-99054b0e533b" />






## Features

- **Font Plane Viewer** — Browse and edit glyphs by Unicode plane (Hiragana, CJK, etc.)
- **BDF Import** — Import bitmap fonts from `.bdf` files (Unicode supported)
- **Glyph Editor** — Pixel-level editing with grid guide, range selection, and keyboard movement
- **Batch Operations** — Align all glyphs to left, apply Small/Large fonts separately
- **Live Preview** — See changes in real-time
- **Firmware Export** — Download modified `.img` file with updated fonts


## Tech Stack

- Svelte 5 + SvelteKit
- TypeScript
- Web Workers for heavy processing
- Font Awesome 6


## Usage

1. Open a firmware `.img` file
2. Select a font plane (Hiragana, CJK Unified Ideographs, etc.)
3. Drag & drop a compatible BDF font file
4. Edit glyphs individually or use batch tools
5. Click **"Apply This Glyph"** or **"Apply Small/Large"** to commit changes
6. Download the modified firmware with **"Download .img"**


## Key Functions

- **Align All Left** — Left-align all glyphs while preserving shape
- **Range Selection** — Drag to select multiple pixels, move with arrow keys
- **Grid Guide** — Toggle on/off for precise editing
- **BDF Import** — Supports Unicode encoded fonts


## Compatibility

| Device | Status |
|---|---|
| Snowsky Echo | ✅ Tested on V1.6.0 firmware |
| Snowsky Echo Mini | ⚠ May work, untested |
| Other Rockchip RKnano devices | ⚠ May work, untested |

> **Note**: This tool has only been verified to work properly on Echo (non-Mini). Use on Echo Mini at your own risk.


## Installation Guide

See the in-app Installation Guide (bottom of the tools panel) for step-by-step flashing instructions.

Short version: remove SD card → turn on → connect USB → USB Data mode → copy `.img` to internal memory root → eject → restart.

> ⚠ The firmware upgrade may format the internal memory. Back up your songs before upgrading.


## WARNING

**This tool modifies device firmware. Improper use may brick your device.**

- Always back up your original firmware before making changes
- Replacement images must match the exact dimensions of the original
- Flash at your own risk — no recovery guarantee


## Support

Provided as-is. No support, troubleshooting, or compensation for bricked devices.


## Credits

Forked from [FlameOcean](https://github.com/unitreign/ocean-flame) by [unitreign](https://github.com/unitreign).



## Development

```bash
bun install
bun run dev
```


## Building

```bash
bun run build
```


## ToDo
* Write detailed instructions on how to use this tool.


