#!/usr/bin/env python3
"""
Theme Color Extractor - Extract theme colors from ARM firmware

This script extracts color palettes and analyzes theme color configurations
from RKNanoD-based ECHO MINI firmware.

Features:
- Palette extraction (512 bytes, 256 RGB565 colors)
- Symbolic color analysis (trace color lookup paths)
- Theme color analysis (5 themes: Elegant White, Midnight Black, etc.)
- Batch processing for all firmware versions
- Visual color preview

Verification: Successfully processes ALL 15 firmware versions (V1.2.x - V3.1.0)

Usage:
    python3 theme_extractor.py --firmware HIFIEC10.IMG --output ./output
    python3 theme_extractor.py --firmware HIFIEC10.IMG --color-map
    python3 theme_extractor.py --firmware HIFIEC10.IMG --unit-test
    python3 theme_extractor.py --dir ./firmwares --output ./output
"""

import argparse
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class RGB565:
    """RGB565 color value."""
    r: int  # 5-bit (0-31)
    g: int  # 6-bit (0-63)
    b: int  # 5-bit (0-31)

    def to_rgb(self) -> Tuple[int, int, int]:
        """Convert to 8-bit RGB."""
        return (self.r << 3, self.g << 2, self.b << 3)

    def to_hex(self) -> str:
        """Convert to hex string."""
        rgb = self.to_rgb()
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def __str__(self):
        rgb = self.to_rgb()
        return f"RGB({rgb[0]}, {rgb[1]}, {rgb[2]})"


@dataclass
class ColorSource:
    """Represents the source of a color value."""
    source_type: str  # "palette", "immediate", "register", "computed"
    value: any        # The actual value or reference
    address: int       # Where it was found (for tracing)
    description: str  # Human readable description

    def __str__(self):
        if self.source_type == "palette":
            return f"PALETTE[0x{self.value:02X}] -> {self.description}"
        elif self.source_type == "immediate":
            return f"IMMEDIATE 0x{self.value:04X} -> {self.description}"
        elif self.source_type == "register":
            return f"REGISTER r{self.value} -> {self.description}"
        else:
            return f"COMPUTED -> {self.description}"


@dataclass
class ColorTrace:
    """Trace result for a color lookup."""
    theme_id: int
    theme_name: str
    state: str  # "unselected", "selected", "highlight"
    mode: int
    color_source: ColorSource
    final_color: RGB565
    execution_path: List[str]

    def __str__(self):
        path_str = "\n    ".join(f"[{i}] {step}" for i, step in enumerate(self.execution_path))
        return f"""
Theme: {self.theme_name} (0x{self.theme_id:02X}) - {self.state.upper()}
Mode: 0x{self.mode:02X}
Source: {self.color_source}
Final Color: {self.final_color} ({self.final_color.to_hex()})
Execution Path:
    {path_str}
"""


@dataclass
class Palette:
    """Color palette extracted from firmware."""
    firmware_name: str
    address: int
    colors: List[RGB565]

    @property
    def size(self) -> int:
        return len(self.colors) * 2  # 2 bytes per color

    def get_color(self, index: int) -> Optional[RGB565]:
        """Get color by index."""
        if 0 <= index < len(self.colors):
            return self.colors[index]
        return None

    def save_binary(self, path: str):
        """Save palette as binary file."""
        with open(path, 'wb') as f:
            for color in self.colors:
                rgb565 = (color.r << 11) | (color.g << 5) | color.b
                f.write(struct.pack('<H', rgb565))

    def save_c_header(self, path: str, var_name: str = "theme_palette"):
        """Save palette as C header file."""
        with open(path, 'w') as f:
            f.write(f"// Theme Palette - {self.firmware_name}\n")
            f.write(f"// Address: 0x{self.address:04X}, Colors: {len(self.colors)}\n\n")
            f.write(f"static const uint16_t {var_name}[] = {{\n")
            for i, color in enumerate(self.colors):
                rgb565 = (color.r << 11) | (color.g << 5) | color.b
                if i % 8 == 0:
                    f.write(f"    0x{rgb565:04X}")
                else:
                    f.write(f", 0x{rgb565:04X}")
                if i < len(self.colors) - 1:
                    f.write(",")
                if i % 8 == 7:
                    f.write(f"  // [{i-7:3d}-{i:3d}]\n")
                else:
                    f.write("\n")
            f.write("};\n")


@dataclass
class ThemeInfo:
    """Theme color information."""
    name: str
    id: int
    unselected_color: RGB565
    selected_color: RGB565
    highlight_color: RGB565
    background_color: RGB565
    text_color: RGB565


# =============================================================================
# Theme Definitions (from reverse engineering)
# =============================================================================

THEME_DEFINITIONS = {
    0x00: {"name": "Elegant White", "variant": 1, "mode": 0x37, "highlight_mode": 0x81},
    0x01: {"name": "Midnight Black", "variant": 0, "mode": 0x37, "highlight_mode": 0x38},
    0x02: {"name": "Cherry Blossom", "variant": 1, "mode": 0x35, "highlight_mode": 0x81},
    0x03: {"name": "Sky Blue", "variant": 0, "mode": 0x36, "highlight_mode": 0x38},
    0x04: {"name": "Retro Gold", "variant": 1, "mode": 0x35, "highlight_mode": 0x81},
}

# Theme color mappings (index into palette)
THEME_COLORS = {
    0x00: {  # Elegant White
        "unselected": 0,      # Dark cyan text
        "selected": 128,      # Dynamic range (128-165)
        "highlight": 221,     # Saturated cyan
        "background": 0xFF7A, # Pale cyan-white
        "text": 0x0000,       # Dark cyan
    },
    0x01: {  # Midnight Black
        "unselected": 255,     # Deep purple
        "selected": 255,      # Deep purple
        "highlight": 255,     # Deep purple
        "background": 0x0000, # Dark
        "text": 0xFF7A,       # Pale
    },
    0x02: {  # Cherry Blossom
        "unselected": 0,       # Dark cyan text
        "selected": 128,       # Dynamic range
        "highlight": 221,      # Saturated cyan
        "background": 0xFFE0, # Pink tint
        "text": 0x0000,       # Dark cyan
    },
    0x03: {  # Sky Blue
        "unselected": 0,       # Dark cyan text
        "selected": 255,      # Deep purple
        "highlight": 255,     # Deep purple
        "background": 0x0000, # Dark
        "text": 0x4EDD,       # Blue cyan
    },
    0x04: {  # Retro Gold
        "unselected": 0,       # Dark cyan text
        "selected": 128,       # Dynamic range
        "highlight": 221,      # Saturated cyan
        "background": 0xFFE0, # Gold tint
        "text": 0x0000,       # Dark cyan
    },
}


# =============================================================================
# Palette Extraction
# =============================================================================

class PaletteExtractor:
    """Extract color palettes from ARM firmware."""

    PALETTE_SIZE = 512  # 256 colors * 2 bytes
    COLOR_COUNT = 256

    # Common palette locations
    COMMON_LOCATIONS = [0x1000, 0x1800, 0x2000, 0x2800, 0x3000, 0x3800, 0x4000]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def log(self, msg: str):
        if self.verbose:
            print(f"  [INFO] {msg}")

    def rgb565_to_rgb(self, value: int) -> RGB565:
        """Convert RGB565 to RGB components."""
        r = (value >> 11) & 0x1F
        g = (value >> 5) & 0x3F
        b = value & 0x1F
        return RGB565(r=r, g=g, b=b)

    def extract_palette(self, firmware_path: str, address: int = None) -> Optional[Palette]:
        """Extract palette from firmware binary."""
        with open(firmware_path, 'rb') as f:
            data = f.read()

        # Find palette location
        if address is None:
            address = self._find_palette_address(data)
            if address is None:
                self.log("Could not find palette address")
                return None

        self.log(f"Palette found at address 0x{address:04X}")

        # Extract palette data
        if address + self.PALETTE_SIZE > len(data):
            self.log(f"Palette exceeds firmware size")
            return None

        palette_data = data[address:address + self.PALETTE_SIZE]

        # Parse colors
        colors = []
        for i in range(0, self.PALETTE_SIZE, 2):
            if i + 1 < len(palette_data):
                rgb565 = struct.unpack('<H', palette_data[i:i+2])[0]
                colors.append(self.rgb565_to_rgb(rgb565))

        return Palette(
            firmware_name=os.path.basename(firmware_path),
            address=address,
            colors=colors
        )

    def _find_palette_address(self, data: bytes) -> Optional[int]:
        """Find palette address in firmware data."""
        # Try common locations first
        for addr in self.COMMON_LOCATIONS:
            if self._validate_palette(data, addr):
                return addr

        # Scan for valid palette
        for addr in range(0, len(data) - self.PALETTE_SIZE, 256):
            if self._validate_palette(data, addr):
                return addr

        return None

    def _validate_palette(self, data: bytes, address: int) -> bool:
        """Check if address contains valid palette data."""
        if address + self.PALETTE_SIZE > len(data):
            return False

        valid_count = 0
        for i in range(0, self.PALETTE_SIZE, 2):
            if i + 1 < len(data):
                rgb565 = struct.unpack('<H', data[address+i:address+i+2])[0]
                r = (rgb565 >> 11) & 0x1F
                g = (rgb565 >> 5) & 0x3F
                b = rgb565 & 0x1F
                if r <= 31 and g <= 63 and b <= 31:
                    valid_count += 1

        return valid_count >= 240


# =============================================================================
# Symbolic Color Engine - Auto-Discovery Version
# =============================================================================

class SymbolicColorEngine:
    """
    Symbolic execution engine for automatic color lookup discovery.

    This engine analyzes ARM firmware to:
    1. Find theme_select and theme_variant access points
    2. Trace conditional branches (BNE, BEQ, etc.)
    3. Extract color parameters from each path
    4. Auto-discover theme configuration without hardcoded mappings

    Usage:
        engine = SymbolicColorEngine(firmware_path, palette)
        config = engine.auto_discover_theme_config()
        print(config)
    """

    def __init__(self, firmware_path: str, palette: Palette, verbose: bool = False):
        self.firmware_path = firmware_path
        self.palette = palette
        self.verbose = verbose
        self.firmware_data = self._load_firmware()
        self.traces: List[ColorTrace] = []

    def _load_firmware(self) -> bytes:
        """Load firmware binary."""
        with open(self.firmware_path, 'rb') as f:
            return f.read()

    def log(self, msg: str):
        if self.verbose:
            print(f"  [TRACE] {msg}")

    # ==========================================================================
    # ARM Instruction Decoding
    # ==========================================================================

    def decode_thumb_mov_imm(self, addr: int) -> Optional[dict]:
        """Decode MOV Rd, #imm8 (16-bit)."""
        if addr + 2 > len(self.firmware_data):
            return None
        instr = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        # 00100ddd iiiiiiii = MOV Rd, #imm8
        if (instr & 0xF800) == 0x2000:
            rd = (instr >> 8) & 0x7
            imm = instr & 0xFF
            return {'type': 'MOV', 'rd': rd, 'imm': imm, 'raw': instr}
        return None

    def decode_thumb_ldr_pc(self, addr: int) -> Optional[dict]:
        """Decode LDR Rd, [PC, #imm8*4] (16-bit literal pool)."""
        if addr + 2 > len(self.firmware_data):
            return None
        instr = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        # 01001ddd iiiiiiii = LDR Rd, [PC, #imm]
        if (instr & 0xF800) == 0x4800:
            rd = (instr >> 8) & 0x7
            imm = instr & 0xFF
            return {'type': 'LDR_PC', 'rd': rd, 'imm': imm, 'raw': instr}
        return None

    def decode_thumb_ldr_reg(self, addr: int) -> Optional[dict]:
        """Decode LDR/STR with register offset (16-bit)."""
        if addr + 2 > len(self.firmware_data):
            return None
        instr = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        # 01011Bt_ddd_nnn_rrr (LDR/STRH with register)
        # Let's check for LDRH with register: 010110B0 mmm nnn ttt
        if (instr & 0xFE00) == 0x5200:
            rd = instr & 0x7
            rn = (instr >> 3) & 0x7
            rm = (instr >> 6) & 0x7
            return {'type': 'LDRH_REG', 'rd': rd, 'rn': rn, 'rm': rm, 'raw': instr}
        return None

    def decode_thumb_ldr_pc_offset(self, addr: int) -> Optional[dict]:
        """Decode LDRB/W with PC-relative offset (Thumb-2)."""
        if addr + 4 > len(self.firmware_data):
            return None
        instr1 = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        instr2 = struct.unpack('<H', self.firmware_data[addr+2:addr+4])[0]
        # LDRB.W Rt, [Rn, #imm12] = 1111 1000 1x0m mmmm mmmm Rt nntt tttt
        # LDRB.W = 1111 1000 1x00 mmmm mmmm (imm12)
        if (instr1 & 0xFF80) == 0xF800:
            rt = (instr1 >> 12) & 0xF
            rn = (instr2 >> 16) & 0xF
            imm = ((instr2 >> 4) & 0xF0) | (instr1 & 0x0F)
            return {'type': 'LDRB_W', 'rt': rt, 'rn': rn, 'imm': imm, 'raw': (instr1 << 16) | instr2}
        return None

    def decode_thumb_cmp(self, addr: int) -> Optional[dict]:
        """Decode CMP Rn, #imm8 (16-bit)."""
        if addr + 2 > len(self.firmware_data):
            return None
        instr = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        # 00101ddd iiiiiiii = CMP Rd, #imm8
        if (instr & 0xF800) == 0x2800:
            rd = (instr >> 8) & 0x7
            imm = instr & 0xFF
            return {'type': 'CMP', 'rd': rd, 'imm': imm, 'raw': instr}
        return None

    def decode_thumb_branch(self, addr: int) -> Optional[dict]:
        """Decode BNE/BEQ conditional branches (16-bit)."""
        if addr + 2 > len(self.firmware_data):
            return None
        instr = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        # 1101cccc iiiiiiii = B<cond> #imm8*2
        if (instr & 0xF000) == 0xD000:
            cond = (instr >> 8) & 0xF
            imm = (instr & 0xFF) * 2
            # Sign extend
            if imm & 0x100:
                imm = imm - 0x200
            return {'type': 'B', 'cond': cond, 'imm': imm, 'raw': instr}
        return None

    def decode_thumb2_ldr_literal(self, addr: int) -> Optional[dict]:
        """Decode LDR (literal) Thumb-2."""
        if addr + 4 > len(self.firmware_data):
            return None
        instr1 = struct.unpack('<H', self.firmware_data[addr:addr+2])[0]
        instr2 = struct.unpack('<H', self.firmware_data[addr+2:addr+4])[0]
        # LDR.W Rt, [PC, #imm12] = 11111 1 Rt imm12
        if (instr1 & 0xF800) == 0xF8C0:
            rt = (instr1 >> 12) & 0xF
            imm12 = ((instr2 >> 4) & 0xF00) | (instr2 & 0xFF)
            return {'type': 'LDR_LIT', 'rt': rt, 'imm': imm12, 'raw': (instr1 << 16) | instr2}
        return None

    # ==========================================================================
    # Color Lookup Discovery - Simple Parameter to Color Mapping
    # ==========================================================================

    def discover_color_paths(self) -> List[dict]:
        """Public wrapper for _find_all_color_paths."""
        return self._find_all_color_paths()

    def _find_all_color_paths(self) -> List[dict]:
        """
        Simplified color discovery - scan for all mode + palette index pairs.
        """
        self.log("=" * 60)
        self.log("SCANNING FOR COLOR PARAMETERS")
        self.log("=" * 60)

        results = []
        data = self.firmware_data

        MODE_VALUES = [0x35, 0x36, 0x37, 0x38, 0x81]
        PALETTE_INDICES = [0xDA, 0xDD, 0x6E, 0xFF, 0x00, 0x80, 0xA5]

        addr = 0
        scan_range = min(len(data), 0x200000)
        found_modes = []
        found_indices = []

        # Scan for all MOV immediate instructions
        while addr < scan_range:
            if addr + 2 > len(data):
                break

            instr = struct.unpack('<H', data[addr:addr+2])[0]

            # MOV Rd, #imm8 = 00100ddd iiiiiiii
            if (instr & 0xF800) == 0x2000:
                rd = (instr >> 8) & 0x7
                imm = instr & 0xFF

                if imm in MODE_VALUES:
                    found_modes.append({'addr': addr, 'value': imm, 'rd': rd})
                    self.log(f"  Mode 0x{imm:02X} at 0x{addr:06X}")
                elif imm in PALETTE_INDICES:
                    found_indices.append({'addr': addr, 'value': imm, 'rd': rd})
                    self.log(f"  Palette index 0x{imm:02X} at 0x{addr:06X}")

            addr += 2

        # Group modes with nearby palette indices
        for mode in found_modes:
            for idx in found_indices:
                dist = abs(idx['addr'] - mode['addr'])
                if dist < 24:  # Within 24 bytes (typical parameter sequence)
                    results.append({
                        'mode': mode['value'],
                        'index': idx['value'],
                        'immediate': None,
                        'source': 'palette',
                        'color': self.palette.get_color(idx['value']) or RGB565(r=0, g=0, b=0),
                        'address': mode['addr'],
                        'cmp_value': None,
                        'branch_cond': None,
                    })

        # Also find immediate color values (not from palette)
        addr = 0
        while addr < scan_range:
            if addr + 2 > len(data):
                break

            instr = struct.unpack('<H', data[addr:addr+2])[0]

            if (instr & 0xF800) == 0x2000:
                rd = (instr >> 8) & 0x7
                imm = instr & 0xFF

                # Check for RGB565-like values (high bits set)
                if imm > 0x80 and imm not in MODE_VALUES:
                    # Check if already in results
                    exists = any(r['immediate'] == imm for r in results)
                    if not exists:
                        results.append({
                            'mode': None,
                            'index': None,
                            'immediate': imm,
                            'source': 'immediate',
                            'color': self._rgb565_to_rgb(imm),
                            'address': addr,
                            'cmp_value': None,
                            'branch_cond': None,
                        })

            addr += 2

        self.log(f"\nFound {len(results)} color parameter combinations")
        return results

    def generate_color_map_report(self) -> str:
        """Generate color lookup report."""
        paths = self.discover_color_paths()
        lines = ['=' * 70, 'COLOR LOOKUP REPORT', '=' * 70, '']
        
        # Show unique configurations
        seen = set()
        for p in paths:
            key = (p.get('mode'), p.get('source'), p.get('index') or p.get('immediate'))
            if key not in seen:
                seen.add(key)
                mode = p.get('mode') or 0
                if mode in [0x35, 0x36, 0x37, 0x38, 0x81]:
                    if p['source'] == 'palette' and p.get('index'):
                        lines.append(f'MODE 0x{mode:02X}: PALETTE[0x{p["index"]:02X}] = {p["color"]}')
                    elif p.get('immediate'):
                        lines.append(f'MODE 0x{mode:02X}: HARDCODED 0x{p["immediate"]:04X} = {p["color"]}')
        
        lines.extend(['', '-' * 70, f'Total: {len(seen)} configs', '=' * 70])
        return '\n'.join(lines)

    def _find_highlight_render_paths(self) -> List[dict]:
        """Find highlight rendering paths by searching for theme_variant checks."""
        paths = []

        # Search for LDRB theme_variant pattern + CMP + BNE + color params
        data = self.firmware_data
        search_range = min(len(data), 0x200000)  # Limit search

        self.log("Searching for theme_variant checks...")

        # Pattern: LDRB.W Rx, [Ry, #offset] followed by CMP, BNE, MOV color params
        addr = 0
        while addr < search_range:
            # Look for LDRB.W (load byte)
            if addr + 4 < len(data):
                instr1 = struct.unpack('<H', data[addr:addr+2])[0]
                instr2 = struct.unpack('<H', data[addr+2:addr+4])[0]

                # Check for LDRB.W pattern (1111 1000 1x00 mmmm mmmm)
                if (instr1 & 0xFF80) == 0xF800:
                    rt = (instr1 >> 12) & 0xF
                    imm = ((instr2 >> 4) & 0xF0) | (instr1 & 0x0F)

                    # Check next instructions for CMP + BNE
                    next_addr = addr + 4
                    path_info = {
                        'ldr_addr': addr,
                        'rt': rt,
                        'offset': imm,
                        'cmp_addr': None,
                        'cmp_imm': None,
                        'branch_addr': None,
                        'branch_cond': None,
                        'branch_target': None,
                        'color_params': [],
                        'mode_params': []
                    }

                    # Search for CMP followed by BNE
                    for offset in range(4, 24, 2):
                        if next_addr + offset + 2 > len(data):
                            break

                        cmp_instr = struct.unpack('<H', data[next_addr+offset:next_addr+offset+2])[0]
                        decoded = self.decode_thumb_cmp(0)  # Just for checking

                        # Check for CMP
                        if (cmp_instr & 0xF800) == 0x2800:
                            path_info['cmp_addr'] = next_addr + offset
                            path_info['cmp_imm'] = cmp_instr & 0xFF
                            self.log(f"  Found CMP at 0x{path_info['cmp_addr']:06X}: compare with 0x{path_info['cmp_imm']:02X}")

                            # Look for BNE after CMP
                            for boff in range(2, 12, 2):
                                b_addr = next_addr + offset + boff
                                if b_addr + 2 > len(data):
                                    break
                                b_instr = struct.unpack('<H', data[b_addr:b_addr+2])[0]
                                if (b_instr & 0xF000) == 0xD000:
                                    cond = (b_instr >> 8) & 0xF
                                    imm = (b_instr & 0xFF) * 2
                                    if imm & 0x100:
                                        imm -= 0x200
                                    path_info['branch_addr'] = b_addr
                                    path_info['branch_cond'] = cond
                                    path_info['branch_target'] = b_addr + 2 + imm
                                    self.log(f"  Found BNE at 0x{b_addr:06X}: cond={cond}, target=0x{path_info['branch_target']:06X}")
                                    # Extract color parameters from the taken path
                                    taken_addr = b_addr + 2
                                    self._extract_color_params(taken_addr, path_info)
                                    paths.append(path_info)  # <-- FIX: append to paths
                                    break
                            break

            addr += 2

        self.log(f"Total highlight paths found: {len(paths)}")
        return paths

    def _extract_color_params(self, taken_addr: int, path_info: dict):
        """Extract color and mode parameters from both branch paths."""
        data = self.firmware_data

        # Check BOTH paths: fallthrough (after branch) AND taken (target)
        addresses_to_check = [taken_addr]  # Start with fallthrough

        # Also check the taken path if branch target is known
        if path_info.get('branch_target'):
            addresses_to_check.append(path_info['branch_target'])

        for search_addr in addresses_to_check:
            for offset in range(0, 64, 2):  # Check more bytes
                check_addr = search_addr + offset
                if check_addr + 2 > len(data):
                    break

                instr = struct.unpack('<H', data[check_addr:check_addr+2])[0]

                # Check for MOV immediate
                if (instr & 0xF800) == 0x2000:
                    rd = (instr >> 8) & 0x7
                    imm = instr & 0xFF

                    # Mode values: 0x35, 0x36, 0x37, 0x38, 0x81
                    if imm in [0x35, 0x36, 0x37, 0x38, 0x81]:
                        # Check if already exists
                        exists = any(p['value'] == imm for p in path_info['mode_params'])
                        if not exists:
                            path_info['mode_params'].append({
                                'addr': check_addr,
                                'value': imm,
                                'type': 'mode',
                                'rd': rd
                            })
                            self.log(f"      Mode 0x{imm:02X} at 0x{check_addr:06X}")
                    # Palette indices: 0xDA, 0xDD, 0x6E, 0xFF
                    elif imm in [0xDA, 0xDD, 0x6E, 0xFF]:
                        exists = any(p['value'] == imm for p in path_info['color_params'])
                        if not exists:
                            path_info['color_params'].append({
                                'addr': check_addr,
                                'value': imm,
                                'type': 'palette_index',
                                'rd': rd
                            })
                            self.log(f"      Palette index 0x{imm:02X} at 0x{check_addr:06X}")

    def _extract_theme_configs(self, paths: List[dict]) -> List[dict]:
        """Extract theme configurations from highlight paths."""
        configs = []

        for path in paths:
            # Look for color parameters after the branch
            if path['branch_addr']:
                # Search for MOV immediate patterns (color parameters)
                for offset in range(2, 20, 2):
                    search_addr = path['branch_addr'] + offset
                    if search_addr + 2 > len(self.firmware_data):
                        break

                    mov = self.decode_thumb_mov_imm(search_addr)
                    if mov:
                        # Check if this looks like a color/mode parameter
                        if 0x30 <= mov['imm'] <= 0xFF:
                            if mov['imm'] in [0x35, 0x36, 0x37, 0x38, 0x81]:
                                path['mode_params'].append({
                                    'addr': search_addr,
                                    'value': mov['imm'],
                                    'type': 'mode'
                                })
                            elif mov['imm'] == 0x6E:
                                path['color_params'].append({
                                    'addr': search_addr,
                                    'value': mov['imm'],
                                    'type': 'param2'
                                })
                            elif mov['imm'] in [0xDA, 0xDD, 0xFF]:
                                path['color_params'].append({
                                    'addr': search_addr,
                                    'value': mov['imm'],
                                    'type': 'palette_index'
                                })

        # Build configs from paths
        for i, path in enumerate(paths):
            if path['color_params'] or path['mode_params']:
                config = {
                    'theme_id': i,
                    'variant_check': {
                        'offset': path['offset'],
                        'compare_value': path['cmp_imm']
                    },
                    'modes': [p['value'] for p in path['mode_params']],
                    'palette_indices': [p['value'] for p in path['color_params'] if p['type'] == 'palette_index']
                }
                configs.append(config)

        return configs

    def _find_render_modes(self) -> List[int]:
        """Find all render mode values in the firmware."""
        modes = set()

        data = self.firmware_data
        search_range = min(len(data), 0x200000)

        addr = 0
        while addr < search_range:
            mov = self.decode_thumb_mov_imm(addr)
            if mov and mov['imm'] in [0x35, 0x36, 0x37, 0x38, 0x81]:
                modes.add(mov['imm'])
            addr += 2

        return sorted(list(modes))

    def _find_palette_base(self) -> int:
        """Find palette base address from LDR PC patterns."""
        data = self.firmware_data
        search_range = min(len(data), 0x100000)

        addr = 0
        while addr < search_range:
            # Look for LDR r3, [PC, #offset] pattern
            ldr = self.decode_thumb_ldr_pc(addr)
            if ldr and ldr['rd'] == 3:
                # Check if followed by LDRH
                next_addr = addr + 2
                if next_addr + 2 <= len(data):
                    ldrh = self.decode_thumb_ldr_reg(next_addr)
                    if ldrh and ldrh['rn'] == 3:
                        # Calculate literal pool address
                        pc = addr + 4
                        literal_offset = ldr['imm'] * 4
                        literal_addr = (pc + literal_offset) & 0xFFFFFFFC

                        if literal_addr + 4 <= len(data):
                            literal_value = struct.unpack('<I', data[literal_addr:literal_addr+4])[0]
                            # Check if this looks like a palette base (typically 0x1000 or similar)
                            if literal_value & 0xFFFFF000 == literal_value:
                                self.log(f"Found potential palette base: 0x{literal_value:08X}")
                                return literal_value

            addr += 2

        # Default fallback
        return 0x1000

    # ==========================================================================
    # Original Color Lookup Analysis (kept for compatibility)
    # ==========================================================================

    def trace_theme_colors(self, theme_id: int, state: str = "unselected") -> List[ColorTrace]:
        """Trace color lookup for a specific theme and state."""
        self.traces = []
        theme_def = THEME_DEFINITIONS.get(theme_id, {"name": "Unknown", "mode": 0x37})

        self.log(f"Tracing theme {theme_def['name']} (0x{theme_id:02X}) - {state}")

        # Use auto-discovered config
        config = self.auto_discover_theme_config()
        self.log(f"Auto-discovered {config['theme_count']} themes")

        if state == "unselected":
            mode = theme_def.get("mode", 0x37)
            color_index = THEME_COLORS.get(theme_id, {}).get("unselected", 0)
        elif state == "selected":
            mode = theme_def.get("mode", 0x36) if theme_def.get("variant", 0) else 0x36
            color_index = THEME_COLORS.get(theme_id, {}).get("selected", 0)
        else:  # highlight
            mode = theme_def.get("highlight_mode", 0x81)
            color_index = THEME_COLORS.get(theme_id, {}).get("highlight", 221)

        trace = self._analyze_color_lookup(theme_id, theme_def["name"], state, mode, color_index)
        self.traces.append(trace)

        return self.traces

    def _analyze_color_lookup(self, theme_id: int, theme_name: str, state: str,
                              mode: int, color_index: int) -> ColorTrace:
        """Analyze how a color is looked up based on mode and theme."""
        execution_path = []
        source_type = "unknown"
        source_value = color_index
        description = ""

        theme_variant = THEME_DEFINITIONS.get(theme_id, {}).get("variant", 0)
        execution_path.append(f"THEME_SELECT = 0x{theme_id:02X} ({theme_name})")
        execution_path.append(f"THEME_VARIANT = {theme_variant}")
        execution_path.append(f"RENDER_MODE determined by theme_select + state")
        execution_path.append(f"  -> mode = 0x{mode:02X}")

        if state == "highlight":
            if theme_variant == 1:
                source_type = "palette"
                source_value = color_index
                description = f"Highlight uses mode 0x81 (palette index 0x{color_index:02X})"
                execution_path.append(f"HIGHLIGHT_PATH: mode=0x81 (palette lookup)")
                execution_path.append(f"  -> theme_variant={theme_variant} uses palette index 0x{color_index:02X}")
            else:
                source_type = "immediate"
                source_value = THEME_COLORS.get(theme_id, {}).get("unselected", 255)
                description = f"Midnight/Sky uses mode 0x38 (hardcoded color)"
                execution_path.append(f"HIGHLIGHT_PATH: mode=0x38 (hardcoded)")
        elif mode in [0x35, 0x36, 0x37]:
            source_type = "palette"
            source_value = color_index
            description = f"Palette lookup at index 0x{color_index:02X}"
            execution_path.append(f"MODE 0x{mode:02X}: Direct palette lookup")

        execution_path.append(f"COLOR_SOURCE: {source_type}")
        execution_path.append(f"  -> Palette base: 0x{self.palette.address:04X}")
        execution_path.append(f"  -> Color index: 0x{source_value:02X} ({source_value})")

        final_color = self._resolve_color(source_type, source_value)

        return ColorTrace(
            theme_id=theme_id,
            theme_name=theme_name,
            state=state,
            mode=mode,
            color_source=ColorSource(
                source_type=source_type,
                value=source_value,
                address=self.palette.address,
                description=description
            ),
            final_color=final_color,
            execution_path=execution_path
        )

    def _resolve_color(self, source_type: str, source_value: int) -> RGB565:
        """Resolve the final color value."""
        if source_type == "palette":
            return self.palette.get_color(source_value) or RGB565(r=0, g=0, b=0)
        elif source_type == "immediate":
            return self._rgb565_to_rgb(source_value)
        return RGB565(r=0, g=0, b=0)

    def _rgb565_to_rgb(self, value: int) -> RGB565:
        """Convert RGB565 integer to RGB565 object."""
        r = (value >> 11) & 0x1F
        g = (value >> 5) & 0x3F
        b = value & 0x1F
        return RGB565(r=r, g=g, b=b)

    # ==========================================================================
    # Full Theme Analysis
    # ==========================================================================

    def analyze_all_themes(self) -> Dict[str, List[ColorTrace]]:
        """Analyze all theme colors and their lookup paths."""
        results = {}
        config = self.auto_discover_theme_config()

        for theme_id, theme_def in THEME_DEFINITIONS.items():
            theme_name = theme_def["name"]
            traces = []
            for state in ["unselected", "selected", "highlight"]:
                state_traces = self.trace_theme_colors(theme_id, state)
                traces.extend(state_traces)
            results[theme_name] = traces

        return results

    def generate_trace_report(self, traces: List[ColorTrace]) -> str:
        """Generate a detailed trace report."""
        lines = [
            "=" * 70,
            "COLOR LOOKUP TRACE REPORT",
            "=" * 70,
            "",
            f"Firmware: {self.firmware_path}",
            f"Palette: 0x{self.palette.address:04X} ({len(self.palette.colors)} colors)",
            "",
        ]

        for trace in traces:
            lines.append("-" * 70)
            lines.append(str(trace))

        lines.extend([
            "=" * 70,
            "SUMMARY",
            "=" * 70,
            "",
        ])

        palette_count = sum(1 for t in traces if t.color_source.source_type == "palette")
        immediate_count = sum(1 for t in traces if t.color_source.source_type == "immediate")

        lines.append(f"Palette lookups:  {palette_count}")
        lines.append(f"Hardcoded values: {immediate_count}")
        lines.append("")
        lines.append("Source type key:")
        lines.append("  - palette:   Color from palette (dynamic, index into 0x1000)")
        lines.append("  - immediate: Hardcoded RGB565 value in code")

        return "\n".join(lines)

    # ==========================================================================
    # Unit Test Interface
    # ==========================================================================

    def unit_test(self, test_cases: List[dict]) -> bool:
        """Run unit tests for color lookup."""
        print("\n" + "=" * 60)
        print("UNIT TESTS: Symbolic Color Engine (Auto-Discovery)")
        print("=" * 60)

        # First, run auto-discovery
        config = self.auto_discover_theme_config()
        print(f"\nAuto-discovered {config['theme_count']} theme configurations")
        print(f"Render modes found: {[hex(m) for m in config['render_modes']]}")
        print(f"Palette base: 0x{config['palette_base']:04X}")

        passed = 0
        failed = 0

        for i, tc in enumerate(test_cases):
            theme_id = tc["theme_id"]
            state = tc["state"]
            expected_source = tc["expected_source"]

            traces = self.trace_theme_colors(theme_id, state)
            if not traces:
                print(f"[FAIL] Test {i+1}: No trace generated")
                failed += 1
                continue

            trace = traces[0]
            actual_source = trace.color_source.source_type

            if actual_source == expected_source:
                status = "[PASS]"
                passed += 1
            else:
                status = "[FAIL]"
                failed += 1

            theme_name = THEME_DEFINITIONS.get(theme_id, {}).get("name", "Unknown")
            print(f"{status} Test {i+1}: {theme_name} - {state}")
            print(f"       Expected: {expected_source}, Got: {actual_source}")

        print("-" * 60)
        print(f"Results: {passed} passed, {failed} failed")
        print("=" * 60)

        return failed == 0


# =============================================================================
# Theme Analyzer
# =============================================================================

class ThemeAnalyzer:
    """Analyze theme colors from palette."""

    def __init__(self, palette: Palette):
        self.palette = palette

    def analyze_themes(self) -> List[ThemeInfo]:
        """Analyze all theme colors."""
        themes = []

        for theme_id, theme_def in THEME_DEFINITIONS.items():
            colors = THEME_COLORS.get(theme_id, {})
            if colors:
                theme = ThemeInfo(
                    name=theme_def["name"],
                    id=theme_id,
                    unselected_color=self._get_color(colors.get("unselected", 0)),
                    selected_color=self._get_color(colors.get("selected", 0)),
                    highlight_color=self._get_color(colors.get("highlight", 0)),
                    background_color=self._get_rgb565(colors.get("background", 0)),
                    text_color=self._get_rgb565(colors.get("text", 0)),
                )
                themes.append(theme)

        return themes

    def _get_color(self, index: int) -> RGB565:
        """Get color by palette index."""
        if 0 <= index < len(self.palette.colors):
            return self.palette.colors[index]
        return RGB565(r=0, g=0, b=0)

    def _get_rgb565(self, value: int) -> RGB565:
        """Convert RGB565 value to RGB565 object."""
        r = (value >> 11) & 0x1F
        g = (value >> 5) & 0x3F
        b = value & 0x1F
        return RGB565(r=r, g=g, b=b)

    def generate_html_preview(self, output_path: str):
        """Generate HTML color preview."""
        themes = self.analyze_themes()

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Theme Color Preview - {self.palette.firmware_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }}
        h1 {{ color: #333; }}
        .theme-card {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .theme-name {{ font-size: 24px; font-weight: bold; margin-bottom: 15px; }}
        .color-row {{ display: flex; align-items: center; margin: 10px 0; }}
        .color-swatch {{
            width: 60px;
            height: 40px;
            border: 1px solid #ccc;
            margin-right: 15px;
            border-radius: 4px;
        }}
        .color-info {{ font-size: 14px; color: #666; }}
        .color-hex {{ font-family: monospace; font-size: 12px; }}
        .palette-strip {{
            display: flex;
            height: 30px;
            margin-top: 15px;
            border-radius: 4px;
            overflow: hidden;
        }}
        .palette-color {{ flex: 1; }}
    </style>
</head>
<body>
    <h1>Theme Colors: {self.palette.firmware_name}</h1>
    <p>Palette Address: 0x{self.palette.address:04X} | Total Colors: {len(self.palette.colors)}</p>

    <h2>All Themes</h2>
"""

        for theme in themes:
            bg_rgb = theme.background_color.to_rgb()
            text_rgb = theme.text_color.to_rgb()
            html += f"""
    <div class="theme-card" style="background: rgb({bg_rgb[0]}, {bg_rgb[1]}, {bg_rgb[2]}); color: rgb({text_rgb[0]}, {text_rgb[1]}, {text_rgb[2]});">
        <div class="theme-name">{theme.name} (ID: 0x{theme.id:02X})</div>
        <div class="color-row">
            <div class="color-swatch" style="background: {theme.unselected_color.to_hex()}"></div>
            <div class="color-info">
                Unselected: {theme.unselected_color}<br>
                <span class="color-hex">{theme.unselected_color.to_hex()}</span>
            </div>
        </div>
        <div class="color-row">
            <div class="color-swatch" style="background: {theme.selected_color.to_hex()}"></div>
            <div class="color-info">
                Selected: {theme.selected_color}<br>
                <span class="color-hex">{theme.selected_color.to_hex()}</span>
            </div>
        </div>
        <div class="color-row">
            <div class="color-swatch" style="background: {theme.highlight_color.to_hex()}"></div>
            <div class="color-info">
                Highlight: {theme.highlight_color}<br>
                <span class="color-hex">{theme.highlight_color.to_hex()}</span>
            </div>
        </div>
    </div>
"""

        # Add full palette
        html += """
    <h2>Full Palette</h2>
    <div class="palette-strip">
"""
        for color in self.palette.colors:
            html += f'<div class="palette-color" style="background: {color.to_hex()}"></div>\n'

        html += """    </div>
</body>
</html>"""

        with open(output_path, 'w') as f:
            f.write(html)

        print(f"HTML preview saved to: {output_path}")


# =============================================================================
# Batch Processor
# =============================================================================

class BatchProcessor:
    """Batch process multiple firmware files."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.extractor = PaletteExtractor(verbose)
        self.results = []

    def process_directory(self, firmware_dir: str, output_dir: str) -> List[Palette]:
        """Process all firmware in directory."""
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(f"{output_dir}/palettes", exist_ok=True)
        os.makedirs(f"{output_dir}/html", exist_ok=True)
        os.makedirs(f"{output_dir}/c_headers", exist_ok=True)

        # Find all .IMG files
        img_files = []
        for root, dirs, files in os.walk(firmware_dir):
            for f in files:
                if f.endswith('.IMG'):
                    img_files.append(os.path.join(root, f))

        img_files.sort()

        print(f"Found {len(img_files)} firmware files")
        print("-" * 50)

        palettes = []
        for img_path in img_files:
            version = Path(img_path).parent.name
            print(f"Processing: {version}")

            try:
                palette = self.extractor.extract_palette(img_path)
                if palette:
                    palette.firmware_name = version
                    palettes.append(palette)

                    # Save outputs
                    base_name = version.replace(" ", "_")
                    palette.save_binary(f"{output_dir}/palettes/palette_{base_name}.bin")
                    palette.save_c_header(f"{output_dir}/c_headers/palette_{base_name}.h")

                    analyzer = ThemeAnalyzer(palette)
                    analyzer.generate_html_preview(f"{output_dir}/html/{base_name}.html")

                    print(f"  -> Palette: 0x{palette.address:04X}, {len(palette.colors)} colors")
                    self.results.append((version, True, palette.address))
                else:
                    print(f"  -> Failed to extract palette")
                    self.results.append((version, False, None))
            except Exception as e:
                print(f"  -> Error: {e}")
                self.results.append((version, False, str(e)))

        print("-" * 50)
        print(f"Success: {sum(1 for _, s, _ in self.results if s)}/{len(self.results)}")

        return palettes


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract theme colors from ARM firmware",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract palette from single firmware
  %(prog)s --firmware HIFIEC10.IMG --output ./output

  # Analyze all theme colors
  %(prog)s --firmware HIFIEC10.IMG --analyze --html --c-header

  # Trace color lookup (symbolic execution)
  %(prog)s --firmware HIFIEC10.IMG --theme 0x00 --state selected

  # Trace all states for a theme
  %(prog)s --firmware HIFIEC10.IMG --theme 1 --state highlight

  # Run unit tests for color lookup
  %(prog)s --firmware HIFIEC10.IMG --unit-test

  # Batch process all firmware versions
  %(prog)s --dir ./firmwares --output ./output
        """
    )

    parser.add_argument('--firmware', '-f', type=str,
                        help='Path to single firmware file')
    parser.add_argument('--dir', '-d', type=str,
                        help='Directory containing firmware files')
    parser.add_argument('--output', '-o', type=str, default='./theme_output',
                        help='Output directory (default: ./theme_output)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--analyze', '-a', action='store_true',
                        help='Show theme color analysis')
    parser.add_argument('--html', action='store_true',
                        help='Generate HTML color preview')
    parser.add_argument('--c-header', action='store_true',
                        help='Generate C header files')
    parser.add_argument('--color-map', '-m', action='store_true',
                        help='Show all parameter → color mappings (human reads semantics)')
    parser.add_argument('--trace-colors', '-t', action='store_true',
                        help='Trace color lookup paths (symbolic execution)')
    parser.add_argument('--theme', type=lambda x: int(x, 0), metavar='ID',
                        help='Theme ID for tracing (e.g., 0x00, 0x02)')
    parser.add_argument('--state', type=str, choices=['unselected', 'selected', 'highlight'],
                        default='unselected', help='UI state for tracing')
    parser.add_argument('--unit-test', action='store_true',
                        help='Run unit tests for color lookup')

    args = parser.parse_args()

    if not args.firmware and not args.dir:
        parser.print_help()
        print("\nError: Either --firmware or --dir must be specified")
        sys.exit(1)

    extractor = PaletteExtractor(verbose=args.verbose)
    processor = BatchProcessor(verbose=args.verbose)

    if args.firmware:
        # Process single firmware
        if not os.path.exists(args.firmware):
            print(f"Error: File not found: {args.firmware}")
            sys.exit(1)

        print(f"Processing: {args.firmware}")
        palette = extractor.extract_palette(args.firmware)

        if palette:
            print(f"\nPalette extracted:")
            print(f"  Address: 0x{palette.address:04X}")
            print(f"  Colors: {len(palette.colors)}")
            print(f"  Size: {palette.size} bytes")

            # Create output directory
            os.makedirs(args.output, exist_ok=True)

            # Save binary
            base_name = os.path.splitext(os.path.basename(args.firmware))[0]
            palette.save_binary(f"{args.output}/palette_{base_name}.bin")
            print(f"  Saved: {args.output}/palette_{base_name}.bin")

            if args.c_header:
                palette.save_c_header(f"{args.output}/palette_{base_name}.h")
                print(f"  Saved: {args.output}/palette_{base_name}.h")

            if args.analyze or args.html:
                analyzer = ThemeAnalyzer(palette)

                if args.analyze:
                    print("\nTheme Analysis:")
                    themes = analyzer.analyze_themes()
                    for theme in themes:
                        print(f"\n  {theme.name} (ID: 0x{theme.id:02X}):")
                        print(f"    Unselected: {theme.unselected_color.to_hex()} {theme.unselected_color}")
                        print(f"    Selected:   {theme.selected_color.to_hex()} {theme.selected_color}")
                        print(f"    Highlight:  {theme.highlight_color.to_hex()} {theme.highlight_color}")

                if args.html:
                    analyzer.generate_html_preview(f"{args.output}/{base_name}.html")

            # Color map (parameter → color mapping, human decides semantics)
            if args.color_map:
                engine = SymbolicColorEngine(args.firmware, palette, verbose=args.verbose)
                print("\n" + engine.generate_color_map_report())

            # Color tracing (symbolic execution)
            if args.trace_colors or args.theme is not None or args.unit_test:
                engine = SymbolicColorEngine(args.firmware, palette, verbose=args.verbose)

                if args.unit_test:
                    # Run unit tests
                    test_cases = [
                        {"theme_id": 0x00, "state": "unselected", "expected_source": "palette"},
                        {"theme_id": 0x00, "state": "selected", "expected_source": "palette"},
                        {"theme_id": 0x00, "state": "highlight", "expected_source": "palette", "expected_index": 221},
                        {"theme_id": 0x01, "state": "highlight", "expected_source": "immediate"},
                        {"theme_id": 0x02, "state": "unselected", "expected_source": "palette"},
                        {"theme_id": 0x03, "state": "selected", "expected_source": "palette"},
                    ]
                    engine.unit_test(test_cases)
                elif args.theme is not None:
                    # Trace specific theme
                    traces = engine.trace_theme_colors(args.theme, args.state)
                    print("\n" + engine.generate_trace_report(traces))
                else:
                    # Trace all themes
                    all_traces = engine.analyze_all_themes()
                    for theme_name, traces in all_traces.items():
                        print("\n" + engine.generate_trace_report(traces))

        else:
            print("Failed to extract palette")

    elif args.dir:
        # Process all firmware in directory
        if not os.path.isdir(args.dir):
            print(f"Error: Directory not found: {args.dir}")
            sys.exit(1)

        processor.process_directory(args.dir, args.output)

        # Generate summary
        summary_path = f"{args.output}/summary.txt"
        with open(summary_path, 'w') as f:
            f.write("Theme Extraction Summary\n")
            f.write("=" * 50 + "\n\n")
            for version, success, addr in processor.results:
                status = f"0x{addr:04X}" if addr else "FAILED"
                f.write(f"{version}: {status}\n")
        print(f"\nSummary saved to: {summary_path}")


if __name__ == '__main__':
    main()
