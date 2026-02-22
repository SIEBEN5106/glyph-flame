#!/usr/bin/env python3
"""
Re-patching Test with Unicorn Emulation

This test verifies that re-patching works correctly:
1. Patch firmware with first set of colors
2. Use Unicorn to verify first patch works
3. Re-patch with different colors
4. Use Unicorn to verify re-patched firmware works with new colors
5. Verify NOP slide is reused (same start address)

NO CIRCULAR INFERENCE - we test the ACTUAL re-patched firmware.
"""

import sys
import subprocess
from pathlib import Path

try:
	from unicorn import *
	from unicorn.arm_const import *
except ImportError:
	print("Error: unicorn module not found")
	print("Install with: pip install unicorn")
	print("Or use: /nix/store/lc6q15imd72k6a4mpm9zzr3g0yygs4k6-system-path/bin/python3")
	sys.exit(1)

# First set of colors (for initial patch) - distinctly different from second set
FIRST_FLAC_COLORS = {
	0: 0xF800,  # Red
	1: 0xF800,
	2: 0xF800,
	3: 0xF800,
	4: 0x07E0,  # Green
}

FIRST_MENU_COLORS = [
	0xF800, 0x07E0, 0x001F,  # T0: red, green, blue
	0xFFFF, 0xFFFF, 0xFFFF,  # T1: all white
	0xF800, 0xF800, 0xF800,  # T2: all red
	0x07E0, 0x07E0, 0x07E0,  # T3: all green
	0x001F, 0x001F, 0x001F,  # T4: all blue
]

# Second set of colors (for re-patch) - different from first
SECOND_FLAC_COLORS = {
	0: 0x44DE,  # Blue (cyan-like)
	1: 0x44DE,
	2: 0x44DE,
	3: 0x44DE,
	4: 0xE162,  # Gold
}

SECOND_MENU_COLORS = [
	0x77DE, 0x2945, 0x0000,  # T0: cyan, dark gray, black
	0xFFFF, 0x2945, 0xFFFF,  # T1: white, dark gray, white
	0x77DE, 0x0000, 0x2945,  # T2: cyan, black, dark gray
	0xFFFF, 0x0000, 0x0000,  # T3: white, black, black
	0xFFFF, 0x0000, 0x0000,  # T4: white, black, black
]


def discover_flac_function(firmware: bytes):
	"""Discover FLAC patch point - known address for ECHO MINI V3.1.0"""
	flac_patch_addr = 0x86CB0

	if flac_patch_addr + 4 < len(firmware):
		hw1 = firmware[flac_patch_addr] | (firmware[flac_patch_addr + 1] << 8)
		if (hw1 & 0xF800) == 0xF000:
			return flac_patch_addr

	return None


def find_nop_slide_start(firmware: bytes, flac_patch_addr: int):
	"""Find NOP slide start by decoding BL instruction"""
	bl_bytes = firmware[flac_patch_addr:flac_patch_addr + 4]
	hw1 = bl_bytes[0] | (bl_bytes[1] << 8)
	hw2 = bl_bytes[2] | (bl_bytes[3] << 8)

	S = (hw1 >> 10) & 1
	J1 = (hw2 >> 13) & 1
	J2 = (hw2 >> 11) & 1
	imm10 = hw1 & 0x3FF
	imm11 = hw2 & 0x7FF

	# imm10 is bits [21:12], imm11 is bits [11:1], so shift imm11 left by 1
	imm25 = (S << 24) | ((~(J1 ^ S) & 1) << 23) | ((~(J2 ^ S) & 1) << 22) | (imm10 << 12) | (imm11 << 1)

	# Shift left by 1 to get byte offset (bit 0 of imm25 is always 0)
	imm32 = imm25 << 1

	if S:
		imm32 |= 0xFE000000  # Sign extend from bit 25

	target = flac_patch_addr + 4 + imm32
	return target


def emulate_flac_handler(firmware: bytes, flac_code_addr: int, theme_idx: int, expected_color: int) -> dict:
	"""Emulate FLAC handler and verify it returns expected color"""
	uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

	code_base = flac_code_addr & ~0xFFF
	uc.mem_map(code_base, 0x10000, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)
	# Map more bytes to include the color table and full NOP slide code
	uc.mem_write(flac_code_addr, firmware[flac_code_addr:flac_code_addr + 512])

	# Also map stack region
	uc.mem_map(0x20000000, 0x10000, UC_PROT_READ | UC_PROT_WRITE)
	uc.reg_write(UC_ARM_REG_SP, 0x20008000)

	uc.reg_write(UC_ARM_REG_CPSR, 0x000001F3)
	uc.reg_write(UC_ARM_REG_R1, theme_idx)
	uc.reg_write(UC_ARM_REG_LR, (flac_code_addr + 100) | 1)
	uc.reg_write(UC_ARM_REG_PC, flac_code_addr | 1)

	last_mem_access = {"addr": None, "type": None}

	def hook_mem_invalid(uc, access, address, size, value, user_data):
		last_mem_access["addr"] = address
		last_mem_access["type"] = access
		return False  # Don't handle

	def hook_code(uc, address, size, user_data):
		try:
			instr_bytes = uc.mem_read(address, 2)
			if instr_bytes[0] == 0x70 and instr_bytes[1] == 0x47:
				uc.emu_stop()
		except:
			pass

	uc.hook_add(UC_HOOK_MEM_INVALID, hook_mem_invalid)
	uc.hook_add(UC_HOOK_CODE, hook_code)

	try:
		uc.emu_start(flac_code_addr | 1, (flac_code_addr + 1000) | 1, 0, 100)
		r0 = uc.reg_read(UC_ARM_REG_R0)

		if r0 == expected_color:
			return {"expected": expected_color, "actual": r0, "passed": True}
		else:
			return {"expected": expected_color, "actual": r0, "passed": False}

	except UcError as e:
		error_msg = str(e)
		if last_mem_access["addr"] is not None:
			access_type = {1: "READ", 2: "WRITE", 4: "FETCH"}.get(last_mem_access["type"], "UNKNOWN")
			error_msg += f" at 0x{last_mem_access['addr']:X} ({access_type})"
		return {"expected": expected_color, "actual": None, "passed": False, "error": error_msg}


def test_repatching():
	"""Test re-patching with Unicorn verification"""
	print("=" * 60)
	print("Re-patching Test with Unicorn Emulation")
	print("=" * 60)

	# Paths
	original_firmware = Path("/tmp/echo-mini-firmwares/ECHO MINI V3.1.0/ECHO MINI V3.1.0/HIFIEC10.IMG")
	first_patched = Path("/tmp/repatch_test_first.IMG")
	repatched = Path("/tmp/repatch_test_second.IMG")

	if not original_firmware.exists():
		print(f"\n❌ Original firmware not found: {original_firmware}")
		return 1

	# Step 1: Create first patch with TypeScript (custom colors)
	print("\n[Step 1] Creating first patch with custom colors...")
	PROJECT_ROOT = Path("/home/losses/Development/flame-ocean")

	first_patch_script = f"""
import {{ readFileSync }} from 'fs';
import {{ ThemePatcher }} from '{PROJECT_ROOT}/src/lib/rse/theme/patcher.js';

const original = readFileSync('{original_firmware}');
const patcher = new ThemePatcher(original);

const firstFlacColors = [0xF800, 0xF800, 0xF800, 0xF800, 0x07E0];
const firstMenuColors = [
	0xF800, 0x07E0, 0x001F,
	0xFFFF, 0xFFFF, 0xFFFF,
	0xF800, 0xF800, 0xF800,
	0x07E0, 0x07E0, 0x07E0,
	0x001F, 0x001F, 0x001F,
];

const result = patcher.patch(firstFlacColors, firstMenuColors, '{first_patched}', true);
console.log(JSON.stringify({{ success: result.success }}));
"""
	first_patch_script_path = Path("/tmp/first_patch_script.ts")
	first_patch_script_path.write_text(first_patch_script)

	first_result = subprocess.run([
		"bun", "run", str(first_patch_script_path)
	], capture_output=True, text=True)

	if first_result.returncode != 0:
		print(f"❌ Failed to create first patch:")
		print(first_result.stderr)
		return 1

	if first_result.stderr:
		print("[DEBUG OUTPUT from first patch]:")
		for line in first_result.stderr.split('\n'):
			if '[DEBUG]' in line or '[INFO]' in line:
				print(f"  {line}")

	print(f"✅ First patch created: {first_patched}")

	# Step 2: Verify first patch with Unicorn
	print("\n[Step 2] Verifying first patch with Unicorn...")
	with open(first_patched, 'rb') as f:
		first_firmware = f.read()

	flac_patch_addr = discover_flac_function(first_firmware)
	if not flac_patch_addr:
		print("❌ FLAC patch point not found in first patched firmware")
		return 1

	first_nop_slide = find_nop_slide_start(first_firmware, flac_patch_addr)
	print(f"  NOP slide: 0x{first_nop_slide:X}")

	# Test a few theme indices
	test_themes = [0, 4]  # Test theme 0 and 4
	first_flac_passed = True
	for theme_idx in test_themes:
		expected = FIRST_FLAC_COLORS[theme_idx]
		result = emulate_flac_handler(first_firmware, first_nop_slide, theme_idx, expected)
		if result["passed"]:
			print(f"  ✅ Theme {theme_idx}: R0 = 0x{result['actual']:04X}")
		else:
			actual = result['actual']
			actual_str = f"0x{actual:04X}" if actual is not None else "None"
			error_str = f" (error: {result.get('error', 'unknown')})" if 'error' in result else ""
			print(f"  ❌ Theme {theme_idx}: Expected 0x{expected:04X}, got {actual_str}{error_str}")
			first_flac_passed = False

	if not first_flac_passed:
		print("❌ First patch verification failed")
		return 1

	print("✅ First patch verified with Unicorn")

	# Step 3: Create TypeScript re-patch script
	print("\n[Step 3] Re-patching with different colors...")
	PROJECT_ROOT = Path("/home/losses/Development/flame-ocean")

	repatch_script = f"""
import {{ readFileSync }} from 'fs';
import {{ ThemePatcher }} from '{PROJECT_ROOT}/src/lib/rse/theme/patcher.js';

const firstPatched = readFileSync('{first_patched}');
const patcher = new ThemePatcher(firstPatched);

const newFlacColors = [0x44DE, 0x44DE, 0x44DE, 0x44DE, 0xE162];
const newMenuColors = [
	0x77DE, 0x2945, 0x0000,
	0xFFFF, 0x2945, 0xFFFF,
	0x77DE, 0x0000, 0x2945,
	0xFFFF, 0x0000, 0x0000,
	0xFFFF, 0x0000, 0x0000,
];

const result = patcher.patch(newFlacColors, newMenuColors, '{repatched}', true);
console.log(JSON.stringify({{
	success: result.success,
	nopSlideStart: result.nopSlide.start,
	metadataAddr: result.metadataAddr
}}));
"""
	repatch_script_path = Path("/tmp/repatch_script.ts")
	repatch_script_path.write_text(repatch_script)

	# Run re-patch
	repatch_result = subprocess.run([
		"bun", "run", str(repatch_script_path)
	], capture_output=True, text=True)

	if repatch_result.returncode != 0:
		print(f"❌ Re-patch failed:")
		print(repatch_result.stderr)
		return 1

	if repatch_result.stderr:
		print("[DEBUG OUTPUT from re-patch]:")
		for line in repatch_result.stderr.split('\n'):
			if '[DEBUG]' in line or '[INFO]' in line:
				print(f"  {line}")

	print(f"✅ Re-patch created: {repatched}")

	# Step 4: Verify re-patched firmware with Unicorn
	print("\n[Step 4] Verifying re-patched firmware with Unicorn...")
	with open(repatched, 'rb') as f:
		repatched_firmware = f.read()

	repatched_nop_slide = find_nop_slide_start(repatched_firmware, flac_patch_addr)
	print(f"  NOP slide: 0x{repatched_nop_slide:X}")

	# Verify NOP slide is reused
	if repatched_nop_slide != first_nop_slide:
		print(f"❌ NOP slide changed! First: 0x{first_nop_slide:X}, Re-patched: 0x{repatched_nop_slide:X}")
		return 1
	print(f"✅ NOP slide reused (same address: 0x{first_nop_slide:X})")

	# Test that new colors work
	second_flac_passed = True
	for theme_idx in test_themes:
		expected = SECOND_FLAC_COLORS[theme_idx]
		result = emulate_flac_handler(repatched_firmware, repatched_nop_slide, theme_idx, expected)
		if result["passed"]:
			print(f"  ✅ Theme {theme_idx}: R0 = 0x{result['actual']:04X}")
		else:
			actual = result['actual']
			actual_str = f"0x{actual:04X}" if actual is not None else "None"
			error_str = f" (error: {result.get('error', 'unknown')})" if 'error' in result else ""
			print(f"  ❌ Theme {theme_idx}: Expected 0x{expected:04X}, got {actual_str}{error_str}")
			second_flac_passed = False

	if not second_flac_passed:
		print("❌ Re-patched firmware verification failed")
		return 1

	print("✅ Re-patched firmware verified with Unicorn")

	# Summary
	print("\n" + "=" * 60)
	print("Summary")
	print("=" * 60)
	print("✅ Re-patching works correctly:")
	print("  - First patch works with Unicorn emulation")
	print("  - Re-patch reuses same NOP slide")
	print("  - Re-patched firmware works with new colors")
	print("  - NO CIRCULAR INFERENCE - tested with actual emulation")

	return 0


if __name__ == '__main__':
	sys.exit(test_repatching())
