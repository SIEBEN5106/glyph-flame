#!/usr/bin/env python3
"""
Round-Trip Emulation Tests for Theme Color Selection

This performs ACTUAL emulation (not just static verification) to verify:
1. FLAC function: Emulate with R1=0,1,2,3,4 and verify R0 returns correct colors
2. Menu function: Verify the color MOVWs exist (static verification for now)

This is REAL testing - we execute the code and verify it works.
"""

import sys
from pathlib import Path

try:
	from unicorn import *
	from unicorn.arm_const import *
except ImportError:
	print("Error: unicorn module not found")
	print("Install with: pip install unicorn")
	print("Or use: /nix/store/lc6q15imd72k6a4mpm9zzr3g0yygs4k6-system-path/bin/python3")
	sys.exit(1)

# Expected colors for each theme index
FLAC_COLORS = {
	0: 0x44DE,
	1: 0x44DE,
	2: 0x44DE,
	3: 0x44DE,
	4: 0xE162,
}

MENU_COLORS = {
	0: 0xEF5D,
	1: 0x10C3,
	2: 0xFF1C,
	3: 0xC6FC,
	4: 0xCC29,
}

FLAC_SIGNATURE = bytes([0x04, 0x29, 0x0C, 0xBF])  # CMP R1,#4 + ITE EQ


def discover_flac_function(firmware: bytes) -> int | None:
	"""Discover FLAC function by searching for CMP+ITE pattern"""
	end = min(0x100000, len(firmware) - 4)
	for addr in range(0x80000, end, 2):
		if firmware[addr:addr+2] == bytes([0x04, 0x29]):  # CMP R1,#4
			if firmware[addr+2:addr+4] == bytes([0x0C, 0xBF]):  # ITE EQ
				return addr
	return None


def discover_menu_function(firmware: bytes) -> int | None:
	"""Discover Menu function by searching for MOV.W R12,#0 pattern"""
	end = min(0x50000, len(firmware) - 20)
	for addr in range(0x30000, end, 2):
		if firmware[addr:addr+4] == bytes([0x4F, 0xF0, 0x00, 0x0C]):
			# Check for MOVW instructions nearby
			has_movw = False
			for check_offset in [4, 6, 8, 10, 12]:
				check_addr = addr + check_offset
				if check_addr + 4 <= len(firmware):
					hw = firmware[check_addr] | (firmware[check_addr + 1] << 8)
					if (hw & 0xFB00) == 0xF200:
						has_movw = True
						break
			if has_movw:
				return addr
	return None


def find_function_start(firmware: bytes, addr: int, max_back: int = 200) -> int:
	"""Find function start by tracing back to PUSH instruction"""
	for back in range(addr, max(0, addr - max_back), -2):
		hw = firmware[back] | (firmware[back + 1] << 8)
		if (hw & 0xFE00) == 0xB400 or (hw & 0xFF00) == 0xB500 or hw == 0xE92D:
			return back
	return addr


def round_trip_test_flac(firmware: bytes, patch_addr: int, firmware_name: str) -> dict:
	"""Round-trip test FLAC color selection logic with all theme indices

	Extracts ONLY the color selection logic (CMP+ITE+MOVW+MOVW) and emulates it.
	Then adds MOV R0,R1 and BX LR to return the color in R0.
	This tests the actual execution, not just static verification.
	"""
	print(f"\n  Testing FLAC color logic at 0x{patch_addr:X} (round-trip emulation)")

	# Extract ONLY the color selection logic: CMP + ITE + MOVW + MOVW (12 bytes)
	# Then add: MOV R0,R1 (2 bytes) + BX LR (2 bytes)
	# Total: 16 bytes
	LOGIC_SIZE = 12
	if patch_addr + LOGIC_SIZE > len(firmware):
		return {"all_passed": False, "error": "Cannot extract color logic"}

	# Extract the 12 bytes of color selection logic
	color_logic = firmware[patch_addr:patch_addr + LOGIC_SIZE]
	# Add MOV R0,R1 (0x08 0x46) and BX LR (0x70 0x47)
	color_logic_with_ret = color_logic + bytes([0x08, 0x46, 0x70, 0x47])

	# Verify it starts with CMP+ITE
	if color_logic[0:2] != bytes([0x04, 0x29]) or color_logic[2:4] != bytes([0x0C, 0xBF]):
		return {"all_passed": False, "error": "Invalid color logic signature"}

	CODE_ADDR = 0x10000

	results = {}
	all_passed = True

	for theme_idx, expected_color in FLAC_COLORS.items():
		try:
			uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)

			# Map code region
			map_base = CODE_ADDR & ~0xFFF
			uc.mem_map(map_base, 0x1000, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)

			# Write the color selection logic with BX LR
			uc.mem_write(CODE_ADDR, color_logic_with_ret)

			# Set up registers: R1 = theme index
			uc.reg_write(UC_ARM_REG_R1, theme_idx)
			uc.reg_write(UC_ARM_REG_LR, (CODE_ADDR + 100) | 1)  # LR with Thumb bit
			uc.reg_write(UC_ARM_REG_PC, CODE_ADDR | 1)  # PC with Thumb bit!
			uc.reg_write(UC_ARM_REG_CPSR, 0x000001F3)  # T-bit set in CPSR

			# Hook to stop at BX LR
			def hook_code(uc, address, size, user_data):
				try:
					instr_bytes = uc.mem_read(address, 2)
					if instr_bytes[0] == 0x70 and instr_bytes[1] == 0x47:  # BX LR
						uc.emu_stop()
				except:
					pass

			uc.hook_add(UC_HOOK_CODE, hook_code)

			# Emulate - start address MUST have Thumb bit (odd)
			uc.emu_start(CODE_ADDR | 1, (CODE_ADDR + 100) | 1, 0, 20)

			# Check R0
			r0 = uc.reg_read(UC_ARM_REG_R0)

			if r0 == expected_color:
				results[theme_idx] = {"expected": expected_color, "actual": r0, "passed": True}
				print(f"    ✅ Theme {theme_idx}: R0 = 0x{r0:04X}")
			else:
				results[theme_idx] = {"expected": expected_color, "actual": r0, "passed": False}
				print(f"    ❌ Theme {theme_idx}: R0 = 0x{r0:04X} (expected 0x{expected_color:04X})")
				all_passed = False

		except UcError as e:
			results[theme_idx] = {"expected": expected_color, "actual": None, "passed": False, "error": str(e)}
			print(f"    ❌ Theme {theme_idx}: {e}")
			all_passed = False

	return {
		"function": "FLAC",
		"patch_addr": patch_addr,
		"firmware": firmware_name,
		"results": results,
		"all_passed": all_passed
	}


def test_menu_colors_static(firmware: bytes, firmware_name: str) -> dict:
	"""Test Menu colors by static verification (search for MOVW instructions)"""
	print(f"\n  Testing Menu colors (static verification)")

	# Search for MOVW instructions with expected colors
	found_colors = {}
	search_start = 0x30000
	search_end = min(0x50000, len(firmware) - 4)

	for addr in range(search_start, search_end - 3, 2):
		hw1 = firmware[addr] | (firmware[addr + 1] << 8)
		if (hw1 & 0xFB00) == 0xF200:  # MOVW
			hw2 = firmware[addr + 2] | (firmware[addr + 3] << 8)
			i = (hw1 >> 10) & 1
			imm4 = hw1 & 0xF
			imm3 = (hw2 >> 12) & 0x7
			imm8 = hw2 & 0xFF
			imm16 = (imm4 << 12) | (i << 11) | (imm3 << 8) | imm8

			if imm16 in MENU_COLORS.values():
				if imm16 not in found_colors:
					found_colors[imm16] = []
				found_colors[imm16].append(addr)

	results = {}
	all_passed = True

	for theme_idx, expected_color in MENU_COLORS.items():
		if expected_color in found_colors:
			results[theme_idx] = {"expected": expected_color, "found": True, "passed": True}
			print(f"    ✅ Theme {theme_idx}: Color 0x{expected_color:04X} found")
		else:
			results[theme_idx] = {"expected": expected_color, "found": False, "passed": False}
			print(f"    ❌ Theme {theme_idx}: Color 0x{expected_color:04X} NOT FOUND")
			all_passed = False

	return {
		"function": "Menu",
		"firmware": firmware_name,
		"results": results,
		"all_passed": all_passed
	}


def test_firmware(firmware_path: Path) -> dict:
	"""Perform round-trip emulation testing on a single firmware"""
	firmware_name = firmware_path.parent.name
	print(f"\n{'='*60}")
	print(f"Testing: {firmware_name}")
	print(f"{'='*60}")

	try:
		with open(firmware_path, 'rb') as f:
			firmware = f.read()

		print(f"Firmware size: {len(firmware):,} bytes")

		# Discover FLAC function
		flac_addr = discover_flac_function(firmware)
		if flac_addr is None:
			print("  ❌ No FLAC function - UNSUPPORTED")
			return {"firmware": firmware_name, "supported": False, "reason": "No FLAC function"}

		print(f"  FLAC function: 0x{flac_addr:X}")

		# Round-trip test FLAC
		flac_result = round_trip_test_flac(firmware, flac_addr, firmware_name)

		# Test Menu colors
		menu_result = test_menu_colors_static(firmware, firmware_name)

		# Overall result
		supported = flac_result["all_passed"] and menu_result["all_passed"]

		print(f"\n  Result: {'✅ SUPPORTED' if supported else '❌ FAILED'}")

		return {
			"firmware": firmware_name,
			"supported": supported,
			"flac": flac_result,
			"menu": menu_result
		}

	except Exception as e:
		print(f"  ❌ ERROR: {e}")
		return {"firmware": firmware_name, "supported": False, "error": str(e)}


def main():
	"""Run round-trip emulation tests on all available firmwares"""
	print("=" * 60)
	print("Round-Trip Emulation Tests")
	print("=" * 60)

	firmware_dir = Path("/tmp/echo-mini-firmwares")
	firmware_files = list(firmware_dir.rglob("*.IMG"))

	if not firmware_files:
		print("⚠️  No firmware files found")
		return 1

	print(f"Found {len(firmware_files)} firmware files")

	# Test each firmware
	results = []
	for firmware_path in sorted(firmware_files):
		result = test_firmware(firmware_path)
		results.append(result)

	# Print summary
	print("\n" + "=" * 60)
	print("Summary")
	print("=" * 60)

	supported = [r for r in results if r.get("supported")]
	failed = [r for r in results if not r.get("supported")]

	print(f"\n✅ Supported ({len(supported)}):")
	for r in supported:
		flac_ok = "✅" if r["flac"]["all_passed"] else "❌"
		menu_ok = "✅" if r["menu"]["all_passed"] else "❌"
		print(f"  - {r['firmware']}: FLAC={flac_ok}, Menu={menu_ok}")

	if failed:
		print(f"\n❌ Failed ({len(failed)}):")
		for r in failed:
			reason = r.get("reason", "Unknown")
			error = r.get("error", "")
			if error:
				print(f"  - {r['firmware']}: {reason} ({error})")
			else:
				print(f"  - {r['firmware']}: {reason}")

	# Exit code
	all_supported = len(supported) == len(firmware_files)
	some_supported = len(supported) > 0

	print("\n" + "=" * 60)
	if all_supported:
		print("✅ ALL FIRMWARES SUPPORTED - Round-trip emulation works correctly")
		return 0
	elif some_supported:
		print(f"⚠️  {len(supported)}/{len(firmware_files)} firmwares supported")
		return 0
	else:
		print("❌ NO FIRMWARES SUPPORTED")
		return 1


if __name__ == '__main__':
	sys.exit(main())
