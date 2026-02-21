#!/usr/bin/env python3
"""
Generate test reference files for color extraction using the REAL Python implementation.

This script uses the actual Python ThemeColorAnalyzer to generate reference data
for testing TypeScript equivalence.
"""

import json
import sys
from pathlib import Path

try:
    from theme_extractor import (
        ThemeColorAnalyzer,
        _discover_flac_patch_point,
        _discover_menu_patch_point,
    )
except ImportError as e:
    print(f"Error importing: {e}")
    sys.exit(1)


def generate_color_extraction_references(firmware_path: Path, output_dir: Path):
    """Generate color extraction reference files"""

    print(f"\n=== Generating color extraction references for {firmware_path.name} ===")

    # Load firmware
    with open(firmware_path, 'rb') as f:
        data = bytearray(f.read())

    print(f"Firmware size: {len(data):,} bytes")

    # Discover functions
    flac_addr = _discover_flac_patch_point(data, 0x80000, 0x100000)
    menu_addr = _discover_menu_patch_point(data, 0x30000, 0x50000)

    print(f"FLAC patch point: 0x{flac_addr:05X}" if flac_addr else "FLAC not found")
    print(f"Menu patch point: 0x{menu_addr:05X}" if menu_addr else "Menu not found")

    # Create analyzer
    analyzer = ThemeColorAnalyzer(str(firmware_path))

    results = {}

    # Analyze FLAC function behavior
    if flac_addr:
        flac_behavior = analyzer._analyze_flac_function_behavior(flac_addr)
        print(f"\nFLAC behavior:")
        print(f"  is_flac: {flac_behavior['is_flac']}")
        print(f"  color_for_4: 0x{flac_behavior['color_for_4']:04X} ({flac_behavior['color_for_4']})")
        print(f"  color_for_other: 0x{flac_behavior['color_for_other']:04X} ({flac_behavior['color_for_other']})")
        print(f"  movw_addr_4: {flac_behavior['movw_addr_4']}")
        print(f"  movw_instr_4: {flac_behavior['movw_instr_4']}")
        print(f"  movw_addr_other: {flac_behavior['movw_addr_other']}")
        print(f"  movw_instr_other: {flac_behavior['movw_instr_other']}")

        results['flac'] = {
            'addr': flac_addr,
            'behavior': flac_behavior
        }

    # Analyze Menu function behavior
    if menu_addr:
        menu_behavior = analyzer._analyze_theme_function_behavior(menu_addr)
        print(f"\nMenu behavior:")
        print(f"  cmp_r12_count: {menu_behavior['cmp_r12_count']}")
        print(f"  distinct_colors: {menu_behavior['distinct_colors']}")
        print(f"  strh_count: {menu_behavior['strh_count']}")
        print(f"  colors: {sorted(menu_behavior['colors']) if menu_behavior['colors'] else []}")

        results['menu'] = {
            'addr': menu_addr,
            'behavior': {
                'cmp_r12_count': menu_behavior['cmp_r12_count'],
                'distinct_colors': menu_behavior['distinct_colors'],
                'strh_count': menu_behavior['strh_count'],
                'colors': sorted(menu_behavior['colors']) if menu_behavior['colors'] else []
            }
        }

    # Save results
    output_path = output_dir / 'color_extraction.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved color extraction reference: {output_path}")

    return results


def main():
    firmware_path = Path('HIFIEC10.IMG')
    output_dir = Path('test-results')

    if not firmware_path.exists():
        print(f"Error: Firmware file not found: {firmware_path}")
        sys.exit(1)

    output_dir.mkdir(exist_ok=True)

    generate_color_extraction_references(firmware_path, output_dir)

    print("\n=== Done ===")


if __name__ == '__main__':
    main()
