# Ocean Flame

A web-based firmware image editor for Snowsky Echo and Echo Mini devices. Fork of [FlameOcean](https://github.com/Losses/flame-ocean-website) with Echo (non-Mini) support.

**Latest:** [ocean-flame-nu.vercel.app](https://ocean-flame-nu.vercel.app)
**Legacy (Win98 UI):** [ocean-flame-legacy.vercel.app](https://ocean-flame-legacy.vercel.app)

## Features

### Latest
- **Redesigned UI** — Clean modern interface with 6 web app themes (Catppuccin Mocha, Frappé, Macchiato, Latte, Dark Orange, Parchment). Click the app name to cycle themes. Last used theme is remembered. These are UI themes for the web tool — not related to the device firmware.
- **Device Mockup** — Selected images render inside an Echo or Echo Mini device frame. Toggle the frame on/off, switch between device color variants
- **Image Categories** — Images organized into named categories (Shared, Light Theme, Dark Theme) with subcategories like Main Menu, Status Bar, Now Playing, Volume Control, and more
- **Image Search** — Search images by name in the sidebar
- **Installation Guide & About** — Built into the tools panel
- **Auto firmware type detection** — Echo, Echo Mini, or unknown — the tree and mockup adapt accordingly

### Legacy & Latest (both versions)
- **Firmware Analysis** — Parse and analyze Snowsky Echo and Echo Mini firmware files
- **Image Viewing** — View embedded UI images in RGB565 format
- **Image Replacement** — Replace images via drag-and-drop, paste (Ctrl+V), or file picker
- **Font Viewing & Replacement** — View SMALL/LARGE font glyphs by Unicode plane, replace with custom bitmap fonts
- **Sequence Replacer** — Batch-replace a sequence of images by filename matching or video frame extraction
- **Export Single Image** — Export the selected image as PNG
- **Export All Images** — Download all images as a ZIP for offline editing
- **Download Modified Firmware** — Exports as `.img` with the original firmware's filename
- **Color Editing** — View and edit theme colors (Progress Bar, Marquee, FLAC) where supported

## Tech Stack

- Svelte 5 + SvelteKit
- TypeScript
- Web Workers for heavy processing
- Font Awesome 6 (latest only)

## Usage

1. Drop a firmware `.img` file onto the page or click to browse
2. Firmware type (Echo or Echo Mini) is auto-detected
3. Browse or search the sidebar to find images or fonts
4. Select an image — it renders inside the device mockup. Toggle the frame on/off above the viewer
5. Replace by dragging a new image onto the viewer, pasting, or using Import Image
6. Download modified firmware with Ctrl+S or the Download .img button

## Compatibility

| Device | Status |
|---|---|
| Snowsky Echo | ✅ Tested on V1.5.0 firmware |
| Snowsky Echo Mini | ✅ Original FlameOcean compatibility |
| Other Rockchip RKnano devices | ⚠ May work, untested |

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

Forked from [FlameOcean](https://github.com/Losses/flame-ocean-website) by [Losses](https://github.com/Losses).
Theming guide: [youtube.com/watch?v=p8HDWJaDaP4](https://www.youtube.com/watch?v=p8HDWJaDaP4)

## Development

```bash
bun install
bun run dev
```

## Building

```bash
bun run build
```