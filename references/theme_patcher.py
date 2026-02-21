#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECHO MINI Theme Color Patcher

A tool to patch firmware with custom theme colors.
Reuses theme_analyzer_v3.py for code analysis.

Usage:
    python theme_patcher.py firmware.IMG --colors config.json --output patched.IMG
    python theme_patcher.py firmware.IMG --analyze
    python theme_patcher.py firmware.IMG --restore backup.IMG
"""

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# Import from theme_analyzer_v3
try:
    from theme_analyzer_v3 import (
        ThumbDecoder,
        MovwRecord,
        ThemeFunctionDetector,
        ThemeColorAnalyzer,
        ThemeDiscovery,
        PatchInfo,
        PatchDetector,
        _discover_flac_patch_point,
        _discover_menu_patch_point,
        _is_movw_instruction,
    )
    HAS_ANALYZER = True
except ImportError as e:
    HAS_ANALYZER = False
    print(f"Warning: theme_analyzer_v3.py import failed: {e}. Some features will be limited.")

# Version-specific hints (optional, used for faster detection)
# The patcher will auto-detect addresses if these are not provided
VERSION_HINTS = {
    # Example for future versions:
    # "V3.2.0": {"search_range": (0x80000, 0x90000)},
}
UNSUPPORTED_VERSIONS = []
PARTIAL_SUPPORT = {}


def discover_flac_function(data: bytes, search_start: int = 0x80000, search_end: int = 0x100000) -> Optional[Tuple[int, int]]:
    """
    Discover FLAC function address and patch point by searching for signature pattern.

    Uses the shared _discover_flac_patch_point from theme_analyzer_v3.

    Returns: (patch_point_addr, patch_point_addr) or None if not found
    """
    patch_point = _discover_flac_patch_point(data, search_start, search_end)
    if patch_point is not None:
        return patch_point, patch_point
    return None


def discover_menu_function(data: bytes, search_start: int = 0x30000, search_end: int = 0x50000) -> Optional[Tuple[int, int]]:
    """
    Discover Menu function address and patch point by searching for preload_store pattern.

    Uses the shared _discover_menu_patch_point from theme_analyzer_v3.

    Returns: (patch_point_addr, patch_point_addr) or None if not found
    """
    patch_point = _discover_menu_patch_point(data, search_start, search_end)
    if patch_point is not None:
        return patch_point, patch_point
    return None


def _find_function_start(data: bytes, addr: int, max_back: int = 200) -> Optional[int]:
    """Find function start by tracing back to PUSH instruction.

    If no PUSH is found (inline code block), returns the pattern address itself.
    """
    for back in range(addr, max(addr - max_back, 0), -2):
        hw = data[back] | (data[back + 1] << 8)
        # PUSH instruction: 16-bit (0xB4xx, 0xB5xx) or 32-bit (0xE92D)
        if (hw & 0xFE00) == 0xB400 or (hw & 0xFF00) == 0xB500:
            return back
        # 32-bit PUSH.W
        if hw == 0xE92D:
            return back
    # No PUSH found - this may be an inline code block
    # Return the pattern address as the "function start"
    return addr


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class NopSlide:
    """Represents a NOP slide region"""
    start: int
    end: int
    size: int
    source: str = "unknown"  # "known", "dynamic", "detected"
    is_active: bool = False  # True if used as NOP slide mechanism
    reference_count: int = 0


@dataclass
class PatchPoint:
    """Represents a patch point in a function"""
    func_addr: int
    patch_addr: int
    patch_size: int
    return_addr: int
    original_bytes: bytes
    description: str = ""


@dataclass
class ThemeFunction:
    """Represents a theme color function"""
    func_addr: int
    func_type: str  # "flac", "menu", etc.
    patch_point: Optional[PatchPoint] = None
    color_target: Optional[int] = None  # RAM address where color is stored
    current_colors: Dict[int, int] = field(default_factory=dict)  # theme_id -> color


@dataclass
class PatchMetadata:
    """Patch metadata stored in NOP region"""
    magic: bytes = b'ECHO'
    version: int = 1
    timestamp: int = 0
    flac_colors: List[int] = field(default_factory=list)
    menu_colors: List[int] = field(default_factory=list)
    checksum: int = 0

    def to_bytes(self) -> bytes:
        """Serialize to bytes"""
        data = self.magic
        data += struct.pack('<B', self.version)
        data += struct.pack('<I', self.timestamp)
        data += b''.join(struct.pack('<H', c) for c in self.flac_colors)
        data += b''.join(struct.pack('<H', c) for c in self.menu_colors)
        self.checksum = crc16(data)
        data += struct.pack('<H', self.checksum)
        return data

    @classmethod
    def from_bytes(cls, data: bytes) -> Optional['PatchMetadata']:
        """Deserialize from bytes"""
        if len(data) < 51:
            return None

        if data[0:4] != b'ECHO':
            return None

        metadata = cls()
        metadata.version = data[4]
        metadata.timestamp = struct.unpack('<I', data[5:9])[0]

        metadata.flac_colors = []
        for i in range(5):
            offset = 9 + i * 2
            metadata.flac_colors.append(struct.unpack('<H', data[offset:offset+2])[0])

        metadata.menu_colors = []
        for i in range(15):
            offset = 19 + i * 2
            metadata.menu_colors.append(struct.unpack('<H', data[offset:offset+2])[0])

        stored_checksum = struct.unpack('<H', data[49:51])[0]
        calculated_checksum = crc16(data[0:49])
        if stored_checksum != calculated_checksum:
            return None

        return metadata


# =============================================================================
# Exceptions
# =============================================================================

class PatchError(Exception):
    """Base patch error"""
    pass


class UnsupportedVersionError(PatchError):
    """Firmware version not supported"""
    pass


class AlreadyPatchedError(PatchError):
    """Firmware already patched"""
    pass


class CapacityError(PatchError):
    """Not enough space in NOP region"""
    pass


class SafetyError(PatchError):
    """Safety check failed"""
    pass


class CompatibilityError(PatchError):
    """Compatibility check failed"""
    pass


# =============================================================================
# Utility Functions
# =============================================================================

def crc16(data: bytes) -> int:
    """Calculate CRC16 checksum"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def read_file(path: str) -> bytes:
    """Read entire file"""
    with open(path, 'rb') as f:
        return f.read()


def write_file(path: str, data: bytes):
    """Write entire file"""
    with open(path, 'wb') as f:
        f.write(data)


def bytes_to_hex(data: bytes) -> str:
    """Convert bytes to hex string"""
    return ' '.join(f'{b:02X}' for b in data)


# =============================================================================
# NOP Slide Discovery
# =============================================================================

class NopSlideFinder:
    """Find and analyze NOP slide regions in firmware"""

    MIN_SLIDE_SIZE = 128  # Minimum size to consider

    def __init__(self, firmware_data: bytes):
        self.data = firmware_data
        self.slides: List[NopSlide] = []

    def find_all_slides(self) -> List[NopSlide]:
        """Find all NOP slide regions"""
        self.slides = []
        i = 0
        n = len(self.data)

        while i < n:
            if self.data[i] == 0x00:
                start = i
                while i < n and self.data[i] == 0x00:
                    i += 1
                size = i - start
                if size >= self.MIN_SLIDE_SIZE:
                    self.slides.append(NopSlide(
                        start=start,
                        end=i,
                        size=size,
                        source="dynamic"
                    ))
            else:
                i += 1

        return sorted(self.slides, key=lambda x: -x.size)

    def select_best_slide(self, theme_functions: List[int], required_size: int) -> Optional[NopSlide]:
        """Select the best NOP slide for patching"""
        candidates = []

        for slide in self.slides:
            if slide.size < required_size:
                continue

            # Check distance to theme functions
            distances = [abs(slide.start - f) for f in theme_functions]
            max_distance = max(distances) if distances else 0

            # Must be within BL range (16MB)
            if max_distance > 16777216:
                continue

            # Prefer smaller slides (don't waste large reserved areas)
            # and slides closer to functions
            candidates.append({
                'slide': slide,
                'utilization': required_size / slide.size,
                'max_distance': max_distance
            })

        if not candidates:
            return None

        # Sort by: closest to 100% utilization (not too big, not too small),
        # then by distance
        candidates.sort(key=lambda x: (abs(1 - x['utilization']), x['max_distance']))

        best = candidates[0]['slide']
        best.source = "selected"
        return best

    def verify_slide_unused(self, slide: NopSlide, code_refs: set) -> Tuple[bool, str]:
        """Verify NOP slide is not used by any code"""
        # Check if any code references fall within the slide
        for ref in code_refs:
            if slide.start <= ref < slide.end:
                return False, f"Reference at 0x{ref:X} points to slide"

        # Check if slide has any non-zero bytes (might be data, not NOP)
        # Already verified by find_all_slides

        return True, "Slide appears unused"


# =============================================================================
# Patch Detection
# =============================================================================

class PatchDetector:
    """Detect if firmware has been patched"""

    # Known patch signatures
    FLAC_ORIGINAL = bytes.fromhex('04290CBF')  # CMP R1,#4 + ITE EQ
    MENU_ORIGINAL = bytes.fromhex('4FF0000C')  # MOV.W R12, #0

    # BL instruction pattern (first halfword starts with 11110)
    BL_PATTERN_MASK = 0xF800
    BL_PATTERN_VALUE = 0xF000

    def __init__(self, firmware_data: bytes, version: str = "Unknown"):
        self.data = firmware_data
        self.version = version

    def is_bl_instruction(self, addr: int) -> bool:
        """Check if instruction at addr is a BL (32-bit Thumb branch with link)

        BL encoding: 11110 S imm10 | 11 J1 1 J2 imm11
        MOV.W encoding: 11110 i 10 0 100 imm4 | 0 imm3 Rd imm8

        Key difference: BL has bits [15:14] = 11 in second halfword
        """
        if addr + 4 > len(self.data):
            return False
        hw1 = self.data[addr] | (self.data[addr + 1] << 8)
        hw2 = self.data[addr + 2] | (self.data[addr + 3] << 8)

        # First halfword must start with 11110 (0xF000-0xF7FF)
        if (hw1 & 0xF800) != 0xF000:
            return False

        # Second halfword must have bits [15:14] = 11 for BL
        # BL: 11 J1 1 J2 imm11 = 0xD000-0xDFFF (bits 15:12 = 1101)
        # But actually bits 15:14 = 11, so 0xC000-0xFFFF
        # More precisely: bits 14:12 = 101 for BL (J1=1, bit 12=1, J2 varies)
        # BL second halfword: 11 J1 1 J2 imm11
        #   bits 15:14 = 11
        #   bit 12 = 1
        # So hw2 & 0xD000 should be 0xD000
        return (hw2 & 0xD000) == 0xD000

    def decode_bl_target(self, addr: int) -> int:
        """Decode BL instruction target address"""
        if addr + 4 > len(self.data):
            return 0
        hw1 = self.data[addr] | (self.data[addr + 1] << 8)
        hw2 = self.data[addr + 2] | (self.data[addr + 3] << 8)

        S = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        J1 = (hw2 >> 13) & 1
        J2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF

        I1 = ~(S ^ J1) & 1
        I2 = ~(S ^ J2) & 1

        imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1)
        if S:
            imm32 |= 0xFE000000  # Sign extend

        return (addr + 4 + imm32) & 0xFFFFFFFF

    def detect_flac_patch(self, flac_addr: int) -> Tuple[bool, str]:
        """Detect if FLAC function is patched

        Check the patch point address for BL instruction first.
        If BL found, it's patched. If original pattern found, not patched.
        """
        # First check if the address contains a BL instruction (patched)
        if self.is_bl_instruction(flac_addr):
            target = self.decode_bl_target(flac_addr)
            if 0x100000 < target < 0x2000000:  # Reasonable NOP slide range
                return True, f"Patched (BL at 0x{flac_addr:X} -> 0x{target:X})"

        # Check for original pattern
        if flac_addr + 4 <= len(self.data):
            current_bytes = self.data[flac_addr:flac_addr + 4]
            if current_bytes == self.FLAC_ORIGINAL:
                return False, "Original"

        # Scan nearby for pattern or BL
        for offset in range(0, 500, 2):
            patch_addr = flac_addr + offset
            if patch_addr + 4 > len(self.data):
                break

            current_bytes = self.data[patch_addr:patch_addr + 4]

            if current_bytes == self.FLAC_ORIGINAL:
                return False, "Original"
            elif self.is_bl_instruction(patch_addr):
                target = self.decode_bl_target(patch_addr)
                if 0x100000 < target < 0x2000000:
                    return True, f"Patched (BL at 0x{patch_addr:X})"

        return False, "CMP+ITE pattern not found"

    def detect_menu_patch(self, menu_addr: int) -> Tuple[bool, str]:
        """Detect if Menu function is patched

        Check the patch point address for BL instruction first.
        If BL found, it's patched. If original pattern found, not patched.
        """
        # First check if the address contains a BL instruction (patched)
        if self.is_bl_instruction(menu_addr):
            target = self.decode_bl_target(menu_addr)
            if 0x100000 < target < 0x2000000:  # Reasonable NOP slide range
                return True, f"Patched (BL at 0x{menu_addr:X} -> 0x{target:X})"

        # Check for original pattern
        if menu_addr + 4 <= len(self.data):
            current_bytes = self.data[menu_addr:menu_addr + 4]
            if current_bytes == self.MENU_ORIGINAL:
                return False, "Original"

        # Scan nearby for pattern or BL
        for offset in range(0, 200, 2):
            patch_addr = menu_addr + offset
            if patch_addr + 4 > len(self.data):
                break

            current_bytes = self.data[patch_addr:patch_addr + 4]

            if current_bytes == self.MENU_ORIGINAL:
                return False, "Original"
            elif self.is_bl_instruction(patch_addr):
                target = self.decode_bl_target(patch_addr)
                if 0x100000 < target < 0x2000000:
                    return True, f"Patched (BL at 0x{patch_addr:X})"

        return False, "MOVW R12 pattern not found"

    def read_patch_metadata(self, nop_slide: NopSlide) -> Optional[PatchMetadata]:
        """Read patch metadata from NOP region"""
        metadata_start = nop_slide.end - 51
        if metadata_start < 0:
            return None

        metadata_bytes = self.data[metadata_start:metadata_start + 51]
        return PatchMetadata.from_bytes(metadata_bytes)


# =============================================================================
# BL Instruction Encoding
# =============================================================================

def encode_bl(from_addr: int, to_addr: int) -> bytes:
    """
    Encode a 32-bit BL instruction for ARM Thumb

    Format:
    hw1: 11110 S imm10
    hw2: 11 J1 1 J2 imm11

    imm32 = SignExtend(S:I1:I2:imm10:imm11:1)
    I1 = NOT(J1 XOR S)
    I2 = NOT(J2 XOR S)

    Range: ±16MB (±16777216 bytes)
    """
    offset = to_addr - (from_addr + 4)

    # BL range is ±16MB
    if offset > 16777214 or offset < -16777216:
        raise PatchError(f"BL offset out of range: {offset}")

    # Get 25-bit signed value (offset >> 1 because Thumb is 16-bit aligned)
    # imm25 is the 25-bit representation of offset >> 1
    imm25 = (offset >> 1) & 0x1FFFFFF

    # Sign bit
    S = 1 if offset < 0 else 0

    # Extract components from 25-bit value
    I1 = (imm25 >> 23) & 1
    I2 = (imm25 >> 22) & 1
    imm10 = (imm25 >> 12) & 0x3FF
    imm11 = imm25 & 0xFFF

    # J1 = NOT(S XOR I1), J2 = NOT(S XOR I2)
    J1 = (~(S ^ I1)) & 1
    J2 = (~(S ^ I2)) & 1

    # Encode
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = 0xD000 | (J1 << 13) | (1 << 12) | (J2 << 11) | imm11

    # Return as little-endian bytes
    return bytes([hw1 & 0xFF, (hw1 >> 8) & 0xFF, hw2 & 0xFF, (hw2 >> 8) & 0xFF])


def encode_b_16bit(from_addr: int, to_addr: int) -> bytes:
    """
    Encode a 16-bit B instruction for ARM Thumb

    Format: 11100 imm11
    Range: +/- 2048 bytes (imm11 encodes offset >> 1)
    """
    offset = to_addr - (from_addr + 4)

    # B range is ±2048 bytes (±1024 halfwords)
    if offset > 2046 or offset < -2048:
        raise PatchError(f"B offset out of range: {offset}")

    imm11 = (offset >> 1) & 0x7FF

    opcode = 0xE000 | imm11
    return bytes([opcode & 0xFF, (opcode >> 8) & 0xFF])


def encode_movw(reg: int, imm16: int) -> bytes:
    """
    Encode MOVW instruction for ARM Thumb

    Format: 11110 i 100100 imm4 0 imm3 Rd imm8
    imm16 = (i << 11) | (imm4 << 12) | (imm3 << 8) | imm8
    """
    i = (imm16 >> 11) & 1
    imm4 = (imm16 >> 12) & 0xF
    imm3 = (imm16 >> 8) & 0x7
    imm8 = imm16 & 0xFF

    hw1 = 0xF240 | (i << 10) | imm4
    hw2 = (imm3 << 12) | (reg << 8) | imm8

    return bytes([hw1 & 0xFF, (hw1 >> 8) & 0xFF, hw2 & 0xFF, (hw2 >> 8) & 0xFF])


def encode_push(regs: List[int]) -> bytes:
    """Encode PUSH instruction"""
    # PUSH {r0-r7, lr} format: 1011 0100 <register_list>
    reg_list = 0
    for r in regs:
        if r == 14:  # LR
            reg_list |= 0x100
        elif 0 <= r <= 7:
            reg_list |= (1 << r)

    opcode = 0xB400 | (reg_list >> 8)
    return bytes([opcode & 0xFF, (opcode >> 8) & 0xFF, reg_list & 0xFF])


# =============================================================================
# Theme Patcher
# =============================================================================

class ThemePatcher:
    """Main theme patcher class"""

    REQUIRED_SPACE = 250  # Estimated space needed for patches

    def __init__(self, firmware_path: str):
        self.firmware_path = firmware_path
        self.data = bytearray(read_file(firmware_path))
        self.version = "Unknown"
        self.support_level = "none"
        self.theme_functions: List[ThemeFunction] = []
        self.nop_slide: Optional[NopSlide] = None
        self.patch_metadata: Optional[PatchMetadata] = None
        self.is_patched = False

    def analyze(self) -> Dict[str, Any]:
        """Analyze firmware for patching"""
        result = {
            'version': self.version,
            'support_level': self.support_level,
            'theme_functions': [],
            'nop_slides': [],
            'is_patched': False,
            'patch_status': {},
            'can_patch': False,
            'errors': []
        }

        # Detect version
        self.version = self._detect_version()
        result['version'] = self.version

        # Find theme functions (must be done before _check_support)
        self.theme_functions = self._find_theme_functions()
        result['theme_functions'] = [
            {'addr': f.func_addr, 'type': f.func_type}
            for f in self.theme_functions
        ]

        # Check support level (now depends on discovered functions)
        self.support_level = self._check_support()
        result['support_level'] = self.support_level

        if self.support_level == 'none':
            result['errors'].append(f"Version {self.version} does not support theme system")
            return result

        if not self.theme_functions:
            result['errors'].append("No theme functions found")
            return result

        # Detect existing patches
        # Check if firmware has been patched by counting signature patterns
        detector = PatchDetector(bytes(self.data), self.version)
        is_patched = self._check_firmware_patched()
        if is_patched:
            result['patch_status']['general'] = {
                'patched': True,
                'status': "Signature patterns indicate patched firmware"
            }
            self.is_patched = True
        else:
            # Fall back to pattern-based detection
            for tf in self.theme_functions:
                if tf.func_type == 'flac':
                    is_patched, status = detector.detect_flac_patch(tf.func_addr)
                    result['patch_status']['flac'] = {'patched': is_patched, 'status': status}
                elif tf.func_type == 'menu':
                    is_patched, status = detector.detect_menu_patch(tf.func_addr)
                    result['patch_status']['menu'] = {'patched': is_patched, 'status': status}

            self.is_patched = any(
                ps.get('patched', False)
                for ps in result['patch_status'].values()
            )
        result['is_patched'] = self.is_patched

        # Find NOP slides
        finder = NopSlideFinder(bytes(self.data))
        slides = finder.find_all_slides()
        result['nop_slides'] = [
            {'start': s.start, 'end': s.end, 'size': s.size}
            for s in slides[:5]  # Top 5
        ]

        # Select best slide
        func_addrs = [f.func_addr for f in self.theme_functions]
        self.nop_slide = finder.select_best_slide(func_addrs, self.REQUIRED_SPACE)

        if self.nop_slide:
            result['selected_nop_slide'] = {
                'start': self.nop_slide.start,
                'end': self.nop_slide.end,
                'size': self.nop_slide.size
            }

            # Check for existing metadata
            self.patch_metadata = detector.read_patch_metadata(self.nop_slide)
            if self.patch_metadata:
                result['existing_metadata'] = {
                    'timestamp': self.patch_metadata.timestamp,
                    'flac_colors': self.patch_metadata.flac_colors,
                    'menu_colors': self.patch_metadata.menu_colors
                }

            result['can_patch'] = True
        else:
            result['errors'].append(f"No suitable NOP slide found (need {self.REQUIRED_SPACE} bytes)")

        return result

    def patch(self, flac_colors: List[int], menu_colors: List[int],
              output_path: str, force: bool = False) -> Dict[str, Any]:
        """Apply theme color patch"""
        # Run analysis first
        analysis = self.analyze()

        if not analysis['can_patch'] and not force:
            raise CompatibilityError(f"Cannot patch: {analysis['errors']}")

        if self.is_patched and not force:
            raise AlreadyPatchedError(
                "Firmware is already patched. Use --force to override or --update-colors to change colors."
            )

        if not self.nop_slide:
            raise CapacityError("No suitable NOP slide found")

        # Validate colors
        if len(flac_colors) != 5:
            raise PatchError("Need exactly 5 FLAC colors (one per theme)")
        if len(menu_colors) != 15:
            raise PatchError("Need exactly 15 Menu colors (3 per theme × 5 themes)")

        # Create backup
        backup_path = output_path + '.backup'
        if os.path.exists(output_path):
            shutil.copy(output_path, backup_path)

        try:
            # Generate and apply patch
            patch_result = self._apply_patch(flac_colors, menu_colors)

            # Store metadata
            metadata = PatchMetadata(
                timestamp=int(time.time()),
                flac_colors=flac_colors,
                menu_colors=menu_colors
            )
            metadata_addr = self.nop_slide.end - 51
            self.data[metadata_addr:metadata_addr + 51] = metadata.to_bytes()

            # Write output
            write_file(output_path, bytes(self.data))

            return {
                'success': True,
                'output_path': output_path,
                'backup_path': backup_path if os.path.exists(backup_path) else None,
                'nop_slide': {
                    'start': self.nop_slide.start,
                    'end': self.nop_slide.end,
                    'size': self.nop_slide.size
                },
                'patch_points': patch_result['patch_points'],
                'metadata_addr': metadata_addr
            }

        except Exception as e:
            # Restore backup if exists
            if os.path.exists(backup_path):
                shutil.copy(backup_path, output_path)
            raise PatchError(f"Patch failed: {e}")

    def _apply_patch(self, flac_colors: List[int], menu_colors: List[int]) -> Dict[str, Any]:
        """Apply the actual patch"""
        patch_points = {}

        # For each theme function, replace with BL to NOP region
        nop_start = self.nop_slide.start

        for tf in self.theme_functions:
            if tf.func_type == 'flac' and tf.patch_point:
                patch_addr = tf.patch_point.patch_addr
                return_addr = tf.patch_point.return_addr

                # Store original bytes
                original = bytes(self.data[patch_addr:patch_addr + 4])

                # Encode BL to NOP region (FLAC code starts at nop_start + some offset)
                flac_code_addr = nop_start + 32  # Leave room for protection B
                bl_bytes = encode_bl(patch_addr, flac_code_addr)

                # Apply patch
                self.data[patch_addr:patch_addr + 4] = bl_bytes

                patch_points['flac'] = {
                    'patch_addr': patch_addr,
                    'return_addr': return_addr,
                    'original_bytes': original.hex(),
                    'new_bytes': bl_bytes.hex()
                }

            elif tf.func_type == 'menu' and tf.patch_point:
                patch_addr = tf.patch_point.patch_addr
                return_addr = tf.patch_point.return_addr

                original = bytes(self.data[patch_addr:patch_addr + 4])

                # Menu code starts after FLAC code
                menu_code_addr = nop_start + 128
                bl_bytes = encode_bl(patch_addr, menu_code_addr)

                self.data[patch_addr:patch_addr + 4] = bl_bytes

                patch_points['menu'] = {
                    'patch_addr': patch_addr,
                    'return_addr': return_addr,
                    'original_bytes': original.hex(),
                    'new_bytes': bl_bytes.hex()
                }

        # Generate code in NOP region
        self._generate_nop_code(flac_colors, menu_colors)

        return {'patch_points': patch_points}

    def _generate_nop_code(self, flac_colors: List[int], menu_colors: List[int]):
        """Generate patch code in NOP region"""
        nop_start = self.nop_slide.start

        # Protection B at start (skip to FLAC code)
        flac_code_addr = nop_start + 32
        protection_b = encode_b_16bit(nop_start, flac_code_addr)
        self.data[nop_start:nop_start + 2] = protection_b

        # Keep NOPs for slide protection
        # ... (remaining implementation would generate the actual ARM code)

        # For now, this is a simplified version
        # Full implementation would generate:
        # - FLAC color selection code
        # - Menu color selection code
        # - Color tables

    def _detect_version(self) -> str:
        """Detect firmware version using automatic pattern discovery"""
        # Method 1: Try to find version string in firmware
        version_patterns = [
            b'V3.1.0', b'V3.0.0', b'V2.9.0', b'V2.8.0',
            b'V2.7.0', b'V2.6.0', b'V2.5.0', b'V2.4.0',
        ]

        for pattern in version_patterns:
            if pattern in self.data:
                return pattern.decode('ascii')

        # Method 2: Use file characteristics and pattern discovery
        file_size = len(self.data)

        # Check if firmware has theme system by discovering functions
        if file_size > 30000000:  # Likely a full firmware image
            # Try to discover FLAC function
            flac_result = discover_flac_function(bytes(self.data))
            menu_result = discover_menu_function(bytes(self.data))

            if flac_result and menu_result:
                # Found both functions, this firmware supports themes
                # Estimate version based on file size
                if 33000000 < file_size < 34000000:
                    return "V3.1.0 (detected)"
                else:
                    return "Unknown (theme-capable)"

        # Method 3: Check hash (for known firmware versions)
        firmware_hash = hashlib.md5(self.data).hexdigest()[:8]
        known_hashes = {}  # Populated with known firmware hashes
        if firmware_hash in known_hashes:
            return known_hashes[firmware_hash]

        return "Unknown"

    def _check_support(self) -> str:
        """Check if firmware supports theme system based on discovered functions"""
        # If we found theme functions, we have full support
        if self.theme_functions:
            has_flac = any(f.func_type == 'flac' for f in self.theme_functions)
            has_menu = any(f.func_type == 'menu' for f in self.theme_functions)
            if has_flac and has_menu:
                return 'full'
            elif has_flac or has_menu:
                return 'partial'
        return 'none'

    def _find_theme_functions(self) -> List[ThemeFunction]:
        """Find theme color functions using automatic pattern discovery

        For unpatched firmware: discovers original patterns.
        For patched firmware: patterns are replaced with BL, so discovery returns None.
        """
        functions = []

        # Get search range hints if available
        hints = VERSION_HINTS.get(self.version, {})
        search_start = hints.get('search_start', 0x30000)
        search_end = hints.get('search_end', 0x150000)

        # FLAC function discovery
        flac_result = discover_flac_function(bytes(self.data), search_start, search_end)
        if flac_result:
            func_addr, patch_addr = flac_result
            tf = ThemeFunction(func_addr=func_addr, func_type='flac')
            tf.patch_point = PatchPoint(
                func_addr=func_addr,
                patch_addr=patch_addr,
                patch_size=4,
                return_addr=patch_addr + 4,
                original_bytes=bytes(self.data[patch_addr:patch_addr+4]),
                description="FLAC CMP+ITE pattern"
            )
            functions.append(tf)

        # Menu function discovery
        menu_result = discover_menu_function(bytes(self.data), search_start, search_end)
        if menu_result:
            func_addr, patch_addr = menu_result
            tf = ThemeFunction(func_addr=func_addr, func_type='menu')
            tf.patch_point = PatchPoint(
                func_addr=func_addr,
                patch_addr=patch_addr,
                patch_size=4,
                return_addr=patch_addr + 12,  # Skip 3 MOVW instructions
                original_bytes=bytes(self.data[patch_addr:patch_addr+4]),
                description="Menu MOV.W R12 pattern"
            )
            functions.append(tf)

        return functions

        return functions

    def _check_firmware_patched(self) -> bool:
        """Check if firmware has been patched by counting signature patterns

        Original firmware has:
        - 2 CMP+ITE patterns (FLAC related)
        - Multiple MOV.W R12,#0 + MOVW patterns (Menu related)

        Patched firmware will have fewer patterns because some were replaced with BL.
        """
        # Count CMP+ITE patterns (FLAC signature)
        cmp_ite_count = 0
        for addr in range(0x80000, min(0x150000, len(self.data)), 2):
            if self.data[addr:addr+2] == bytes.fromhex('0429'):  # CMP R1,#4
                if self.data[addr+2:addr+4] == bytes.fromhex('0CBF'):  # ITE EQ
                    cmp_ite_count += 1
        
        # Count MOV.W R12,#0 + MOVW patterns (Menu signature)
        menu_pattern_count = 0
        for addr in range(0x30000, min(0x60000, len(self.data)), 2):
            if self.data[addr:addr+4] == bytes.fromhex('4FF0000C'):  # MOV.W R12, #0
                # Check for MOVW after
                for check_offset in (4, 6, 8, 10, 12):
                    check_addr = addr + check_offset
                    if check_addr + 4 <= len(self.data):
                        hw = self.data[check_addr] | (self.data[check_addr+1] << 8)
                        if (hw & 0xFB00) == 0xF200:  # MOVW
                            menu_pattern_count += 1
                            break
        
        # Original firmware should have:
        # - At least 2 CMP+ITE patterns (FLAC)
        # - At least 1 Menu pattern
        # 
        # Patched firmware will have fewer patterns
        if cmp_ite_count < 2:
            return True  # Likely patched (FLAC pattern missing)
        
        if menu_pattern_count < 1:
            return True  # Likely patched (Menu pattern missing)
        
        return False

    def _find_function_start(self, addr: int, max_back: int = 200) -> int:
        """Find function start by tracing back to PUSH instruction"""
        result = _find_function_start(bytes(self.data), addr, max_back)
        return result if result else addr


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='ECHO MINI Theme Color Patcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze firmware:
    python theme_patcher.py firmware.IMG --analyze

  Apply patch with colors from JSON:
    python theme_patcher.py firmware.IMG --colors colors.json --output patched.IMG

  Restore from backup:
    python theme_patcher.py firmware.IMG --restore firmware.IMG.backup
        """
    )

    parser.add_argument('firmware', help='Firmware file to patch')
    parser.add_argument('--analyze', action='store_true',
                        help='Analyze firmware without patching')
    parser.add_argument('--colors', type=str,
                        help='JSON file with color configuration')
    parser.add_argument('--output', '-o', type=str,
                        help='Output file path')
    parser.add_argument('--force', '-f', action='store_true',
                        help='Force patch even if already patched')
    parser.add_argument('--restore', type=str,
                        help='Restore from backup file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Restore mode
    if args.restore:
        if not os.path.exists(args.restore):
            print(f"Error: Backup file not found: {args.restore}")
            sys.exit(1)
        shutil.copy(args.restore, args.firmware)
        print(f"Restored {args.firmware} from {args.restore}")
        sys.exit(0)

    # Create patcher
    patcher = ThemePatcher(args.firmware)

    # Analyze mode
    if args.analyze:
        result = patcher.analyze()
        print("\n=== Firmware Analysis ===")
        print(f"Version: {result['version']}")
        print(f"Support level: {result['support_level']}")
        print(f"Is patched: {result['is_patched']}")

        if result['theme_functions']:
            print(f"\nTheme functions found: {len(result['theme_functions'])}")
            for tf in result['theme_functions']:
                print(f"  0x{tf['addr']:05X} ({tf['type']})")

        if result['patch_status']:
            print(f"\nPatch status:")
            for name, status in result['patch_status'].items():
                print(f"  {name}: {status['status']}")

        if result['nop_slides']:
            print(f"\nNOP slides found: {len(result['nop_slides'])}")
            for slide in result['nop_slides']:
                print(f"  0x{slide['start']:05X} - 0x{slide['end']:05X} ({slide['size']} bytes)")

        if 'selected_nop_slide' in result:
            slide = result['selected_nop_slide']
            print(f"\nSelected NOP slide: 0x{slide['start']:05X} ({slide['size']} bytes)")

        if result['errors']:
            print(f"\nErrors: {result['errors']}")

        print(f"\nCan patch: {result['can_patch']}")
        sys.exit(0)

    # Patch mode
    if not args.colors:
        print("Error: --colors required for patching")
        parser.print_help()
        sys.exit(1)

    if not args.output:
        args.output = args.firmware + '.patched'

    # Load colors
    with open(args.colors, 'r') as f:
        colors_config = json.load(f)

    flac_colors = colors_config.get('flac', [])
    menu_colors = colors_config.get('menu', [])

    # Apply patch
    try:
        result = patcher.patch(flac_colors, menu_colors, args.output, force=args.force)
        print("\n=== Patch Applied Successfully ===")
        print(f"Output: {result['output_path']}")
        print(f"NOP slide: 0x{result['nop_slide']['start']:05X}")
        for name, pp in result['patch_points'].items():
            print(f"  {name}: 0x{pp['patch_addr']:05X}")
        if result.get('backup_path'):
            print(f"Backup: {result['backup_path']}")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
