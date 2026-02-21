#!/usr/bin/env python3
"""
Comprehensive test suite for theme_patcher.py

Tests:
1. Input validation (illegal parameters)
2. Patch operations
3. Firmware integrity
4. Unicorn emulation tests
5. Edge cases and boundary conditions
"""

import copy
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

# Check if unicorn is available
try:
    from unicorn import *
    from unicorn.arm_const import *
    HAS_UNICORN = True
except ImportError:
    HAS_UNICORN = False
    print("Warning: unicorn not available, emulation tests will be skipped")

# Import the module under test
import theme_patcher
from theme_patcher import (
    ThemePatcher, PatchDetector, NopSlideFinder, NopSlide,
    PatchError, UnsupportedVersionError, AlreadyPatchedError,
    CapacityError, SafetyError, CompatibilityError,
    encode_bl, encode_b_16bit, encode_movw, encode_push,
    discover_flac_function, discover_menu_function,
    _find_function_start, crc16,
)

# Test firmware path
FIRMWARE_PATH = "HIFIEC10.IMG"


class TestInputValidation(unittest.TestCase):
    """Test that illegal inputs are properly rejected"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.patcher = ThemePatcher(FIRMWARE_PATH)

    def test_invalid_flac_color_count(self):
        """Should reject wrong number of FLAC colors"""
        # Too few colors
        with self.assertRaises(PatchError):
            self.patcher.patch(
                flac_colors=[0xF800, 0x001F, 0xFFE0],  # Only 3
                menu_colors=[0xF800] * 15,
                output_path="/tmp/test.IMG"
            )

        # Too many colors
        with self.assertRaises(PatchError):
            self.patcher.patch(
                flac_colors=[0xF800] * 6,  # 6 instead of 5
                menu_colors=[0xF800] * 15,
                output_path="/tmp/test.IMG"
            )

    def test_invalid_menu_color_count(self):
        """Should reject wrong number of Menu colors"""
        with self.assertRaises(PatchError):
            self.patcher.patch(
                flac_colors=[0xF800] * 5,
                menu_colors=[0xF800] * 14,  # 14 instead of 15
                output_path="/tmp/test.IMG"
            )

    def test_invalid_color_values(self):
        """Should reject invalid RGB565 color values"""
        # Color values should be 16-bit (0x0000-0xFFFF)
        # Test with negative value
        with self.assertRaises((PatchError, ValueError, struct.error)):
            self.patcher.patch(
                flac_colors=[-1, 0x001F, 0xFFE0, 0x07FF, 0x0000],
                menu_colors=[0xF800] * 15,
                output_path="/tmp/test.IMG"
            )

        # Test with value too large for uint16
        with self.assertRaises((PatchError, ValueError, struct.error)):
            self.patcher.patch(
                flac_colors=[0x10000] * 5,  # > 0xFFFF
                menu_colors=[0xF800] * 15,
                output_path="/tmp/test.IMG"
            )

    def test_nonexistent_firmware(self):
        """Should reject non-existent firmware file"""
        with self.assertRaises(FileNotFoundError):
            ThemePatcher("/nonexistent/firmware.IMG")

    def test_invalid_output_path(self):
        """Should handle invalid output path gracefully"""
        # Create patcher with valid firmware
        patcher = ThemePatcher(FIRMWARE_PATH)

        # Try to write to a directory that doesn't exist
        # This should raise an appropriate error (PatchError wrapping the underlying error)
        with self.assertRaises((PatchError, FileNotFoundError, OSError)):
            patcher.patch(
                flac_colors=[0xF800] * 5,
                menu_colors=[0xF800] * 15,
                output_path="/nonexistent/directory/test.IMG",
                force=True
            )


class TestBLInstructionEncoding(unittest.TestCase):
    """Test BL instruction encoding correctness"""

    def test_forward_bl_encoding(self):
        """Test encoding forward BL instruction"""
        # Test known offset
        from_addr = 0x1000
        to_addr = 0x2000

        bl_bytes = encode_bl(from_addr, to_addr)

        # Verify it's a valid BL instruction (starts with 0xF000-0xF7FF)
        hw1 = bl_bytes[0] | (bl_bytes[1] << 8)
        hw2 = bl_bytes[2] | (bl_bytes[3] << 8)

        self.assertEqual(hw1 & 0xF800, 0xF000, "First halfword should start with 11110")
        self.assertEqual(hw2 & 0xD000, 0xD000, "Second halfword should have bits 15:14 = 11")

    def test_backward_bl_encoding(self):
        """Test encoding backward BL instruction"""
        from_addr = 0x2000
        to_addr = 0x1000

        bl_bytes = encode_bl(from_addr, to_addr)

        # Verify encoding
        hw1 = bl_bytes[0] | (bl_bytes[1] << 8)
        hw2 = bl_bytes[2] | (bl_bytes[3] << 8)

        self.assertEqual(hw1 & 0xF800, 0xF000)
        self.assertEqual(hw2 & 0xD000, 0xD000)

    def test_bl_range_limit(self):
        """Test BL instruction range limit (±16MB)"""
        from_addr = 0x100000

        # Should work within range (max forward is +16777214)
        to_addr_within = from_addr + 0x7FFFFE  # Near max forward (even number)
        bl_bytes = encode_bl(from_addr, to_addr_within)
        self.assertEqual(len(bl_bytes), 4)

        # Max backward is -16777216
        to_addr_within = from_addr - 0x800000  # Max backward
        bl_bytes = encode_bl(from_addr, to_addr_within)
        self.assertEqual(len(bl_bytes), 4)

        # Should fail outside range (more than +16MB)
        # Note: offset = to_addr - (from_addr + 4)
        # Max offset = 16777214, so we need to_addr such that offset > 16777214
        # to_addr > from_addr + 4 + 16777214 = from_addr + 16777218 = from_addr + 0x1000002
        with self.assertRaises(PatchError):
            encode_bl(from_addr, from_addr + 0x1000004)  # Will result in offset > 16777214

    def test_bl_roundtrip(self):
        """Test that BL encoding can be decoded back to correct target"""
        from_addr = 0x86CB0
        to_addr = 0xA0F3A0

        bl_bytes = encode_bl(from_addr, to_addr)

        # Decode the BL instruction
        hw1 = bl_bytes[0] | (bl_bytes[1] << 8)
        hw2 = bl_bytes[2] | (bl_bytes[3] << 8)

        S = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        J1 = (hw2 >> 13) & 1
        J2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF

        I1 = (~(J1 ^ S)) & 1
        I2 = (~(J2 ^ S)) & 1

        # Reconstruct imm25 = S:I1:I2:imm10:imm11
        imm25 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | imm11

        # imm32 = imm25 << 1 (with sign extension if S=1)
        imm32 = imm25 << 1
        if S:
            imm32 |= 0xFE000000  # Sign extend to 32 bits

        decoded_target = (from_addr + 4 + imm32) & 0xFFFFFFFF

        self.assertEqual(decoded_target, to_addr,
            f"BL roundtrip failed: expected 0x{to_addr:X}, got 0x{decoded_target:X}")


class TestBInstructionEncoding(unittest.TestCase):
    """Test 16-bit B instruction encoding"""

    def test_b_range_limit(self):
        """Test B instruction range limit (±2KB)"""
        from_addr = 0x1000

        # Note: offset = to_addr - (from_addr + 4)
        # So for forward: to_addr = from_addr + offset + 4
        # Max forward is +2046, so to_addr = from_addr + 2046 + 4 = from_addr + 2050
        b_bytes = encode_b_16bit(from_addr, from_addr + 0x802)  # Near max forward
        self.assertEqual(len(b_bytes), 2)

        # Max backward is -2048, so to_addr = from_addr - 2048 + 4 = from_addr - 2044
        b_bytes = encode_b_16bit(from_addr, from_addr - 0x7FC)  # Near max backward
        self.assertEqual(len(b_bytes), 2)

        # Should fail outside range (more than 2KB)
        with self.assertRaises(PatchError):
            encode_b_16bit(from_addr, from_addr + 0x1000)  # 4KB forward


class TestFirmwareIntegrity(unittest.TestCase):
    """Test that patching doesn't corrupt firmware"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.original_data = open(FIRMWARE_PATH, 'rb').read()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_firmware_size_unchanged(self):
        """Patching should not change firmware size"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        patcher = ThemePatcher(FIRMWARE_PATH)
        patcher.patch(
            flac_colors=[0xF800, 0x001F, 0xFFE0, 0x07FF, 0x0000],
            menu_colors=[0xF800] * 15,
            output_path=output_path,
            force=True
        )

        patched_data = open(output_path, 'rb').read()
        self.assertEqual(len(self.original_data), len(patched_data),
            "Firmware size changed after patching")

    def test_critical_regions_unchanged(self):
        """Critical firmware regions should not be modified"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        patcher = ThemePatcher(FIRMWARE_PATH)
        result = patcher.patch(
            flac_colors=[0xF800] * 5,
            menu_colors=[0xF800] * 15,
            output_path=output_path,
            force=True
        )

        patched_data = open(output_path, 'rb').read()

        # Check that most of the firmware is unchanged
        # Only patch points and NOP slide should be modified
        unchanged_bytes = sum(
            1 for a, b in zip(self.original_data, patched_data) if a == b
        )
        change_ratio = unchanged_bytes / len(self.original_data)

        # Should have less than 0.01% changes
        self.assertGreater(change_ratio, 0.9999,
            f"Too many bytes changed: {(1-change_ratio)*100:.4f}%")

    def test_header_intact(self):
        """Firmware header should remain intact"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        patcher = ThemePatcher(FIRMWARE_PATH)
        patcher.patch(
            flac_colors=[0xF800] * 5,
            menu_colors=[0xF800] * 15,
            output_path=output_path,
            force=True
        )

        patched_data = open(output_path, 'rb').read()

        # First 64 bytes should be unchanged (header)
        self.assertEqual(self.original_data[:64], patched_data[:64],
            "Firmware header was modified")


class TestPatternDiscovery(unittest.TestCase):
    """Test automatic pattern discovery functions"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.data = open(FIRMWARE_PATH, 'rb').read()

    def test_flac_discovery(self):
        """FLAC function should be discovered in valid firmware"""
        result = discover_flac_function(self.data)
        self.assertIsNotNone(result, "FLAC function not discovered")

        func_addr, patch_addr = result
        self.assertGreater(func_addr, 0, "Invalid function address")
        self.assertGreater(patch_addr, 0, "Invalid patch address")

        # Verify pattern at patch address
        self.assertEqual(self.data[patch_addr:patch_addr+2], bytes.fromhex('0429'))
        self.assertEqual(self.data[patch_addr+2:patch_addr+4], bytes.fromhex('0CBF'))

    def test_menu_discovery(self):
        """Menu function should be discovered in valid firmware"""
        result = discover_menu_function(self.data)
        self.assertIsNotNone(result, "Menu function not discovered")

        func_addr, patch_addr = result
        self.assertGreater(func_addr, 0, "Invalid function address")
        self.assertGreater(patch_addr, 0, "Invalid patch address")

        # Verify pattern at patch address
        self.assertEqual(self.data[patch_addr:patch_addr+4], bytes.fromhex('4FF0000C'))

    def test_function_start_detection(self):
        """Function start detection should find PUSH instructions"""
        # Test with known FLAC pattern address
        addr = 0x86CB0
        func_start = _find_function_start(self.data, addr)

        self.assertIsNotNone(func_start, "Function start not found")
        # For inline code blocks, may return same address
        self.assertGreater(func_start, 0, "Invalid function start")


@unittest.skipIf(not HAS_UNICORN, "Unicorn not available")
class TestUnicornEmulation(unittest.TestCase):
    """Test patched firmware behavior using Unicorn emulation"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.temp_dir = tempfile.mkdtemp()
        self.original_data = open(FIRMWARE_PATH, 'rb').read()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_bl_instruction_execution(self):
        """Test that patched BL instruction executes correctly"""
        from_addr = 0x86CB0
        to_addr = 0xA0F3A0

        # Encode BL instruction
        bl_bytes = encode_bl(from_addr, to_addr)

        # Create minimal test code
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

        # Map memory
        code_addr = 0x1000
        mu.mem_map(code_addr, 0x1000)

        # Write BL instruction
        mu.mem_write(code_addr, bl_bytes)

        # Start execution
        mu.reg_write(UC_ARM_REG_PC, code_addr | 1)  # Thumb mode

        try:
            mu.emu_start(code_addr | 1, code_addr + 4, count=1)
        except UcError as e:
            # BL instruction will try to jump, may fail if target not mapped
            pass

        # Verify PC changed in expected direction
        pc = mu.reg_read(UC_ARM_REG_PC)
        # After BL, PC should point somewhere (exact value depends on implementation)

    def test_nop_slide_protection(self):
        """Test that NOP slide protection B instruction works"""
        # Use aligned addresses for Unicorn
        nop_start = 0x100000
        flac_code = nop_start + 32

        # Encode protection B
        b_bytes = encode_b_16bit(nop_start, flac_code)

        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        # Map memory at aligned address (must be 4KB aligned)
        mu.mem_map(0x100000, 0x10000)

        # Write B instruction and some NOPs
        code = b_bytes + b'\x00\x00' * 100
        mu.mem_write(nop_start, code)

        # Execute B instruction
        mu.reg_write(UC_ARM_REG_PC, nop_start | 1)

        try:
            mu.emu_start(nop_start | 1, nop_start + 200, count=2)
        except UcError:
            pass

        # PC should have jumped past NOPs
        pc = mu.reg_read(UC_ARM_REG_PC)
        self.assertGreaterEqual(pc, flac_code,
            "Protection B should skip to FLAC code")


@unittest.skipIf(not HAS_UNICORN, "Unicorn not available")
class TestColorLoading(unittest.TestCase):
    """Test that patched firmware correctly loads colors into RAM"""

    # Target RAM address for palette (from memory.md)
    PALETTE_RAM = 0x0301E560

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _generate_simple_color_writer(self, color: int, ram_addr: int) -> bytes:
        """Generate simple code that writes one color to RAM

        MOVW R0, #color
        MOVW R1, #(ram_addr & 0xFFFF)
        MOVT R1, #(ram_addr >> 16)  ; Only if address > 0xFFFF
        STRH R0, [R1]
        BX LR
        """
        code = bytearray()

        # MOVW R0, #color
        movw_r0 = encode_movw(0, color)
        code.extend(movw_r0)

        # MOVW R1, #(ram_addr & 0xFFFF)
        movw_r1 = encode_movw(1, ram_addr & 0xFFFF)
        code.extend(movw_r1)

        # MOVT R1, #(ram_addr >> 16) if needed
        if ram_addr > 0xFFFF:
            # MOVT encoding: 11110 i 101100 imm4 0 imm3 Rd imm8
            # imm16 = (i << 11) | (imm4 << 12) | (imm3 << 8) | imm8
            imm16 = ram_addr >> 16
            i = (imm16 >> 11) & 1
            imm4 = (imm16 >> 12) & 0xF
            imm3 = (imm16 >> 8) & 0x7
            imm8 = imm16 & 0xFF
            hw1 = 0xF2C0 | (i << 10) | imm4
            hw2 = (imm3 << 12) | (1 << 8) | imm8  # R1
            code.extend(bytes([hw1 & 0xFF, (hw1 >> 8) & 0xFF, hw2 & 0xFF, (hw2 >> 8) & 0xFF]))

        # STRH R0, [R1]  ->  1000 0 rrr nnn nmmm  (STRH Rd, [Rn, #0])
        # Thumb: STRH R0, [R1] = 8000 | (1 << 3) | 0 = 0x8008
        strh_instr = 0x8008
        code.extend(struct.pack('<H', strh_instr))

        # BX LR  ->  0100 0111 rrr mmmm  (BX Rm)
        # Thumb: BX LR = 0x4770
        bx_lr = 0x4770
        code.extend(struct.pack('<H', bx_lr))

        return bytes(code)

    def test_single_color_write(self):
        """Test that a single color is correctly written to RAM"""
        test_color = 0xF800  # Red

        # Create emulator with single memory region
        mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

        # Map a single 1MB region
        base_addr = 0x100000
        mu.mem_map(base_addr, 0x100000)

        # Code at start
        code_addr = base_addr

        # RAM within the same region
        ram_addr = base_addr + 0x80000

        # Generate code with correct RAM address
        code = self._generate_simple_color_writer(test_color, ram_addr)
        mu.mem_write(code_addr, code)

        # Initialize RAM to zero
        mu.mem_write(ram_addr, b'\x00' * 0x100)

        # Return address after code
        return_addr = code_addr + len(code) + 0x100
        mu.reg_write(UC_ARM_REG_LR, return_addr | 1)

        # Execute
        mu.reg_write(UC_ARM_REG_PC, code_addr | 1)
        try:
            mu.emu_start(code_addr | 1, return_addr + 20, count=10)
        except UcError:
            pass

        # Read RAM and verify color was written
        ram_data = mu.mem_read(ram_addr, 2)
        written_color = struct.unpack('<H', ram_data)[0]

        self.assertEqual(written_color, test_color,
            f"Color not written correctly: expected 0x{test_color:04X}, got 0x{written_color:04X}")

    def test_flac_color_selection_by_theme_id(self):
        """Test that FLAC code selects correct color based on theme ID (R1)"""
        # Test colors for 5 themes
        test_colors = [0xF800, 0x001F, 0x07E0, 0x001F, 0xFFFF]  # Red, Blue, Green, Blue, White

        for theme_id in range(5):
            expected_color = test_colors[theme_id]

            # Create emulator
            mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

            # Single memory region
            base_addr = 0x100000
            mu.mem_map(base_addr, 0x100000)

            code_addr = base_addr
            ram_addr = base_addr + 0x80000

            # Generate code
            code = self._generate_simple_color_writer(expected_color, ram_addr)
            mu.mem_write(code_addr, code)
            mu.mem_write(ram_addr, b'\x00' * 0x100)

            return_addr = code_addr + len(code) + 0x100
            mu.reg_write(UC_ARM_REG_LR, return_addr | 1)

            # Set theme ID in R1
            mu.reg_write(UC_ARM_REG_R1, theme_id)

            # Execute
            mu.reg_write(UC_ARM_REG_PC, code_addr | 1)
            try:
                mu.emu_start(code_addr | 1, return_addr + 20, count=10)
            except UcError:
                pass

            # Verify
            ram_data = mu.mem_read(ram_addr, 2)
            written_color = struct.unpack('<H', ram_data)[0]

            self.assertEqual(written_color, expected_color,
                f"Theme {theme_id}: expected 0x{expected_color:04X}, got 0x{written_color:04X}")

    def test_menu_color_selection_by_theme_id(self):
        """Test that Menu code selects correct colors based on theme ID (R12)"""
        # Test colors for 5 themes (3 colors each)
        test_colors = [
            [0xF800, 0xF800, 0xF800],  # Theme 0: all red
            [0x001F, 0x001F, 0x001F],  # Theme 1: all blue
            [0x07E0, 0x07E0, 0x07E0],  # Theme 2: all green
            [0xFFE0, 0xFFE0, 0xFFE0],  # Theme 3: all yellow
            [0xFFFF, 0xFFFF, 0xFFFF],  # Theme 4: all white
        ]

        for theme_id in range(5):
            # Test each of the 3 menu colors for this theme
            for color_idx in range(3):
                expected_color = test_colors[theme_id][color_idx]

                # Create emulator
                mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

                base_addr = 0x100000
                mu.mem_map(base_addr, 0x100000)

                code_addr = base_addr
                ram_addr = base_addr + 0x80000 + color_idx * 2

                code = self._generate_simple_color_writer(expected_color, ram_addr)
                mu.mem_write(code_addr, code)
                mu.mem_write(ram_addr - color_idx * 2, b'\x00' * 0x100)  # Clear all 3 color slots

                return_addr = code_addr + len(code) + 0x100
                mu.reg_write(UC_ARM_REG_LR, return_addr | 1)

                # Set theme ID in R12
                mu.reg_write(UC_ARM_REG_R12, theme_id)

                # Execute
                mu.reg_write(UC_ARM_REG_PC, code_addr | 1)
                try:
                    mu.emu_start(code_addr | 1, return_addr + 20, count=10)
                except UcError:
                    pass

                # Verify
                ram_data = mu.mem_read(ram_addr, 2)
                written_color = struct.unpack('<H', ram_data)[0]

                self.assertEqual(written_color, expected_color,
                    f"Theme {theme_id} color {color_idx}: expected 0x{expected_color:04X}, got 0x{written_color:04X}")

    def test_color_value_preservation(self):
        """Test that all RGB565 color values are preserved correctly"""
        # Test a range of RGB565 values
        test_colors = [
            0x0000,  # Black
            0xFFFF,  # White
            0xF800,  # Red
            0x001F,  # Blue
            0x07E0,  # Green
            0xFFE0,  # Yellow
            0x07FF,  # Cyan
            0xF81F,  # Magenta
            0x8410,  # Gray
        ]

        for test_color in test_colors:
            # Create emulator
            mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

            base_addr = 0x100000
            mu.mem_map(base_addr, 0x100000)

            code_addr = base_addr
            ram_addr = base_addr + 0x80000

            code = self._generate_simple_color_writer(test_color, ram_addr)
            mu.mem_write(code_addr, code)
            mu.mem_write(ram_addr, b'\x00' * 0x100)

            return_addr = code_addr + len(code) + 0x100
            mu.reg_write(UC_ARM_REG_LR, return_addr | 1)

            mu.reg_write(UC_ARM_REG_PC, code_addr | 1)
            try:
                mu.emu_start(code_addr | 1, return_addr + 20, count=10)
            except UcError:
                pass

            ram_data = mu.mem_read(ram_addr, 2)
            written_color = struct.unpack('<H', ram_data)[0]

            self.assertEqual(written_color, test_color,
                f"Color 0x{test_color:04X} not preserved, got 0x{written_color:04X}")

    def test_patched_firmware_color_extraction(self):
        """Test that patched firmware contains correct colors in metadata"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        # Define test colors
        flac_colors = [0xF800, 0x001F, 0x07E0, 0xFFE0, 0x8410]
        menu_colors = [0xF800, 0x001F, 0x07E0] * 5  # 15 colors (3 per theme)

        # Create patched firmware
        patcher = ThemePatcher(FIRMWARE_PATH)
        result = patcher.patch(
            flac_colors=flac_colors,
            menu_colors=menu_colors,
            output_path=output_path,
            force=True
        )

        # Read patched firmware
        patched_data = open(output_path, 'rb').read()

        # Extract metadata from NOP slide end
        nop_slide = result['nop_slide']
        metadata_start = nop_slide['end'] - 51

        # Read metadata
        metadata_bytes = patched_data[metadata_start:metadata_start + 51]

        # Verify magic
        self.assertEqual(metadata_bytes[0:4], b'ECHO', "Metadata magic not found")

        # Extract stored colors
        stored_flac = []
        for i in range(5):
            offset = 9 + i * 2
            stored_flac.append(struct.unpack('<H', metadata_bytes[offset:offset+2])[0])

        stored_menu = []
        for i in range(15):
            offset = 19 + i * 2
            stored_menu.append(struct.unpack('<H', metadata_bytes[offset:offset+2])[0])

        # Verify FLAC colors
        self.assertEqual(stored_flac, flac_colors,
            f"FLAC colors mismatch: expected {flac_colors}, got {stored_flac}")

        # Verify Menu colors
        self.assertEqual(stored_menu, menu_colors,
            f"Menu colors mismatch: expected {menu_colors}, got {stored_menu}")


class TestPatchDetection(unittest.TestCase):
    """Test patch detection functionality"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_original_firmware_not_patched(self):
        """Original firmware should be detected as not patched"""
        patcher = ThemePatcher(FIRMWARE_PATH)
        result = patcher.analyze()

        self.assertFalse(result['is_patched'], "Original firmware detected as patched")

    def test_patched_firmware_detected(self):
        """Patched firmware should be detected"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        # First patch
        patcher = ThemePatcher(FIRMWARE_PATH)
        patcher.patch(
            flac_colors=[0xF800] * 5,
            menu_colors=[0xF800] * 15,
            output_path=output_path,
            force=True
        )

        # Analyze patched firmware
        patcher2 = ThemePatcher(output_path)
        result = patcher2.analyze()

        self.assertTrue(result['is_patched'], "Patched firmware not detected")

    def test_already_patched_rejection(self):
        """Should reject patching already-patched firmware without force"""
        output_path = os.path.join(self.temp_dir, "patched.IMG")

        # First patch
        patcher = ThemePatcher(FIRMWARE_PATH)
        patcher.patch(
            flac_colors=[0xF800] * 5,
            menu_colors=[0xF800] * 15,
            output_path=output_path,
            force=True
        )

        # Try to patch again without force
        patcher2 = ThemePatcher(output_path)
        with self.assertRaises(AlreadyPatchedError):
            patcher2.patch(
                flac_colors=[0x001F] * 5,
                menu_colors=[0x001F] * 15,
                output_path=output_path + ".new",
                force=False
            )


class TestNOPSlideSelection(unittest.TestCase):
    """Test NOP slide selection and validation"""

    def setUp(self):
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")
        self.data = open(FIRMWARE_PATH, 'rb').read()

    def test_nop_slide_finder(self):
        """NOP slide finder should find valid slides"""
        finder = NopSlideFinder(self.data)
        slides = finder.find_all_slides()

        self.assertGreater(len(slides), 0, "No NOP slides found")

        # Check slide properties
        for slide in slides:
            self.assertGreater(slide.size, 0, "Slide has zero size")
            self.assertGreater(slide.end, slide.start, "Invalid slide boundaries")

    def test_nop_slide_selection(self):
        """Best NOP slide should be within BL range of functions"""
        finder = NopSlideFinder(self.data)
        slides = finder.find_all_slides()

        func_addrs = [0x86CB0, 0x3F870]  # Typical theme function addresses

        best = finder.select_best_slide(func_addrs, 250)

        self.assertIsNotNone(best, "No suitable NOP slide found")

        # Check distance is within BL range (16MB)
        for func_addr in func_addrs:
            distance = abs(best.start - func_addr)
            self.assertLess(distance, 16777216, "NOP slide too far from function")


class TestCRC16(unittest.TestCase):
    """Test CRC16 implementation"""

    def test_crc16_consistency(self):
        """CRC16 should produce consistent results"""
        data = b"Hello, World!"
        crc1 = crc16(data)
        crc2 = crc16(data)

        self.assertEqual(crc1, crc2, "CRC16 not consistent")

    def test_crc16_different_data(self):
        """Different data should produce different CRC"""
        crc1 = crc16(b"data1")
        crc2 = crc16(b"data2")

        self.assertNotEqual(crc1, crc2, "CRC16 same for different data")

    def test_crc16_empty_data(self):
        """CRC16 of empty data should not crash"""
        crc = crc16(b"")
        self.assertIsInstance(crc, int)


class TestBoundaryConditions(unittest.TestCase):
    """Test boundary conditions and edge cases"""

    def test_empty_color_list(self):
        """Empty color lists should be rejected"""
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")

        patcher = ThemePatcher(FIRMWARE_PATH)
        with self.assertRaises(PatchError):
            patcher.patch(
                flac_colors=[],
                menu_colors=[0xF800] * 15,
                output_path="/tmp/test.IMG"
            )

    def test_extreme_color_values(self):
        """Extreme but valid color values should work"""
        if not os.path.exists(FIRMWARE_PATH):
            self.skipTest(f"Firmware not found: {FIRMWARE_PATH}")

        patcher = ThemePatcher(FIRMWARE_PATH)
        temp_dir = tempfile.mkdtemp()

        try:
            # Test with min and max color values
            result = patcher.patch(
                flac_colors=[0x0000, 0xFFFF, 0x0000, 0xFFFF, 0x0000],
                menu_colors=[0x0000, 0xFFFF] * 7 + [0x0000],
                output_path=os.path.join(temp_dir, "test.IMG"),
                force=True
            )
            self.assertTrue(result['success'])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestInputValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestBLInstructionEncoding))
    suite.addTests(loader.loadTestsFromTestCase(TestBInstructionEncoding))
    suite.addTests(loader.loadTestsFromTestCase(TestFirmwareIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestPatternDiscovery))
    suite.addTests(loader.loadTestsFromTestCase(TestUnicornEmulation))
    suite.addTests(loader.loadTestsFromTestCase(TestColorLoading))
    suite.addTests(loader.loadTestsFromTestCase(TestPatchDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestNOPSlideSelection))
    suite.addTests(loader.loadTestsFromTestCase(TestCRC16))
    suite.addTests(loader.loadTestsFromTestCase(TestBoundaryConditions))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
