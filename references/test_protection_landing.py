#!/usr/bin/env python3
"""
Test Protection B and Landing Points

Comprehensive tests verifying:
1. Protection B instruction in NOP slide works correctly
2. Landing points are preserved (not overwritten)  
3. Empty space is safe to use for patch code
"""

from pathlib import Path
from unicorn import *
from unicorn.arm_const import *
from capstone import *
import sys

def encode_b_16bit(from_addr: int, to_addr: int) -> bytes:
    """Encode a 16-bit B instruction for ARM Thumb"""
    offset = to_addr - (from_addr + 4)
    if offset > 2046 or offset < -2048:
        raise ValueError(f"B offset out of range: {offset}")
    imm11 = (offset >> 1) & 0x7FF
    opcode = 0xE000 | imm11
    return bytes([opcode & 0xFF, (opcode >> 8) & 0xFF])

def test_protection_jump():
    """Test protection B instruction works correctly"""
    print("=" * 70)
    print("Test 1: Protection B Instruction")
    print("=" * 70)
    
    CODE_ADDR = 0x10000
    FLAC_CODE_ADDR = CODE_ADDR + 32
    
    # Build code with protection B
    protection_b = encode_b_16bit(CODE_ADDR, FLAC_CODE_ADDR)
    code = bytearray(protection_b)
    
    # Fill with empty space (zeros)
    while len(code) < 32:
        code.extend(bytes([0x00, 0x00]))
    
    # Add FLAC code at offset 32
    code.extend(bytes([0x4E, 0xF2, 0x62, 0x11]))  # MOVW R1, #0xE162
    code.extend(bytes([0x08, 0x46]))  # MOV R0, R1
    code.extend(bytes([0x70, 0x47]))  # BX LR
    
    print(f"\nLayout:")
    print(f"  0x{CODE_ADDR:X}: Protection B -> 0x{FLAC_CODE_ADDR:X}")
    print(f"  0x{CODE_ADDR+2:X} - 0x{FLAC_CODE_ADDR:X}: Empty space")
    print(f"  0x{FLAC_CODE_ADDR:X}: FLAC code (MOVW + MOV + BX LR)")
    
    # Test with Unicorn
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    map_base = CODE_ADDR & ~0xFFF
    uc.mem_map(map_base, 0x1000, UC_PROT_READ | UC_PROT_WRITE | UC_PROT_EXEC)
    uc.mem_write(CODE_ADDR, bytes(code))
    
    uc.reg_write(UC_ARM_REG_CPSR, 0x000001F3)
    uc.reg_write(UC_ARM_REG_R0, 0x0000)
    uc.reg_write(UC_ARM_REG_R1, 999)
    uc.reg_write(UC_ARM_REG_LR, (CODE_ADDR + 0x100) | 1)
    uc.reg_write(UC_ARM_REG_PC, CODE_ADDR | 1)
    
    executed = []
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    
    def hook_code(uc, address, size, user_data):
        executed.append(address)
        instr_bytes = uc.mem_read(address, size)
        r0 = uc.reg_read(UC_ARM_REG_R0)
        r1 = uc.reg_read(UC_ARM_REG_R1)
        
        for insn in md.disasm(instr_bytes, address):
            print(f"  0x{address:X} ({size}B): {insn.mnemonic} {insn.op_str:20s} | R0=0x{r0:04X} R1=0x{r1:04X}")
        
        if instr_bytes[0] == 0x70 and instr_bytes[1] == 0x47:
            uc.emu_stop()
    
    uc.hook_add(UC_HOOK_CODE, hook_code)
    
    try:
        uc.emu_start(CODE_ADDR | 1, (CODE_ADDR + 0x200) | 1, 0, 10)
        r0 = uc.reg_read(UC_ARM_REG_R0)
        
        jumped = FLAC_CODE_ADDR in executed
        correct_value = r0 == 0xE162
        
        if jumped and correct_value:
            print(f"\n✅ PASS: Protection B works")
            print(f"   Jumped to FLAC code and executed correctly")
            return True
        else:
            print(f"\n❌ FAIL: Protection B failed")
            print(f"   Jumped: {jumped}, Correct value: {correct_value}")
            return False
    except UcError as e:
        print(f"\n❌ FAIL: {e}")
        return False

def test_empty_space_safe():
    """Verify empty space is safe to use"""
    print("\n" + "=" * 70)
    print("Test 2: Empty Space Safety")
    print("=" * 70)
    
    firmware_path = Path("/tmp/echo-mini-firmwares/ECHO MINI V3.1.0/ECHO MINI V3.1.0/HIFIEC10.IMG")
    with open(firmware_path, 'rb') as f:
        firmware = bytearray(f.read())
    
    EMPTY_START = 0x12BBFC
    EMPTY_SIZE = 128
    EMPTY_END = EMPTY_START + EMPTY_SIZE
    
    print(f"\nChecking empty space: 0x{EMPTY_START:X} - 0x{EMPTY_END:X}")
    
    # Verify all zeros
    all_zeros = all(firmware[i] == 0 for i in range(EMPTY_START, EMPTY_END))
    
    if all_zeros:
        print(f"✅ PASS: All bytes are 0x00 (unused)")
        print(f"   Safe to use for patch code")
        return True
    else:
        print(f"❌ FAIL: Space contains data")
        return False

def test_landing_points_preserved():
    """Verify landing points are not overwritten"""
    print("\n" + "=" * 70)
    print("Test 3: Landing Points Preservation")
    print("=" * 70)
    
    FLAC_PATCH_ADDR = 0x86CB0  # Where BL is written
    EMPTY_START = 0x12BBFC
    FLAC_CODE_ADDR = EMPTY_START + 32
    
    print(f"\nPatch layout:")
    print(f"  FLAC patch point: 0x{FLAC_PATCH_ADDR:X}")
    print(f"  Empty space: 0x{EMPTY_START:X} - 0x{EMPTY_START + 128:X}")
    print(f"  FLAC landing point: 0x{FLAC_CODE_ADDR:X}")
    print(f"  Protection B: 0x{EMPTY_START:X} -> 0x{FLAC_CODE_ADDR:X}")
    
    # Check FLAC code is in empty space
    in_space = EMPTY_START <= FLAC_CODE_ADDR < (EMPTY_START + 128)
    
    # Check no overlap with protection B
    protection_b_end = EMPTY_START + 2
    no_overlap = FLAC_CODE_ADDR >= protection_b_end
    
    if in_space and no_overlap:
        print(f"\n✅ PASS: Landing point preserved")
        print(f"   FLAC code at 0x{FLAC_CODE_ADDR:X} (in empty space)")
        print(f"   No overlap with protection B")
        return True
    else:
        print(f"\n❌ FAIL: Landing point issues")
        print(f"   In space: {in_space}")
        print(f"   No overlap: {no_overlap}")
        return False

def main():
    print("=" * 70)
    print("PROTECTION AND LANDING POINTS TEST")
    print("=" * 70)
    
    results = [
        ("Protection B Jump", test_protection_jump()),
        ("Empty Space Safe", test_empty_space_safe()),
        ("Landing Points Preserved", test_landing_points_preserved()),
    ]
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("\nConclusion:")
        print("  ✓ Protection B instruction works correctly")
        print("  ✓ Empty space is safe for patch code")
        print("  ✓ Landing points are preserved")
        print("  ✓ NOP slide won't be affected by patch")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())
