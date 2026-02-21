#!/usr/bin/env python3
"""
Generate test reference files using the REAL Python theme_patcher.py implementation.

This script uses the actual Python implementation functions as ground truth,
not simplified versions written to match TypeScript.
"""

import json
import sys
from pathlib import Path

# Import from the REAL Python implementations
try:
    from theme_extractor import (
        _discover_flac_patch_point,
        _discover_menu_patch_point,
    )
    from theme_patcher import (
        NopSlideFinder,
        encode_bl,
        PatchMetadata,
        crc16,
    )
except ImportError as e:
    print(f"Error importing: {e}")
    sys.exit(1)


def generate_references(firmware_path: Path, output_dir: Path):
    """Generate all test reference files for a firmware"""

    print(f"\n=== Generating references for {firmware_path.name} ===")

    # Load firmware
    with open(firmware_path, 'rb') as f:
        data = bytearray(f.read())

    print(f"Firmware size: {len(data):,} bytes")

    # Discover patch points using real functions
    flac_addr = _discover_flac_patch_point(data, 0x80000, 0x100000)
    menu_addr = _discover_menu_patch_point(data, 0x30000, 0x50000)

    print(f"FLAC patch point: 0x{flac_addr:08X}" if flac_addr else "FLAC not found")
    print(f"Menu patch point: 0x{menu_addr:08X}" if menu_addr else "Menu not found")

    # Use real NopSlideFinder
    finder = NopSlideFinder(data)
    slides = finder.find_all_slides()
    print(f"Found {len(slides)} NOP slides")

    # Use real select_best_slide
    if flac_addr and menu_addr:
        func_addrs = [flac_addr, menu_addr]
        best_slide = finder.select_best_slide(func_addrs, 250)

        if best_slide:
            print(f"Selected NOP slide: 0x{best_slide.start:08X} - 0x{best_slide.end:08X} ({best_slide.size} bytes)")

            # Test colors
            flac_colors = [0xF800, 0x001F, 0xFFE0, 0x07FF, 0x0000]
            menu_colors = [0xF800] * 15

            # Use real encode_bl
            flac_code_addr = best_slide.start
            menu_code_addr = best_slide.start + 120

            bl_flac = encode_bl(flac_addr, flac_code_addr)
            bl_menu = encode_bl(menu_addr, menu_code_addr)

            print(f"FLAC BL: {' '.join(f'{b:02X}' for b in bl_flac)}")
            print(f"Menu BL: {' '.join(f'{b:02X}' for b in bl_menu)}")

            # Create patched firmware
            patched_data = bytearray(data)
            patched_data[flac_addr:flac_addr+4] = bl_flac
            patched_data[menu_addr:menu_addr+4] = bl_menu

            # Generate metadata using real PatchMetadata class
            metadata = PatchMetadata(
                timestamp=0,  # Placeholder
                flac_colors=flac_colors,
                menu_colors=menu_colors
            )
            metadata_bytes = metadata.to_bytes()
            metadata_addr = best_slide.end - 51
            patched_data[metadata_addr:metadata_addr + 51] = metadata_bytes

            # Save patched firmware
            output_path = output_dir / 'patched_firmware.bin'
            with open(output_path, 'wb') as f:
                f.write(patched_data)
            print(f"Saved patched firmware: {output_path}")

            # Generate discovery result
            discovery_result = {
                'version': 'V3.1.0',
                'patchPoints': {
                    'flac': {
                        'patchAddr': flac_addr,
                        'originalBytes': ' '.join(f'{b:02X}' for b in data[flac_addr:flac_addr+4]),
                        'newBytes': ' '.join(f'{b:02X}' for b in bl_flac)
                    },
                    'menu': {
                        'patchAddr': menu_addr,
                        'originalBytes': ' '.join(f'{b:02X}' for b in data[menu_addr:menu_addr+4]),
                        'newBytes': ' '.join(f'{b:02X}' for b in bl_menu)
                    }
                },
                'nopSlide': {
                    'start': best_slide.start,
                    'end': best_slide.end,
                    'size': best_slide.size,
                    'source': best_slide.source
                },
                'metadataAddr': metadata_addr,
                'flacColors': flac_colors,
                'menuColors': menu_colors
            }

            # Save individual reference files
            with open(output_dir / 'flac_discovery.json', 'w') as f:
                json.dump({'patchPoints': {'flac': discovery_result['patchPoints']['flac']}}, f, indent=2)

            with open(output_dir / 'menu_discovery.json', 'w') as f:
                json.dump({'patchPoints': {'menu': discovery_result['patchPoints']['menu']}}, f, indent=2)

            with open(output_dir / 'nop_slide.json', 'w') as f:
                json.dump({'nopSlide': discovery_result['nopSlide']}, f, indent=2)

            with open(output_dir / 'patch_output.json', 'w') as f:
                json.dump(discovery_result, f, indent=2)

            print("All reference files generated")
        else:
            print("No suitable NOP slide found")
    else:
        print("Error: Both FLAC and Menu patch points must be found")


def main():
    firmware_path = Path('HIFIEC10.IMG')
    output_dir = Path('test-results')

    if not firmware_path.exists():
        print(f"Error: Firmware file not found: {firmware_path}")
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    generate_references(firmware_path, output_dir)

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
