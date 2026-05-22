# Ocean Flame

A web-based firmware customization tool for Snowsky Echo devices. Ocean Flame is a fork of [FlameOcean](https://github.com/Losses/flame-ocean-website) with added support for the **Snowsky Echo (non-Mini)** firmware format, alongside the original Echo Mini support.

## Features

- **Firmware Analysis**: Parse and analyze Snowsky Echo and Echo Mini firmware files
- **Resource Extraction**: Extract and display font glyphs (SMALL/LARGE) organized by Unicode planes
- **Image Viewing**: View embedded bitmap images in RGB565 format
- **Image Replacement**: Replace firmware images with custom ones via drag-and-drop, paste, or file selection
- **Font Replacement**: Replace firmware fonts with custom pixel/bitmap fonts via drag-and-drop or paste
- **Batch Operations**: Replace multiple images at once by filename matching
- **Image Categories**: Images are organized into named categories (Light Theme, Dark Theme, Main Menu, List, Now Playing) for easier navigation
- **Export Single Image**: Export the currently selected image as a PNG file directly from the toolbar
- **Export All**: Download modified firmware or export all images as a ZIP archive for easy editing

## Tech Stack

- Svelte 5 + SvelteKit
- TypeScript
- Web Workers for heavy processing

## Usage

1. Open the application in a web browser
2. Drop a firmware file (`.img` or `.bin`) onto the window or click to browse
3. Navigate the resource tree to view fonts and images
4. Replace images by:
   - Dragging and dropping image files onto the viewer
   - Pasting images from clipboard (Ctrl+V)
   - Clicking the import button and selecting files
5. Replace fonts by:
   - Dragging and dropping font files (.ttf, .otf, .woff, .woff2) onto the font viewer
   - Pasting font files from clipboard (Ctrl+V)
6. Export the modified firmware (Ctrl+S)
7. To export a single image as PNG, select it in the tree and click the **Export Image** button in the toolbar

## Compatibility

This tool supports:

- **Snowsky Echo Mini** — original FlameOcean compatibility, fully supported
- **Snowsky Echo (non-Mini)** — added in Ocean Flame, tested on V1.5.0 firmware

Other Snowsky device firmware may work but has not been tested. Use at your own risk.

## WARNING

**This tool modifies device firmware. Improper use may brick your device.**

- Always backup your original firmware before making modifications
- Ensure replacement images match the exact dimensions of the original
- Flash modified firmware at your own risk
- There is no guarantee of recovery if something goes wrong

## Support

This tool is provided as-is. Don't expect support, troubleshooting help, or compensation for bricked devices. You're modifying firmware — you already know what you're signing up for.

## Credits

Forked from [FlameOcean](https://github.com/Losses/flame-ocean-website) by [Losses](https://github.com/Losses).

## Development

```bash
bun install
bun run dev
```

## Building

```bash
bun run build
```

The static site will be output to `build/`.
