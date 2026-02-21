#!/usr/bin/env python3
"""
Universal Theme Color Analyzer V3
- No assumptions about firmware data, addresses, patterns, or colors
- Complete Thumb instruction decoder implementation
- Detect theme-related functions based on instruction semantics
- Extract all theme colors and generate complete reports
"""

import os
import sys
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set
from enum import Enum, auto


# ============================================================================
# Data Structure Definitions
# ============================================================================

class InstructionType(Enum):
    """Instruction Type"""
    MOVW = auto()
    MOVS = auto()
    CMP = auto()
    BEQ = auto()
    BNE = auto()
    B = auto()
    CBZ = auto()
    CBNZ = auto()
    IT = auto()
    STRH = auto()
    STRH_W = auto()
    LDR = auto()
    LDRB = auto()
    PUSH = auto()
    POP = auto()
    BX = auto()
    ADD = auto()
    SUB = auto()
    AND = auto()
    ORR = auto()
    EOR = auto()
    LSL = auto()
    LSR = auto()
    ASR = auto()
    TST = auto()
    MVN = auto()
    RSB = auto()
    ADC = auto()
    SBC = auto()
    ROR = auto()
    NOP = auto()
    UNKNOWN = auto()


@dataclass
class Instruction:
    """Decoded Instruction"""
    addr: int
    raw_bytes: bytes
    mnemonic: str
    operands: str
    instr_type: InstructionType

    # Instruction Details
    rd: int = -1          # Destination register
    rn: int = -1          # Base register
    rm: int = -1          # Source register
    imm: int = 0          # Immediate value
    cond: int = -1        # Condition code
    it_mask: int = 0      # IT block mask
    branch_target: int = 0  # Branch target

    def __str__(self):
        return f"0x{self.addr:05X}: {self.mnemonic} {self.operands}"


@dataclass
class ColorWrite:
    """Color Write Record"""
    addr: int
    instr: Instruction
    color_value: int
    target_reg: int       # STRHBase register
    source_reg: int       # STRHSource register
    theme_condition: Optional[int] = None  # Applicable theme condition (None = unconditional)
    movw_instr: Optional['MovwRecord'] = None  # Corresponding MOVW instruction

    def __str__(self):
        return f"0x{self.addr:05X}: {self.instr.mnemonic} {self.instr.operands} -> 0x{self.color_value:04X}"


@dataclass
class MovwRecord:
    """MOVW Color Load Record"""
    addr: int
    instr: Instruction
    color_value: int
    target_reg: int       # Destination register
    theme_condition: Optional[int] = None  # Applicable theme condition

    def __str__(self):
        return f"0x{self.addr:05X}: {self.instr.mnemonic} {self.instr.operands} -> R{self.target_reg} = 0x{self.color_value:04X}"


@dataclass
class ThemeFunction:
    """Theme-Related Function"""
    addr: int
    end_addr: int
    pattern_type: str     # "switch_case", "ite", "preload_store"
    color_writes: List[ColorWrite] = field(default_factory=list)
    preload_colors: Dict[int, int] = field(default_factory=dict)  # reg -> color
    ui_element: str = "unknown"  # UI Element Label

    def get_theme_colors(self, theme_value: int) -> Dict[int, int]:
        """Get color mapping for specific theme"""
        # Determined via control flow simulation
        pass


@dataclass
class AnalysisReport:
    """Analysis Report"""
    firmware_path: str
    firmware_size: int
    theme_functions: List[ThemeFunction] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class PatchInfo:
    """Information about a patched firmware"""
    is_patched: bool = False
    patch_type: str = "none"  # "none", "flac_only", "menu_only", "full", "unknown"
    flac_patched: bool = False
    menu_patched: bool = False
    nop_has_code: bool = False
    patch_target_addr: int = 0
    confidence: float = 0.0
    metadata: Optional[Dict] = None


# ============================================================================
# Theme Discovery Tool - Based on decompilation analysis, no hardcoding
# ============================================================================

class ThemeDiscovery:
    """Dynamically discover theme info based on decompilation analysis"""

    @classmethod
    def discover_theme_count(cls, data: bytes) -> Tuple[int, List[str]]:
        """
        Dynamically discover theme count by analyzing CMP patterns in code

        Method:
        1. Search for PUSH instructions (function start) in firmware
        2. Analyze CMP instructions within functionImmediate value
        3. Find consecutive 0, 1, 2, ..., N patterns
        4. Use heuristic method to determine true theme count

        Returns: (Theme count, [])  # No longer extract theme names, only return count
        """
        # Create temporary decoder
        temp_decoder = ThumbDecoder(data)

        theme_counts = cls._analyze_cmp_patterns(temp_decoder, data)

        if theme_counts:
            # Heuristic method:
            # 1. Ignore results where count <= 3 (may be noise)
            # 2. Find highest frequency where count >= 5
            # 3. If none >= 5, take highest frequency >= 4

            valid_counts = {k: v for k, v in theme_counts.items() if k >= 5}
            if valid_counts:
                # Take highest frequency >= 5
                best = max(valid_counts.items(), key=lambda x: x[1])
                return best[0], []

            valid_counts = {k: v for k, v in theme_counts.items() if k >= 4}
            if valid_counts:
                best = max(valid_counts.items(), key=lambda x: x[1])
                return best[0], []

        # If analysis fails, return default value 5
        return 5, []

    @classmethod
    def _analyze_cmp_patterns(cls, decoder, data: bytes, search_start: int = 0x20000, search_end: int = 0x150000) -> Dict[int, int]:
        """
        Analyze CMP patterns in firmware, count theme count frequencies

        Returns: {theme_count: occurrence_count}
        """
        theme_count_freq = {}
        addr = search_start

        while addr < search_end:
            # Check if it's a function start (PUSH instruction)
            hw = decoder.read16(addr)
            if hw == 0:
                addr += 2
                continue

            instr = decoder.decode(addr)

            # Detect PUSH instruction (16-bit: 0xB500, 32-bit: 0xE92D)
            is_push = (hw & 0xFF00) == 0xB500 or (hw & 0xFFFF0000) == 0x92D0000E

            if is_push or instr.instr_type.name == 'PUSH':
                # Analyze CMP patterns in this function
                count = cls._count_theme_indices_in_function(decoder, addr)

                if count > 0:
                    theme_count_freq[count] = theme_count_freq.get(count, 0) + 1

            addr += 2

        return theme_count_freq

    @classmethod
    def _count_theme_indices_in_function(cls, decoder, func_addr: int, max_scan: int = 500) -> int:
        """
        Analyze CMP instructions in function, determine theme count

        Return max of consecutive CMP #0, #1, #2, ... + 1
        """
        theme_indices = set()
        offset = 0

        while offset < max_scan:
            hw = decoder.read16(func_addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(func_addr + offset)
            mn = instr.mnemonic.upper()

            # Check CMP instruction
            if 'CMP' in mn:
                imm = instr.imm
                # Theme indices are typically in range 0-15
                if 0 <= imm <= 15:
                    theme_indices.add(imm)

            offset += 4 if is_32bit else 2

        # Check for consecutive index sequences
        if not theme_indices:
            return 0

        # Find maximum consecutive sequence
        max_consecutive = 0
        for start in sorted(theme_indices):
            count = 0
            for i in range(start, max(theme_indices) + 1):
                if i in theme_indices:
                    count += 1
                else:
                    break
            if count > max_consecutive:
                max_consecutive = count

        # Need at least 2 consecutive indices for valid theme pattern
        if max_consecutive >= 2:
            return max_consecutive

        return 0

    @classmethod
    def detect_flac_by_context(cls, decoder: 'ThumbDecoder', func_addr: int, scan_range: int = 1200) -> dict:
        """
        Detect FLAC String function via call context features

        FLAC String function features:
        1. Contains '|' character operation (MOVS Rx, #0x7C)
        2. Has CMP Rx, #4 (16-bit CMP, not CMP.W R12) + IT + two consecutive MOVW pattern
        3. No branch instructions between MOVW instructions

        Returns: {is_flac, color_for_4, color_for_other, separator_addr, ...}
        """
        result = {
            'is_flac': False,
            'color_for_4': 0,
            'color_for_other': 0,
            'separator_addr': '',
            'movw_addr_4': '',
            'movw_addr_other': '',
        }

        offset = 0
        found_separator = False
        separator_offset = 0

        # Step 1: Search for '|' character operation (MOVS Rx, #0x7C)
        while offset < scan_range:
            hw = decoder.read16(func_addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(func_addr + offset)

            # Check MOVS Rx, #0x7C ('|' = 0x7C)
            if instr.mnemonic.upper() == 'MOVS' and instr.imm == 0x7C:
                found_separator = True
                separator_offset = offset
                result['separator_addr'] = f"0x{func_addr + offset:05X}"
                break

            offset += 4 if is_32bit else 2

        if not found_separator:
            # '|' character not found, not a FLAC function
            return result

        # Step 2: Search for FLAC color pattern within entire function
        # FLAC feature: CMP Rx, #4 (16-bit, not CMP.W R12) + IT + MOVW + MOVW (no branch gap)
        offset = 0
        while offset < scan_range:
            hw = decoder.read16(func_addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(func_addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # FLAC uses 16-bit CMP (hw < 0xE800), target is not R12
            # e.g.: CMP R1, #0x04 (hw = 0x2904)
            if 'CMP' in mn and (instr.imm == 4 or '#4' in ops or '#0x4' in ops):
                # Exclude CMP.W R12, #4 (this is switch_case feature, not FLAC)
                if is_32bit and 'R12' in ops:
                    offset += 4
                    continue

                # Check if followed by IT + MOVW + MOVW pattern (no branch gap)
                test_offset = offset + 2  # 16-bit CMP, so next instruction at +2

                # Check IT instruction
                it_hw = decoder.read16(func_addr + test_offset)
                if (it_hw & 0xFF00) == 0xBF00:  # IT instruction
                    test_offset += 2

                    # Collect two consecutive MOVW (no branch in between)
                    movw_list = []
                    temp_offset = test_offset
                    while temp_offset < scan_range and len(movw_list) < 2:
                        movw_hw = decoder.read16(func_addr + temp_offset)
                        movw_32bit = movw_hw >= 0xE800
                        movw_instr = decoder.decode(func_addr + temp_offset)
                        movw_mn = movw_instr.mnemonic.upper()

                        # If branch instruction encountered, stop (not FLAC pattern)
                        if movw_mn in ['BEQ', 'BNE', 'B', 'BL', 'CBZ', 'CBNZ']:
                            break

                        if 'MOVW' in movw_mn and '#' in movw_instr.operands:
                            try:
                                val_str = movw_instr.operands.split('#')[1].split()[0].rstrip('}')
                                val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                                movw_list.append({
                                    'addr': f"0x{func_addr + temp_offset:05X}",
                                    'color': val
                                })
                            except:
                                pass

                        temp_offset += 4 if movw_32bit else 2

                    # Verify FLAC pattern (two different color values, no branch gap)
                    if len(movw_list) == 2 and movw_list[0]['color'] != movw_list[1]['color']:
                        result['is_flac'] = True
                        result['color_for_4'] = movw_list[0]['color']
                        result['color_for_other'] = movw_list[1]['color']
                        result['movw_addr_4'] = movw_list[0]['addr']
                        result['movw_addr_other'] = movw_list[1]['addr']
                        return result

            offset += 4 if is_32bit else 2

        return result


# ============================================================================
# Thumb Instruction Decoder
# ============================================================================

class ThumbDecoder:
    """Thumb Instruction Decoder"""

    # Condition code names
    COND_NAMES = {
        0: "EQ", 1: "NE", 2: "CS", 3: "CC",
        4: "MI", 5: "PL", 6: "VS", 7: "VC",
        8: "HI", 9: "LS", 10: "GE", 11: "LT",
        12: "GT", 13: "LE", 14: "AL", 15: "AL"
    }

    # Register names
    REG_NAMES = [f"R{i}" for i in range(16)]
    REG_NAMES[13] = "SP"
    REG_NAMES[14] = "LR"
    REG_NAMES[15] = "PC"

    def __init__(self, data: bytes):
        self.data = data

    def read16(self, offset: int) -> int:
        if offset + 2 > len(self.data):
            return 0
        return self.data[offset] | (self.data[offset + 1] << 8)

    def read32(self, offset: int) -> int:
        if offset + 4 > len(self.data):
            return 0
        return struct.unpack('<I', self.data[offset:offset+4])[0]

    def decode(self, addr: int) -> Instruction:
        """Decode instruction at specified address"""
        if addr + 2 > len(self.data):
            return self._unknown(addr, b'\x00\x00')

        hw = self.read16(addr)

        # Check if 32-bit instruction
        if self._is_32bit(hw):
            if addr + 4 > len(self.data):
                return self._unknown(addr, bytes([hw & 0xFF, hw >> 8]))
            hw2 = self.read16(addr + 2)
            return self._decode_32bit(addr, hw, hw2)
        else:
            return self._decode_16bit(addr, hw)

    def _is_32bit(self, hw: int) -> bool:
        """Check if 32-bit Thumb instruction"""
        # 32-bit instruction prefix patterns
        return (hw & 0xF800) in [0xE800, 0xF000, 0xF800]

    def _unknown(self, addr: int, raw: bytes) -> Instruction:
        return Instruction(
            addr=addr,
            raw_bytes=raw,
            mnemonic="???",
            operands="",
            instr_type=InstructionType.UNKNOWN
        )

    def _decode_16bit(self, addr: int, hw: int) -> Instruction:
        """Decode 16-bit Thumb instruction"""
        raw = bytes([hw & 0xFF, hw >> 8])

        # Decode by opcode groups
        op = hw >> 11

        # Shift, add, subtract, move, and compare (bits [15:11])
        if op == 0b00000:  # LSL immediate
            return self._decode_lsl_imm(addr, hw, raw)
        elif op == 0b00001:  # LSR immediate
            return self._decode_lsr_imm(addr, hw, raw)
        elif op == 0b00010:  # ASR immediate
            return self._decode_asr_imm(addr, hw, raw)
        elif op == 0b00011:  # Add/Sub register/immediate
            return self._decode_add_sub(addr, hw, raw)
        elif op == 0b00100:  # MOV immediate
            return self._decode_mov_imm(addr, hw, raw)
        elif op == 0b00101:  # CMP immediate
            return self._decode_cmp_imm(addr, hw, raw)
        elif op == 0b00110:  # ADD immediate (8-bit)
            return self._decode_add8_imm(addr, hw, raw)
        elif op == 0b00111:  # SUB immediate (8-bit)
            return self._decode_sub8_imm(addr, hw, raw)

        # Data processing (bits [15:10] = 010000)
        elif (hw >> 10) == 0b010000:
            return self._decode_data_proc(addr, hw, raw)

        # Special data processing and branch/exchange (bits [15:10] = 010001)
        elif (hw >> 10) == 0b010001:
            return self._decode_special_proc(addr, hw, raw)

        # LDR (literal) (bits [15:11] = 01001)
        elif op == 0b01001:
            return self._decode_ldr_lit(addr, hw, raw)

        # Load/store register offset (bits [15:12] = 0101)
        elif (hw >> 12) == 0b0101:
            return self._decode_ldst_reg(addr, hw, raw)

        # Load/store word immediate (bits [15:13] = 011)
        elif (hw >> 13) == 0b011:
            return self._decode_ldst_word(addr, hw, raw)

        # Load/store halfword immediate (bits [15:13] = 100)
        elif (hw >> 13) == 0b100:
            return self._decode_ldst_half(addr, hw, raw)

        # Load/store sp-relative (bits [15:13] = 1001)
        elif (hw >> 13) == 0b1001:
            return self._decode_ldst_sp(addr, hw, raw)

        # Load address (bits [15:12] = 1010)
        elif (hw >> 12) == 0b1010:
            return self._decode_load_addr(addr, hw, raw)

        # Miscellaneous (bits [15:12] = 1011)
        elif (hw >> 12) == 0b1011:
            return self._decode_misc(addr, hw, raw)

        # Conditional branch (bits [15:12] = 1101)
        elif (hw >> 12) == 0b1101:
            return self._decode_cond_branch(addr, hw, raw)

        # Unconditional branch (bits [15:11] = 11100)
        elif (hw >> 11) == 0b11100:
            return self._decode_uncond_branch(addr, hw, raw)

        return self._unknown(addr, raw)

    # ----- 16-bit instruction decoding -----

    def _decode_lsl_imm(self, addr, hw, raw):
        imm5 = (hw >> 6) & 0x1F
        rm = (hw >> 3) & 0x7
        rd = hw & 0x7
        return Instruction(addr, raw, "LSLS", f"R{rd}, R{rm}, #{imm5}",
                          InstructionType.LSL, rd=rd, rm=rm, imm=imm5)

    def _decode_lsr_imm(self, addr, hw, raw):
        imm5 = (hw >> 6) & 0x1F
        rm = (hw >> 3) & 0x7
        rd = hw & 0x7
        return Instruction(addr, raw, "LSRS", f"R{rd}, R{rm}, #{imm5}",
                          InstructionType.LSR, rd=rd, rm=rm, imm=imm5)

    def _decode_asr_imm(self, addr, hw, raw):
        imm5 = (hw >> 6) & 0x1F
        rm = (hw >> 3) & 0x7
        rd = hw & 0x7
        return Instruction(addr, raw, "ASRS", f"R{rd}, R{rm}, #{imm5}",
                          InstructionType.ASR, rd=rd, rm=rm, imm=imm5)

    def _decode_add_sub(self, addr, hw, raw):
        op = (hw >> 9) & 0x3
        imm3 = (hw >> 6) & 0x7
        rn = (hw >> 3) & 0x7
        rd = hw & 0x7

        if op == 0:  # ADD register
            return Instruction(addr, raw, "ADDS", f"R{rd}, R{rn}, R{imm3}",
                              InstructionType.ADD, rd=rd, rn=rn, rm=imm3)
        elif op == 1:  # SUB register
            return Instruction(addr, raw, "SUBS", f"R{rd}, R{rn}, R{imm3}",
                              InstructionType.SUB, rd=rd, rn=rn, rm=imm3)
        elif op == 2:  # ADD 3-bit immediate
            return Instruction(addr, raw, "ADDS", f"R{rd}, R{rn}, #{imm3}",
                              InstructionType.ADD, rd=rd, rn=rn, imm=imm3)
        else:  # SUB 3-bit immediate
            return Instruction(addr, raw, "SUBS", f"R{rd}, R{rn}, #{imm3}",
                              InstructionType.SUB, rd=rd, rn=rn, imm=imm3)

    def _decode_mov_imm(self, addr, hw, raw):
        rd = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        return Instruction(addr, raw, "MOVS", f"R{rd}, #0x{imm8:02X}",
                          InstructionType.MOVS, rd=rd, imm=imm8)

    def _decode_cmp_imm(self, addr, hw, raw):
        rn = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        return Instruction(addr, raw, "CMP", f"R{rn}, #0x{imm8:02X}",
                          InstructionType.CMP, rn=rn, imm=imm8)

    def _decode_add8_imm(self, addr, hw, raw):
        rdn = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        return Instruction(addr, raw, "ADDS", f"R{rdn}, #{imm8}",
                          InstructionType.ADD, rd=rdn, imm=imm8)

    def _decode_sub8_imm(self, addr, hw, raw):
        rdn = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        return Instruction(addr, raw, "SUBS", f"R{rdn}, #{imm8}",
                          InstructionType.SUB, rd=rdn, imm=imm8)

    def _decode_data_proc(self, addr, hw, raw):
        op = (hw >> 6) & 0xF
        rm = (hw >> 3) & 0x7
        rdn = hw & 0x7

        ops = ["ANDS", "EORS", "LSLS", "LSRS", "ASRS", "ADCS", "SBCS", "RORS",
               "TST", "RSBS", "CMP", "CMN", "ORRS", "MULS", "BICS", "MVNS"]

        mnem = ops[op]
        itype = {
            "ANDS": InstructionType.AND, "EORS": InstructionType.EOR,
            "LSLS": InstructionType.LSL, "LSRS": InstructionType.LSR,
            "ASRS": InstructionType.ASR, "ADCS": InstructionType.ADC,
            "SBCS": InstructionType.SBC, "RORS": InstructionType.ROR,
            "TST": InstructionType.TST, "RSBS": InstructionType.RSB,
            "CMP": InstructionType.CMP, "CMN": InstructionType.CMP,
            "ORRS": InstructionType.ORR, "BICS": InstructionType.AND,
            "MVNS": InstructionType.MVN
        }.get(mnem, InstructionType.UNKNOWN)

        if mnem in ["TST", "CMP", "CMN"]:
            return Instruction(addr, raw, mnem, f"R{rdn}, R{rm}", itype, rn=rdn, rm=rm)
        elif mnem == "MVNS":
            return Instruction(addr, raw, mnem, f"R{rdn}, R{rm}", itype, rd=rdn, rm=rm)
        else:
            return Instruction(addr, raw, mnem, f"R{rdn}, R{rm}", itype, rd=rdn, rm=rm)

    def _decode_special_proc(self, addr, hw, raw):
        op = (hw >> 8) & 0x3  # Note: op is 2 bits, not 3 bits
        d = (hw >> 7) & 0x1
        rm = (hw >> 3) & 0xF  # Rm is 4 bits
        rdn = (d << 4) | (hw & 0x7)

        if op == 0:  # ADD high registers
            return Instruction(addr, raw, "ADD", f"R{rdn}, R{rm}",
                              InstructionType.ADD, rd=rdn, rm=rm)
        elif op == 1:  # CMP high registers
            return Instruction(addr, raw, "CMP", f"R{rdn}, R{rm}",
                              InstructionType.CMP, rn=rdn, rm=rm)
        elif op == 2:  # MOV high registers
            return Instruction(addr, raw, "MOV", f"R{rdn}, R{rm}",
                              InstructionType.MOVS, rd=rdn, rm=rm)
        elif op == 3:  # BX / BLX
            if d:
                return Instruction(addr, raw, "BLX", f"R{rm}",
                                  InstructionType.BX, rm=rm, branch_target=0)
            else:
                if rm == 14:  # BX LR
                    return Instruction(addr, raw, "BX", "LR", InstructionType.BX, rm=14)
                return Instruction(addr, raw, "BX", f"R{rm}", InstructionType.BX, rm=rm)

        return self._unknown(addr, raw)

    def _decode_ldr_lit(self, addr, hw, raw):
        rt = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        pc_aligned = (addr + 4) & ~3
        target = pc_aligned + imm8 * 4
        return Instruction(addr, raw, "LDR", f"R{rt}, [PC, #{imm8*4}]",
                          InstructionType.LDR, rd=rt, imm=target)

    def _decode_ldst_reg(self, addr, hw, raw):
        rm = (hw >> 6) & 0x7
        rn = (hw >> 3) & 0x7
        rt = hw & 0x7
        opA = (hw >> 9) & 0x7

        ops = ["STR", "STRH", "STRB", "LDRSB", "LDR", "LDRH", "LDRB", "LDRSH"]
        mnem = ops[opA]

        if "STR" in mnem:
            return Instruction(addr, raw, mnem, f"R{rt}, [R{rn}, R{rm}]",
                              InstructionType.STRH, rd=rt, rn=rn, rm=rm)
        else:
            return Instruction(addr, raw, mnem, f"R{rt}, [R{rn}, R{rm}]",
                              InstructionType.LDR, rd=rt, rn=rn, rm=rm)

    def _decode_ldst_word(self, addr, hw, raw):
        b = (hw >> 12) & 0x1
        l = (hw >> 11) & 0x1
        imm5 = (hw >> 6) & 0x1F
        rn = (hw >> 3) & 0x7
        rt = hw & 0x7

        offset = imm5 * 4 if not b else imm5
        mnem = ("LDR" if l else "STR") + ("B" if b else "")

        return Instruction(addr, raw, mnem, f"R{rt}, [R{rn}, #{offset}]",
                          InstructionType.LDR if l else InstructionType.STRH,
                          rd=rt, rn=rn, imm=offset)

    def _decode_ldst_half(self, addr, hw, raw):
        l = (hw >> 11) & 0x1
        imm5 = (hw >> 6) & 0x1F
        rn = (hw >> 3) & 0x7
        rt = hw & 0x7
        offset = imm5 * 2

        mnem = "LDRH" if l else "STRH"
        return Instruction(addr, raw, mnem, f"R{rt}, [R{rn}, #{offset}]",
                          InstructionType.STRH if not l else InstructionType.LDR,
                          rd=rt, rn=rn, imm=offset)

    def _decode_ldst_sp(self, addr, hw, raw):
        l = (hw >> 11) & 0x1
        rt = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        offset = imm8 * 4

        mnem = "LDR" if l else "STR"
        return Instruction(addr, raw, mnem, f"R{rt}, [SP, #{offset}]",
                          InstructionType.LDR if l else InstructionType.STRH,
                          rd=rt, imm=offset)

    def _decode_load_addr(self, addr, hw, raw):
        sp = (hw >> 11) & 0x1
        rd = (hw >> 8) & 0x7
        imm8 = hw & 0xFF
        offset = imm8 * 4

        base = "SP" if sp else "PC"
        return Instruction(addr, raw, "ADR", f"R{rd}, {base}+{offset}",
                          InstructionType.ADD, rd=rd, imm=offset)

    def _decode_misc(self, addr, hw, raw):
        op = (hw >> 8) & 0xF

        if op == 0:  # Add/SUB SP immediate
            s = (hw >> 7) & 0x1
            imm7 = hw & 0x7F
            offset = imm7 * 4
            mnem = "SUB" if s else "ADD"
            return Instruction(addr, raw, mnem, f"SP, #{offset}",
                              InstructionType.ADD, imm=offset)

        elif (hw & 0xFE00) == 0xB400:  # PUSH {registers} or PUSH {registers, LR}
            m = (hw >> 8) & 0x1
            reg_list = []
            for i in range(8):
                if hw & (1 << i):
                    reg_list.append(f"R{i}")
            if m:
                reg_list.append("LR")
            return Instruction(addr, raw, "PUSH", "{" + ", ".join(reg_list) + "}",
                              InstructionType.PUSH, imm=m)

        elif (hw & 0xFE00) == 0xBC00:  # POP {registers} or POP {registers, PC}
            p = (hw >> 8) & 0x1
            reg_list = []
            for i in range(8):
                if hw & (1 << i):
                    reg_list.append(f"R{i}")
            if p:
                reg_list.append("PC")
            return Instruction(addr, raw, "POP", "{" + ", ".join(reg_list) + "}",
                              InstructionType.POP, imm=p)

        elif (hw & 0xFF00) == 0xBE00:  # BKPT
            return Instruction(addr, raw, "BKPT", f"#{hw & 0xFF}", InstructionType.NOP)

        elif (hw & 0xFF00) == 0xBF00:  # IT / hints
            firstcond = (hw >> 4) & 0xF
            mask = hw & 0xF

            if mask == 0:
                # Hint instructions
                hints = {0: "NOP", 1: "YIELD", 2: "WFE", 3: "WFI", 4: "SEV"}
                hint = hints.get(firstcond, "???")
                return Instruction(addr, raw, hint, "", InstructionType.NOP)
            else:
                cond_name = self.COND_NAMES.get(firstcond, "?")
                return Instruction(addr, raw, "IT", cond_name,
                                  InstructionType.IT, cond=firstcond, it_mask=mask)

        elif (hw & 0xF500) == 0xB100:  # CBZ / CBNZ
            rn = hw & 0x7
            offset = ((hw >> 3) & 0x1F) * 2 + 4
            is_cbz = not (hw & 0x800)
            mnem = "CBZ" if is_cbz else "CBNZ"
            target = addr + offset
            itype = InstructionType.CBZ if is_cbz else InstructionType.CBNZ
            return Instruction(addr, raw, mnem, f"R{rn}, 0x{target:05X}",
                              itype, rn=rn, branch_target=target)

        return self._unknown(addr, raw)

    def _decode_cond_branch(self, addr, hw, raw):
        cond = (hw >> 8) & 0xF
        imm8 = hw & 0xFF

        if cond == 14:  # UDF
            return Instruction(addr, raw, "UDF", f"#{imm8}", InstructionType.NOP)

        if cond == 15:  # SVC
            return Instruction(addr, raw, "SVC", f"#{imm8}", InstructionType.NOP)

        # Conditional branch
        if imm8 & 0x80:
            imm8 = imm8 - 256
        target = addr + imm8 * 2 + 4

        cond_name = self.COND_NAMES.get(cond, "?")
        mnem = f"B{cond_name}"

        if cond == 0:
            itype = InstructionType.BEQ
        elif cond == 1:
            itype = InstructionType.BNE
        else:
            itype = InstructionType.B

        return Instruction(addr, raw, mnem, f"0x{target:05X}",
                          itype, cond=cond, branch_target=target)

    def _decode_uncond_branch(self, addr, hw, raw):
        imm11 = hw & 0x7FF
        if imm11 & 0x400:
            imm11 = imm11 - 2048
        target = addr + imm11 * 2 + 4
        return Instruction(addr, raw, "B", f"0x{target:05X}",
                          InstructionType.B, branch_target=target)

    # ----- 32-bit instruction decoding -----

    def _decode_32bit(self, addr: int, hw1: int, hw2: int) -> Instruction:
        """Decode 32-bit Thumb instruction"""
        raw = bytes([hw1 & 0xFF, hw1 >> 8, hw2 & 0xFF, hw2 >> 8])

        # PUSH.W / STMDB (Store Multiple Decrement Before)
        # Encoding: 1110 1001 001M 0Rdn | register_list
        # Where M=1 means includes LR, Rdn is usually SP (1101=13)
        if (hw1 & 0xFF00) == 0xE900:  # STMDB / PUSH.W
            return self._decode_stmdb(addr, hw1, hw2, raw)

        # MOVW / MOVT
        if (hw1 & 0xFBF0) == 0xF240:  # MOVW
            return self._decode_movw(addr, hw1, hw2, raw)

        if (hw1 & 0xFBF0) == 0xF2C0:  # MOVT
            return self._decode_movt(addr, hw1, hw2, raw)

        # MOV immediate
        if (hw1 & 0xFBF0) == 0xF04F:  # MOV.W Rd, #modimm
            return self._decode_mov_w(addr, hw1, hw2, raw)

        # CMP immediate
        if (hw1 & 0xFBF0) == 0xF1B0:  # CMP.W Rn, #modimm
            return self._decode_cmp_w(addr, hw1, hw2, raw)

        # LDRB (literal)
        if hw1 == 0xF890:
            return self._decode_ldrb_lit(addr, hw1, hw2, raw)

        # STRH.W (register offset)
        if (hw1 & 0xFFF0) in [0xF8A0, 0xF820]:
            return self._decode_strh_w(addr, hw1, hw2, raw)

        # BL
        if (hw1 & 0xF800) == 0xF000:
            if (hw2 & 0xD000) == 0xD000:  # BL
                return self._decode_bl(addr, hw1, hw2, raw)
            elif (hw2 & 0xD000) == 0x8000:  # B
                return self._decode_b32(addr, hw1, hw2, raw)

        # General 32-bit
        return Instruction(addr, raw, "32BIT", f"0x{hw1:04X} 0x{hw2:04X}",
                          InstructionType.UNKNOWN)

    def _decode_stmdb(self, addr, hw1, hw2, raw):
        """Decode STMDB/PUSH.W instruction"""
        m = (hw1 >> 5) & 1  # M bit (LR)
        rn = hw1 & 0xF      # Base register
        reg_list = []
        for i in range(16):
            if hw2 & (1 << i):
                if i == 13:
                    reg_list.append("SP")
                elif i == 14:
                    reg_list.append("LR")
                elif i == 15:
                    reg_list.append("PC")
                else:
                    reg_list.append(f"R{i}")

        if rn == 13:  # SP - This is PUSH
            if m:
                reg_list.append("LR")
            return Instruction(addr, raw, "PUSH.W", "{" + ", ".join(reg_list) + "}",
                              InstructionType.PUSH, imm=1 if "LR" in reg_list else 0)

        return Instruction(addr, raw, "STMDB", f"R{rn}!, {{{', '.join(reg_list)}}}",
                          InstructionType.PUSH)

    def _decode_movw(self, addr, hw1, hw2, raw):
        i = (hw1 >> 10) & 1
        imm4 = hw1 & 0xF
        imm3 = (hw2 >> 12) & 0x7
        rd = (hw2 >> 8) & 0xF
        imm8 = hw2 & 0xFF
        imm16 = (i << 11) | (imm4 << 12) | (imm3 << 8) | imm8

        return Instruction(addr, raw, "MOVW", f"R{rd}, #0x{imm16:04X}",
                          InstructionType.MOVW, rd=rd, imm=imm16)

    def _decode_movt(self, addr, hw1, hw2, raw):
        i = (hw1 >> 10) & 1
        imm4 = hw1 & 0xF
        imm3 = (hw2 >> 12) & 0x7
        rd = (hw2 >> 8) & 0xF
        imm8 = hw2 & 0xFF
        imm16 = (i << 11) | (imm4 << 12) | (imm3 << 8) | imm8

        return Instruction(addr, raw, "MOVT", f"R{rd}, #0x{imm16:04X}",
                          InstructionType.MOVW, rd=rd, imm=imm16 << 16)

    def _decode_mov_w(self, addr, hw1, hw2, raw):
        rd = (hw2 >> 8) & 0xF
        # Simplified handling, only extractImmediate value
        imm = hw2 & 0xFF
        return Instruction(addr, raw, "MOV.W", f"R{rd}, #0x{imm:02X}",
                          InstructionType.MOVS, rd=rd, imm=imm)

    def _decode_cmp_w(self, addr, hw1, hw2, raw):
        rn = hw1 & 0xF
        imm = hw2 & 0xFF
        return Instruction(addr, raw, "CMP.W", f"R{rn}, #0x{imm:02X}",
                          InstructionType.CMP, rn=rn, imm=imm)

    def _decode_ldrb_lit(self, addr, hw1, hw2, raw):
        rt = (hw2 >> 12) & 0xF
        offset = hw2 & 0xFFF
        target = addr + 4 + offset
        return Instruction(addr, raw, "LDRB.W", f"R{rt}, [PC, #{offset}]",
                          InstructionType.LDRB, rd=rt, imm=target)

    def _decode_strh_w(self, addr, hw1, hw2, raw):
        # STRH.W Rt, [Rn, #imm] Encoding: 1111 1000 1010 nnnn | rrrr tttt 1100 iiii
        # Where hw1 = F8An (n = Rn)
        # In hw2, Rt at bits[15:12], imm12 at bits[11:0]
        rn = hw1 & 0xF
        rt = (hw2 >> 12) & 0xF
        offset = hw2 & 0xFFF
        return Instruction(addr, raw, "STRH.W", f"R{rt}, [R{rn}, #{offset}]",
                          InstructionType.STRH_W, rd=rt, rn=rn, imm=offset)

    def _decode_bl(self, addr, hw1, hw2, raw):
        s = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        j1 = (hw2 >> 13) & 1
        j2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF

        i1 = ~(j1 ^ s) & 1
        i2 = ~(j2 ^ s) & 1

        imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
        if s:
            imm32 = imm32 | 0xFE000000

        target = addr + 4 + imm32
        return Instruction(addr, raw, "BL", f"0x{target:05X}",
                          InstructionType.B, branch_target=target)

    def _decode_b32(self, addr, hw1, hw2, raw):
        s = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        j1 = (hw2 >> 13) & 1
        j2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF

        i1 = ~(j1 ^ s) & 1
        i2 = ~(j2 ^ s) & 1

        imm32 = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
        if s:
            imm32 = imm32 | 0xFE000000

        target = addr + 4 + imm32
        return Instruction(addr, raw, "B.W", f"0x{target:05X}",
                          InstructionType.B, branch_target=target)


# ============================================================================
# Theme Function Detector
# ============================================================================

class ThemeFunctionDetector:
    """Detect Theme-Related Functions"""

    def __init__(self, decoder: ThumbDecoder):
        self.decoder = decoder

    def _is_32bit_instruction(self, addr: int) -> bool:
        """Check if instruction is 32-bit"""
        if addr + 2 > len(self.decoder.data):
            return False
        hw = self.decoder.read16(addr)
        return (hw & 0xF800) in [0xE800, 0xF000, 0xF800]

    def scan_firmware(self, max_scan_size: int = 0x100000) -> List[ThemeFunction]:
        """Scan firmware for Theme-Related Functions"""
        functions = []
        data = self.decoder.data

        # Limit scan range (code section usually in first 1MB)
        original_size = len(data)
        if len(data) > max_scan_size:
            self.decoder.data = data[:max_scan_size]

        # For deduplication
        seen_func_addrs = set()

        # Method 1: Search for preload+conditional store pattern (most accurate)
        # Feature: Multiple consecutive MOVW loading colors, then CMP + conditional branch
        for func in self._find_preload_store_patterns():
            if func.addr not in seen_func_addrs:
                seen_func_addrs.add(func.addr)
                functions.append(func)

        # Method 2: Search for switch-case pattern
        # Feature: Multiple CMP R0, #N + BEQ/BNE sequences
        for func in self._find_switch_case_patterns():
            if func.addr not in seen_func_addrs:
                seen_func_addrs.add(func.addr)
                functions.append(func)

        # Method 3: Search for ITE pattern
        # Feature: IT instruction + conditional MOVW
        for func in self._find_ite_patterns():
            if func.addr not in seen_func_addrs:
                seen_func_addrs.add(func.addr)
                functions.append(func)

        # Restore original data
        self.decoder.data = data

        return functions

    def _find_preload_store_patterns(self) -> List[ThemeFunction]:
        """Find preload+conditional store pattern"""
        functions = []
        data = self.decoder.data

        # Fast scan: Search for MOVW instruction byte patterns
        # MOVW Rd, #imm16 Encoding: 11110 i 0 00100 imm4 | 0 imm3 Rd imm8
        # First byte is usually 0xF2 or 0xF6
        movw_candidates = []

        for i in range(0, len(data) - 8, 2):
            hw = data[i] | (data[i+1] << 8)
            if (hw & 0xFBF0) == 0xF240:  # MOVW prefix
                movw_candidates.append(i)

        # Analyze candidate addresses
        seen_addrs = set()
        for i in movw_candidates:
            instr = self.decoder.decode(i)

            if instr.instr_type == InstructionType.MOVW:
                # Check if consecutive MOVW sequence
                movw_sequence = self._collect_movw_sequence(i)

                if len(movw_sequence) >= 2:
                    # Check if followed by CMP + conditional branch
                    next_addr = movw_sequence[-1].addr + 4
                    if self._has_conditional_structure(next_addr):
                        # Find function start
                        func_start = self._find_function_start(i)
                        if func_start is not None and func_start not in seen_addrs:
                            seen_addrs.add(func_start)
                            # Find function end
                            func_end = self._find_function_end(func_start)
                            func = ThemeFunction(
                                addr=func_start,
                                end_addr=func_end,
                                pattern_type="preload_store"
                            )
                            func.preload_colors = {m.rd: m.imm for m in movw_sequence}
                            functions.append(func)

        return functions

    def _find_switch_case_patterns(self) -> List[ThemeFunction]:
        """Find switch-case pattern"""
        functions = []
        data = self.decoder.data

        # Fast scan: Search for CMP R0, #N byte patterns
        # CMP R0, #imm8 Encoding: 00101 Rn imm8 (bits[15:11] = 00101)
        cmp_candidates = []

        for i in range(0, len(data) - 6, 2):
            hw = data[i] | (data[i+1] << 8)

            # 16-bit CMP Rd, #imm8 Encoding: 00101 Rn imm8 (bits[15:11] = 00101)
            if (hw >> 11) == 0b00101:
                rd = (hw >> 8) & 0x7
                imm = hw & 0xFF
                if rd == 0 and imm < 10:  # CMP R0, #0-9
                    cmp_candidates.append((i, imm))

            # 32-bit CMP.W R0, #imm Encoding: F1BC 0Fxx (where xx isImmediate value)
            elif hw == 0xF1BC:
                hw2 = data[i+2] | (data[i+3] << 8)
                if (hw2 & 0xFF00) == 0x0F00:  # CMP.W R0, #imm
                    imm = hw2 & 0xFF
                    if imm < 10:
                        cmp_candidates.append((i, imm))

        # Analyze consecutive CMP sequences
        seen_addrs = set()
        i = 0
        while i < len(cmp_candidates):
            # Collect consecutive CMPs
            consecutive = [cmp_candidates[i]]
            j = i + 1
            while j < len(cmp_candidates):
                if cmp_candidates[j][0] - cmp_candidates[j-1][0] <= 20:  # Allow other instructions in between
                    consecutive.append(cmp_candidates[j])
                    j += 1
                else:
                    break

            if len(consecutive) >= 3:
                # Check for differentImmediate value (0, 1, 2, 3, 4)
                imms = set(c[1] for c in consecutive)
                if len(imms) >= 3:
                    func_start = self._find_function_start(consecutive[0][0])
                    if func_start and func_start not in seen_addrs:
                        seen_addrs.add(func_start)

                        # Collect MOVW color values in function
                        # Use CMP sequence position as base, not function start
                        cmp_start = consecutive[0][0]
                        func_end = consecutive[-1][0] + 100
                        color_values = {}
                        addr = cmp_start  # Collect from CMP sequence start position
                        while addr < func_end:
                            if addr + 4 > len(data):
                                break
                            hw = data[addr] | (data[addr+1] << 8)

                            # Check if MOVW (32-bit)
                            if (hw & 0xFBF0) == 0xF240:
                                hw2 = data[addr+2] | (data[addr+3] << 8)
                                imm4 = hw & 0xF
                                i_bit = (hw >> 10) & 1
                                imm3 = (hw2 >> 12) & 0x7
                                rd = (hw2 >> 8) & 0xF
                                imm8 = hw2 & 0xFF
                                imm16 = (i_bit << 11) | (imm4 << 12) | (imm3 << 8) | imm8
                                color_values[len(color_values)] = imm16
                                addr += 4
                                continue

                            # Move to next instruction
                            if self._is_32bit_instruction(addr):
                                addr += 4
                            else:
                                addr += 2

                        func = ThemeFunction(
                            addr=func_start,
                            end_addr=func_end,
                            pattern_type="switch_case"
                        )
                        func.preload_colors = color_values
                        functions.append(func)

            i = j if j > i + 1 else i + 1

        return functions

    def _find_ite_patterns(self) -> List[ThemeFunction]:
        """Find ITE conditional execution pattern"""
        functions = []
        data = self.decoder.data

        # Fast scan: Search for IT instruction byte patterns
        # IT instructionEncoding: 1011 1111 firstcond mask (BFxx)
        it_candidates = []

        for i in range(0, len(data) - 40, 2):
            hw = data[i] | (data[i+1] << 8)
            if (hw & 0xFF00) == 0xBF00:  # IT instruction
                firstcond = (hw >> 4) & 0xF
                mask = hw & 0xF
                if mask != 0:  # Not NOP or hint instructions
                    it_candidates.append(i)

        # Analyze candidate addresses
        seen_addrs = set()
        for i in it_candidates:
            instr = self.decoder.decode(i)

            if instr.instr_type == InstructionType.IT:
                # Check if MOVW (color load) exists in IT block
                # Note: MOVW is 32-bit instruction, need to check more space
                has_color_movw = False
                it_size = self._get_it_block_size(instr.it_mask)
                color_values = []

                addr = i + 2
                for j in range(it_size * 2):  # each instruction max 4 bytes
                    if addr + 4 > len(data):
                        break
                    it_instr = self.decoder.decode(addr)
                    if it_instr.instr_type == InstructionType.MOVW:
                        has_color_movw = True
                        color_values.append(it_instr.imm)
                    # Move to next instruction
                    if self._is_32bit_instruction(addr):
                        addr += 4
                    else:
                        addr += 2

                if has_color_movw:
                    func_start = self._find_function_start(i)
                    # If function start not found, use range before IT instruction as function start
                    if func_start is None:
                        func_start = i - 50  # Default 50 bytes before
                    if func_start not in seen_addrs:
                        seen_addrs.add(func_start)
                        func = ThemeFunction(
                            addr=func_start,
                            end_addr=i + 40,
                            pattern_type="ite"
                        )
                        func.preload_colors[0] = color_values[0] if color_values else 0
                        if len(color_values) > 1:
                            func.preload_colors[1] = color_values[1]
                        functions.append(func)

        return functions

    def _collect_movw_sequence(self, start_addr: int) -> List[Instruction]:
        """Collect consecutive MOVW instruction sequence"""
        sequence = []
        addr = start_addr
        max_count = 10

        for _ in range(max_count):
            if addr + 4 > len(self.decoder.data):
                break

            instr = self.decoder.decode(addr)

            if instr.instr_type == InstructionType.MOVW:
                sequence.append(instr)
                addr += 4
            elif instr.instr_type in [InstructionType.MOVS, InstructionType.LDR]:
                # Allow other load instructions in between
                addr += 2 if instr.instr_type == InstructionType.MOVS else 4
            else:
                break

        return sequence

    def _has_conditional_structure(self, addr: int) -> bool:
        """Check for conditional structure after address (CMP + BEQ/BNE/IT)"""
        for offset in range(0, 30, 2):
            instr = self.decoder.decode(addr + offset)
            if instr.instr_type == InstructionType.CMP:
                next_instr = self.decoder.decode(addr + offset + 2)
                if next_instr.instr_type in [InstructionType.BEQ, InstructionType.BNE, InstructionType.IT]:
                    return True
        return False

    def _find_function_start(self, addr: int) -> Optional[int]:
        """Search backward for function start (PUSH instruction)"""
        for offset in range(0, 1000, 2):  # Increase search range to 1000 bytes
            check_addr = addr - offset
            if check_addr < 0:
                break
            instr = self.decoder.decode(check_addr)
            if instr.instr_type == InstructionType.PUSH:
                return check_addr
        return None

    def _find_function_end(self, addr: int, max_search: int = 400) -> int:
        """
        Search forward for function end
        Strategy: Find last POP + BX LR sequence
        """
        search_end = min(addr + max_search, len(self.decoder.data))
        it_block_remaining = 0
        last_pop_bx_addr = 0

        while addr < search_end:
            hw = self.decoder.read16(addr)
            is_32bit = (hw & 0xF800) in [0xE800, 0xF000, 0xF800]
            instr_size = 4 if is_32bit else 2

            # Handle IT block
            if it_block_remaining > 0:
                it_block_remaining -= 1
                addr += instr_size
                continue

            # Check IT instruction
            if (hw & 0xFF00) == 0xBF00:
                mask = hw & 0xF
                if mask != 0:
                    if mask & 0x1:
                        it_block_remaining = 4
                    elif mask & 0x2:
                        it_block_remaining = 3
                    elif mask & 0x4:
                        it_block_remaining = 2
                    else:
                        it_block_remaining = 1
                addr += instr_size
                continue

            # Check POP + BX LR sequence (outside IT block)
            if (hw & 0xFF00) == 0xBC00:  # POP
                next_addr = addr + 2
                if next_addr + 2 <= len(self.decoder.data):
                    next_hw = self.decoder.read16(next_addr)
                    if next_hw == 0x4770:  # BX LR
                        last_pop_bx_addr = next_addr + 2

            addr += instr_size

        return last_pop_bx_addr if last_pop_bx_addr > 0 else addr

    def _get_it_block_size(self, mask: int) -> int:
        """Get IT block size"""
        if mask == 0:
            return 0
        if mask & 0x1:
            return 4
        elif mask & 0x2:
            return 3
        elif mask & 0x4:
            return 2
        else:
            return 1


# ============================================================================
# Control Flow Simulator
# ============================================================================

class ControlFlowSimulator:
    """Control Flow Simulator"""

    def __init__(self, decoder: ThumbDecoder):
        self.decoder = decoder

    def _is_32bit_instruction(self, addr: int) -> bool:
        """Check if instruction is 32-bit"""
        if addr + 2 > len(self.decoder.data):
            return False
        hw = self.decoder.read16(addr)
        return (hw & 0xF800) in [0xE800, 0xF000, 0xF800]

    def simulate(self, func: ThemeFunction, theme_value: int) -> Tuple[Dict[int, int], List[ColorWrite], List[MovwRecord]]:
        """
        Simulate function execution

        Returns: (Final register state, Color Write Record list, MOVW load record list)
        """
        registers = {i: 0 for i in range(16)}
        registers[0] = theme_value  # R0 = theme value

        # Track which MOVW loaded each register
        register_sources: Dict[int, Optional[MovwRecord]] = {i: None for i in range(16)}

        color_writes = []
        movw_records = []  # Record MOVW instructions
        seen_addrs = set()  # Prevent duplicates
        last_cmp_result = False
        it_block_remaining = 0
        it_conditions = []
        current_theme_condition = None  # Current condition applicable theme

        addr = func.addr
        max_steps = 200
        end_addr = func.end_addr if func.end_addr > 0 else func.addr + 500

        step = 0
        while step < max_steps and addr < end_addr:
            # preventnoneinfinite loop
            if addr in seen_addrs:
                break
            seen_addrs.add(addr)

            instr = self.decoder.decode(addr)
            instr_size = 4 if self._is_32bit_instruction(addr) else 2

            # Handle IT blockinside instruction
            if it_block_remaining > 0:
                cond_idx = len(it_conditions) - it_block_remaining
                if cond_idx < len(it_conditions):
                    should_exec = it_conditions[cond_idx]

                    if should_exec:
                        if instr.instr_type in [InstructionType.STRH, InstructionType.STRH_W]:
                            write = self._handle_strh(instr, registers, theme_value, register_sources)
                            if write:
                                write.theme_condition = current_theme_condition
                                color_writes.append(write)
                        elif instr.instr_type == InstructionType.MOVW:
                            movw = MovwRecord(
                                addr=addr,
                                instr=instr,
                                color_value=instr.imm,
                                target_reg=instr.rd,
                                theme_condition=current_theme_condition
                            )
                            movw_records.append(movw)
                            register_sources[instr.rd] = movw  # record registersource
                            registers[instr.rd] = instr.imm
                        elif instr.instr_type == InstructionType.POP:
                            # POP inside IT block execution，check not containing PC
                            hw = self.decoder.read16(addr)
                            if hw & 0x100:  # POP {..., PC}
                                break  # functionReturns
                        elif instr.instr_type == InstructionType.BX:
                            # BX LR inside IT block execution
                            break  # functionReturns

                it_block_remaining -= 1
                addr += instr_size
                step += 1
                continue

            # Handle normal instructions
            if instr.instr_type == InstructionType.PUSH:
                pass  # ignore

            elif instr.instr_type == InstructionType.POP:
                pass  # ignore

            elif instr.instr_type == InstructionType.BX:
                break  # functionReturns

            elif instr.instr_type == InstructionType.MOVW:
                # Record MOVW instructions
                movw = MovwRecord(
                    addr=addr,
                    instr=instr,
                    color_value=instr.imm,
                    target_reg=instr.rd,
                    theme_condition=current_theme_condition
                )
                movw_records.append(movw)
                register_sources[instr.rd] = movw  # record registersource
                registers[instr.rd] = instr.imm

            elif instr.instr_type == InstructionType.MOVS:
                registers[instr.rd] = instr.imm

            elif instr.instr_type == InstructionType.CMP:
                if 0 <= instr.rn < 16:
                    last_cmp_result = (registers[instr.rn] == instr.imm)

            elif instr.instr_type == InstructionType.BEQ:
                if last_cmp_result:
                    addr = instr.branch_target
                    step += 1
                    continue

            elif instr.instr_type == InstructionType.BNE:
                if not last_cmp_result:
                    addr = instr.branch_target
                    step += 1
                    continue

            elif instr.instr_type == InstructionType.B:
                addr = instr.branch_target
                step += 1
                continue

            elif instr.instr_type == InstructionType.CBZ:
                if registers[instr.rn] == 0:
                    addr = instr.branch_target
                    step += 1
                    continue

            elif instr.instr_type == InstructionType.CBNZ:
                if registers[instr.rn] != 0:
                    addr = instr.branch_target
                    step += 1
                    continue

            elif instr.instr_type == InstructionType.IT:
                it_block_remaining, it_conditions = self._setup_it_block(
                    instr, last_cmp_result
                )

            elif instr.instr_type in [InstructionType.STRH, InstructionType.STRH_W]:
                write = self._handle_strh(instr, registers, theme_value, register_sources)
                if write:
                    color_writes.append(write)

            # Move to next instruction
            addr += instr_size
            step += 1

        return registers, color_writes, movw_records

    def _setup_it_block(self, instr: Instruction, cmp_result: bool) -> Tuple[int, List[bool]]:
        """Set IT block execution conditions"""
        mask = instr.it_mask
        firstcond = instr.cond

        # Calculate block size
        if mask & 0x1:
            size = 4
        elif mask & 0x2:
            size = 3
        elif mask & 0x4:
            size = 2
        else:
            size = 1

        # Calculate whether each instruction executes
        conditions = []
        fc_lsb = firstcond & 1

        # No.oneiteminstructionalways uses firstcond
        cond_true = (firstcond == 0 and cmp_result) or (firstcond == 1 and not cmp_result)
        conditions.append(cond_true)

        # aftersubsequent instruction
        for i in range(1, size):
            bit_pos = 4 - i  # mask[3], mask[2], mask[1]
            mask_bit = (mask >> bit_pos) & 1

            if mask_bit == fc_lsb:
                # T - same condition
                conditions.append(cond_true)
            else:
                # E - opposite condition
                conditions.append(not cond_true)

        return size, conditions

    def _handle_strh(self, instr: Instruction, registers: Dict[int, int],
                     theme_value: int, register_sources: Dict[int, Optional['MovwRecord']] = None) -> Optional[ColorWrite]:
        """Handle STRH instruction"""
        rt = instr.rd if instr.rd >= 0 else 0
        rn = instr.rn if instr.rn >= 0 else 0
        color = registers.get(rt, 0)

        # Find MOVW loading this register MOVW instruction
        movw_instr = None
        if register_sources:
            movw_instr = register_sources.get(rt)

        return ColorWrite(
            addr=instr.addr,
            instr=instr,
            color_value=color,
            target_reg=rn,
            source_reg=rt,
            theme_condition=theme_value,
            movw_instr=movw_instr
        )


# ============================================================================
# Report Generator
# ============================================================================

class ReportGenerator:
    """Generate Analysis Report"""

    def __init__(self, firmware_path: str, decoder: Optional['ThumbDecoder'] = None):
        self.firmware_path = firmware_path
        self.decoder = decoder
        self.functions = []
        self.theme_colors = defaultdict(dict)  # theme_id -> {target: color}
        self.patch_info: Optional[PatchInfo] = None

    def set_patch_info(self, patch_info: PatchInfo):
        """Set patch detection info"""
        self.patch_info = patch_info

    def add_function(self, func: ThemeFunction, theme_results: Dict[int, List[ColorWrite]]):
        """Add function analysis result"""
        self.functions.append((func, theme_results))

        # If UI element not identified，identify based on behavior
        if func.ui_element == "unknown" or not func.ui_element:
            func.ui_element = self._identify_ui_element(func, theme_results)

        # Summarize colors for preload_store pattern function（this is menu theme function）
        # Only process first detected preload_store function，avoid mixing data from other functions
        if func.pattern_type == "preload_store" and "Menu Text" in func.ui_element:
            # check if already hasmenusinglecolorfunction
            has_menu = any(
                f.pattern_type == "preload_store" and "Menu Text" in f.ui_element
                for f, _ in self.functions[:-1]  # exclude the just added one
            )
            if not has_menu:
                for theme_id, writes in theme_results.items():
                    for write in writes:
                        # Only collect writes to R1, R2, R3 color（these are main color registers）
                        if write.target_reg in [1, 2, 3]:
                            key = f"R{write.target_reg}"
                            self.theme_colors[theme_id][key] = write.color_value

        # Summarize colors for ITE pattern FLAC function
        if func.pattern_type == "ite" and "FLAC" in func.ui_element:
            # extract FLAC color using behavior analysis
            if self.decoder:
                flac_behavior = self._analyze_flac_behavior(func.addr)
                if flac_behavior['is_flac']:
                    for theme_id in range(5):
                        if theme_id == 4:
                            self.theme_colors[theme_id]["FLAC"] = flac_behavior['color_for_4']
                        else:
                            self.theme_colors[theme_id]["FLAC"] = flac_behavior['color_for_other']

    def _analyze_flac_behavior(self, addr: int, scan_range: int = 100) -> dict:
        """Identify FLAC function using behavior analysis"""
        result = {
            'is_flac': False,
            'color_for_4': 0,
            'color_for_other': 0,
        }

        if not self.decoder:
            return result

        offset = 0
        found_cmp_4 = False
        cmp_4_offset = 0

        # Step 1: Find CMP Rx, #4
        while offset < scan_range:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            if 'CMP' in mn and (instr.imm == 4 or '#4' in ops or '#0x4' in ops):
                found_cmp_4 = True
                cmp_4_offset = offset
                break

            offset += 4 if is_32bit else 2

        if not found_cmp_4:
            return result

        # Step 2: Find two consecutive MOVW after CMP #4
        offset = cmp_4_offset + (4 if self.decoder.read16(addr + cmp_4_offset) >= 0xE800 else 2)

        movw_list = []
        while offset < scan_range and len(movw_list) < 2:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            if 'MOVW' in mn and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    movw_list.append(val)
                except:
                    pass

            offset += 4 if is_32bit else 2

        if len(movw_list) == 2 and movw_list[0] != movw_list[1]:
            result['is_flac'] = True
            result['color_for_4'] = movw_list[0]
            result['color_for_other'] = movw_list[1]

        return result

    def _identify_ui_element(self, func: ThemeFunction, theme_results: Dict[int, List[ColorWrite]]) -> str:
        """Identify UI element corresponding to function（using behavior analysis, no hardcoded color values）"""
        # Get all color values for auxiliary judgment
        all_colors = set()
        for writes in theme_results.values():
            for w in writes:
                all_colors.add(w.color_value)
        for c in func.preload_colors.values():
            all_colors.add(c)

        # For ITE pattern, detect FLAC using behavior analysis
        if func.pattern_type == "ite" and self.decoder:
            flac_behavior = self._analyze_flac_behavior(func.addr)
            if flac_behavior['is_flac']:
                return "FLAC String Text"

        # For switch_case pattern, check FLAC first
        if func.pattern_type == "switch_case" and self.decoder:
            # detect FLAC using context analysis
            from theme_extractor import ThemeDiscovery
            flac_context = ThemeDiscovery.detect_flac_by_context(self.decoder, func.addr)
            if flac_context['is_flac']:
                return "FLAC String Text"

            # then detect progress bar/marquee
            behavior = self._analyze_switch_case_behavior(func.addr)
            if behavior['cmp_r12_count'] >= 5 and behavior['distinct_colors'] == 5:
                if behavior['strh_count'] > 0:
                    return "Progress Bar Background"
                else:
                    return "Marquee/Scrolling Text Overlay"

        # Menu Text Colors (preload_store pattern)
        if func.pattern_type == "preload_store":
            # check if has write to R1, R2, R3
            if any(w.target_reg in [1, 2, 3] for writes in theme_results.values() for w in writes):
                return "Menu Text Colors (Highlight/Normal/Second)"

        return "Unknown UI Element"

    def _analyze_switch_case_behavior(self, addr: int, scan_range: int = 200) -> dict:
        """Analyze switch_case function behavior features"""
        features = {
            'cmp_r12_count': 0,
            'distinct_colors': 0,
            'strh_count': 0,
            'colors': set(),
        }

        if not self.decoder:
            return features

        offset = 0
        colors = []

        while offset < scan_range:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            if mn == 'CMP' and 'R12' in ops:
                imm_val = instr.imm
                if 0 <= imm_val <= 4:
                    features['cmp_r12_count'] += 1

            if 'MOVW' in mn and 'R0' in ops and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    colors.append(val)
                except:
                    pass

            if 'STRH' in mn:
                features['strh_count'] += 1

            offset += 4 if is_32bit else 2

        features['colors'] = set(colors)
        features['distinct_colors'] = len(set(colors))

        return features

    def generate_markdown(self) -> str:
        """Generate Markdown report"""
        lines = []
        lines.append(f"# Theme Color Analysis Report")
        lines.append(f"")
        lines.append(f"**Firmware file**: `{os.path.basename(self.firmware_path)}`")
        lines.append(f"**Analysis time**: {self._get_timestamp()}")
        lines.append(f"")

        # Detected functions
        lines.append(f"## Detected theme functions")
        lines.append(f"")
        lines.append(f"| Address | Pattern | UI Element |")
        lines.append(f"|------|------|---------|")

        for func, _ in self.functions:
            lines.append(f"| 0x{func.addr:05X} | {func.pattern_type} | {func.ui_element} |")

        lines.append(f"")

        # UI Element Color Summary
        lines.append(f"## UI Element Color Summary")
        lines.append(f"")

        if self.theme_colors:
            # Group colors by class
            menu_colors = {}
            flac_colors = {}
            other_colors = {}

            for theme_id, colors in self.theme_colors.items():
                for key, val in colors.items():
                    if key.startswith("R"):
                        if theme_id not in menu_colors:
                            menu_colors[theme_id] = {}
                        menu_colors[theme_id][key] = val
                    elif key == "FLAC":
                        flac_colors[theme_id] = val
                    else:
                        if theme_id not in other_colors:
                            other_colors[theme_id] = {}
                        other_colors[theme_id][key] = val

            # Menu Text Colors
            if menu_colors:
                lines.append(f"### Menu Text Colors")
                lines.append(f"")
                all_targets = sorted(set(
                    k for tc in menu_colors.values() for k in tc.keys()
                ))

                # Add color meaning description
                lines.append(f"**Destination register meaning**:")
                lines.append(f"- R1: Highlight/Foreground color")
                lines.append(f"- R2: Secondary color")
                lines.append(f"- R3: Foreground color")
                lines.append(f"")

                lines.append(f"| theme | " + " | ".join(all_targets) + " |")
                lines.append(f"|------|" + "|".join(["------"] * len(all_targets)) + "|")

                for theme_id in sorted(menu_colors.keys()):
                    colors = menu_colors[theme_id]
                    row = [f"Theme {theme_id}"]
                    for key in all_targets:
                        if key in colors:
                            row.append(f"0x{colors[key]:04X}")
                        else:
                            row.append("-")
                    lines.append(f"| " + " | ".join(row) + " |")
                lines.append(f"")

            # FLAC String colors
            if flac_colors:
                lines.append(f"### FLAC String Text Colors")
                lines.append(f"")
                lines.append(f"| theme | FLAC color |")
                lines.append(f"|------|----------|")
                for theme_id in sorted(flac_colors.keys()):
                    lines.append(f"| Theme {theme_id} | 0x{flac_colors[theme_id]:04X} |")
                lines.append(f"")

        else:
            lines.append(f"*No theme color functions detected. This firmware version may not support theme system.*")

        lines.append(f"")

        # Detailed Instruction Report
        lines.append(f"## Detailed Instruction Report")
        lines.append(f"")

        for func, theme_results in self.functions:
            lines.append(f"### function @ 0x{func.addr:05X} ({func.ui_element})")
            lines.append(f"")
            lines.append(f"**Pattern**: {func.pattern_type}")
            lines.append(f"")

            for theme_id, writes in sorted(theme_results.items()):
                if not writes:
                    continue

                lines.append(f"#### Theme {theme_id}")
                lines.append(f"")
                lines.append(f"| MOVW Address | MOVW instruction | STRH Address | STRH instruction | colorvalue |")
                lines.append(f"|------------|-----------|-----------|-----------|--------|")

                for write in writes:
                    # display MOVW instruction（ifresulthas）
                    if write.movw_instr:
                        movw_str = f"0x{write.movw_instr.addr:05X}: {write.movw_instr.instr.mnemonic} {write.movw_instr.instr.operands}"
                    else:
                        movw_str = "(preload)"
                    strh_str = f"0x{write.addr:05X}: {write.instr.mnemonic} {write.instr.operands}"
                    lines.append(f"| {movw_str.split(':')[0] if ':' in movw_str else movw_str} | {movw_str.split(': ')[1] if ': ' in movw_str else movw_str} | 0x{write.addr:05X} | {write.instr.mnemonic} {write.instr.operands} | 0x{write.color_value:04X} |")

                lines.append(f"")

        return "\n".join(lines)

    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate_html(self, title: str = "Theme Color Analysis Report") -> str:
        """Generate HTML report"""
        from datetime import datetime

        # Convert color value to CSS color
        def color_to_css(val):
            if val == 0 or val == "0x0000":
                return "#000000"
            r = (val >> 11) & 0x1F
            g = (val >> 5) & 0x3F
            b = val & 0x1F
            # 5-6-5 RGB expanded to 8-8-8
            r = (r << 3) | (r >> 2)
            g = (g << 2) | (g >> 4)
            b = (b << 3) | (b >> 2)
            return f"rgb({r},{g},{b})"

        def parse_color(c):
            if isinstance(c, int):
                return c
            if isinstance(c, str) and c.startswith("0x"):
                return int(c, 16)
            return 0

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 0 0 30px rgba(0,212,255,0.3);
        }}
        h2 {{
            font-size: 1.5em;
            margin: 30px 0 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #00d4ff;
            color: #00d4ff;
        }}
        .firmware-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .firmware-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 40px rgba(0,212,255,0.2);
        }}
        .firmware-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .firmware-name {{
            font-size: 1.3em;
            font-weight: bold;
            color: #fff;
        }}
        .firmware-status {{
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        .status-ok {{ background: #00ff8833; color: #00ff88; }}
        .status-no-theme {{ background: #ffaa0033; color: #ffaa00; }}
        .themes-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 15px;
        }}
        .theme-box {{
            background: rgba(0,0,0,0.3);
            border-radius: 12px;
            padding: 15px;
            text-align: center;
        }}
        .theme-name {{
            font-size: 0.9em;
            margin-bottom: 10px;
            color: #888;
        }}
        .color-swatch {{
            width: 60px;
            height: 60px;
            border-radius: 10px;
            margin: 0 auto 8px;
            border: 2px solid rgba(255,255,255,0.2);
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        }}
        .color-value {{
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 0.8em;
            color: #aaa;
        }}
        .color-row {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            margin: 5px 0;
        }}
        .color-label {{
            font-size: 0.7em;
            color: #666;
            width: 40px;
            text-align: right;
        }}
        .addr {{ font-family: monospace; color: #00d4ff; }}
        .mnemonic {{ font-family: monospace; color: #ffaa00; }}
        .no-theme-msg {{
            text-align: center;
            color: #888;
            padding: 30px;
            font-style: italic;
        }}
        .summary-section {{
            background: rgba(0,212,255,0.1);
            border-radius: 16px;
            padding: 25px;
            margin-bottom: 30px;
        }}
        .summary-stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            flex-wrap: wrap;
        }}
        .stat-item {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #00d4ff;
        }}
        .stat-label {{
            color: #888;
            font-size: 0.9em;
        }}
        .ui-element-label {{
            font-size: 0.9em;
            color: #aaa;
            margin-bottom: 10px;
            font-style: italic;
        }}
        footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            color: #666;
            font-size: 0.85em;
        }}
        .patch-banner {{
            background: linear-gradient(135deg, rgba(255, 100, 100, 0.2) 0%, rgba(255, 50, 50, 0.3) 100%);
            border: 2px solid #ff6b6b;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
            display: flex;
            align-items: center;
            gap: 20px;
        }}
        .patch-icon {{
            font-size: 2.5em;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}
        .patch-info {{
            flex: 1;
        }}
        .patch-title {{
            color: #ff6b6b;
            font-size: 1.3em;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .patch-details {{
            color: #ccc;
            font-size: 0.95em;
        }}
        .patch-detail-item {{
            margin: 5px 0;
        }}
        .patch-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            margin-left: 5px;
        }}
        .badge-full {{ background: #ff6b6b; color: white; }}
        .badge-flac {{ background: #ffaa00; color: black; }}
        .badge-menu {{ background: #00aaff; color: white; }}
        .badge-unknown {{ background: #888; color: white; }}
        .confidence-bar {{
            width: 100px;
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            display: inline-block;
            vertical-align: middle;
        }}
        .confidence-fill {{
            height: 100%;
            background: linear-gradient(90deg, #ffaa00, #00ff88);
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 ECHO MINI Theme Color Analysis Report</h1>
"""

        # Add patch status banner if firmware is patched
        if self.patch_info and self.patch_info.is_patched:
            patch_type_labels = {
                "full": ("Full Theme Patch", "badge-full"),
                "flac_only": ("FLAC String Patch", "badge-flac"),
                "menu_only": ("Menu Color Patch", "badge-menu"),
                "unknown": ("Unknown Patch", "badge-unknown"),
            }
            label, badge_class = patch_type_labels.get(
                self.patch_info.patch_type, ("Unknown Patch", "badge-unknown")
            )

            # Format metadata if available
            metadata_html = ""
            if self.patch_info.metadata:
                meta = self.patch_info.metadata
                version = meta.get('version', 'Unknown')
                timestamp = meta.get('timestamp', 'Unknown')
                metadata_html = f"""
                <div class="patch-detail-item">
                    <strong>Patch version:</strong> {version} |
                    <strong>Applied:</strong> {timestamp}
                </div>"""

            html += f"""
        <div class="patch-banner">
            <div class="patch-icon">⚠️</div>
            <div class="patch-info">
                <div class="patch-title">
                    Firmware Has Been Patched!
                    <span class="patch-badge {badge_class}">{label}</span>
                </div>
                <div class="patch-details">
                    <div class="patch-detail-item">
                        <strong>Patch target:</strong> 0x{self.patch_info.patch_target_addr:05X}
                    </div>
                    <div class="patch-detail-item">
                        <strong>FLAC patched:</strong> {'✅ Yes' if self.patch_info.flac_patched else '❌ No'} |
                        <strong>Menu patched:</strong> {'✅ Yes' if self.patch_info.menu_patched else '❌ No'} |
                        <strong>NOP has code:</strong> {'✅ Yes' if self.patch_info.nop_has_code else '❌ No'}
                    </div>
                    <div class="patch-detail-item">
                        <strong>Confidence:</strong>
                        <span class="confidence-bar">
                            <span class="confidence-fill" style="width: {self.patch_info.confidence * 100:.0f}%"></span>
                        </span>
                        {self.patch_info.confidence * 100:.0f}%
                    </div>
                    {metadata_html}
                </div>
            </div>
        </div>
"""

        # If has color data, show summary
        if self.theme_colors:
            # Count UI element types
            ui_types = {}
            for func, theme_results in self.functions:
                ui_type = func.ui_element
                if ui_type not in ui_types:
                    ui_types[ui_type] = []
                ui_types[ui_type].append(func.addr)

            html += f"""
        <div class="summary-section">
            <h2>📊 Analysis Summary</h2>
            <div class="summary-stats">
                <div class="stat-item">
                    <div class="stat-value">{len(self.theme_colors)}</div>
                    <div class="stat-label">Theme count</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{len([f for f in self.functions if f[0].pattern_type == 'preload_store'])}</div>
                    <div class="stat-label">Theme functions</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{len(ui_types)}</div>
                    <div class="stat-label">UIElementtype</div>
                </div>
            </div>
            <div class="ui-type-breakdown" style="margin-top: 20px;">
                <h3 style="font-size: 1.1em; margin-bottom: 10px; color: #00d4ff;">Detected UI Elementtype:</h3>
                <div style="display: flex; flex-wrap: wrap; gap: 10px;">
"""
            for ui_type, addrs in sorted(ui_types.items()):
                addr_strs = ', '.join(f'0x{a:05X}' for a in addrs[:3])
                if len(addrs) > 3:
                    addr_strs += f' (+{len(addrs)-3} more)'
                html += f"""
                    <div style="background: rgba(255,255,255,0.1); padding: 8px 15px; border-radius: 8px; font-size: 0.9em;">
                        <span style="color: #00ff88;">●</span> {ui_type}
                        <span style="color: #888; font-size: 0.85em;">({len(addrs)} functions)</span>
                    </div>
"""
            html += """
                </div>
            </div>
        </div>
"""

        html += f"""
        <h2>📁 Firmware Analysis Results</h2>
"""

        for func, theme_results in self.functions:
            has_colors = any(writes for writes in theme_results.values())

            html += f"""
        <div class="firmware-card">
            <div class="firmware-header">
                <span class="firmware-name">function @ 0x{func.addr:05X}</span>
                <span class="firmware-status status-{'ok' if has_colors else 'no-theme'}">{'Analyzed' if has_colors else 'No color data'}</span>
            </div>
"""

            if func.pattern_type == "preload_store" and theme_results:
                html += f"""
            <div class="ui-element-label">{func.ui_element}</div>
            <div class="themes-grid">
"""
                for theme_id in range(5):
                    writes = theme_results.get(theme_id, [])
                    colors = {}
                    for w in writes:
                        colors[w.target_reg] = w.color_value

                    r1 = colors.get(1, 0)
                    r2 = colors.get(2, 0)
                    r3 = colors.get(3, 0)

                    html += f"""
                <div class="theme-box">
                    <div class="theme-name">Theme {theme_id}</div>
                    <div class="color-row">
                        <span class="color-label">R1</span>
                        <div class="color-swatch" style="background:{color_to_css(r1)}" title="0x{r1:04X}"></div>
                    </div>
                    <div class="color-value">0x{r1:04X}</div>
                    <div class="color-row">
                        <span class="color-label">R2</span>
                        <div class="color-swatch" style="background:{color_to_css(r2)}" title="0x{r2:04X}"></div>
                    </div>
                    <div class="color-value">0x{r2:04X}</div>
                    <div class="color-row">
                        <span class="color-label">R3</span>
                        <div class="color-swatch" style="background:{color_to_css(r3)}" title="0x{r3:04X}"></div>
                    </div>
                    <div class="color-value">0x{r3:04X}</div>
                </div>
"""
                html += """
            </div>
        </div>
"""
            elif func.pattern_type == "ite" and "FLAC" in func.ui_element:
                # FLAC String function
                flac_behavior = self._analyze_flac_behavior(func.addr)
                if flac_behavior['is_flac']:
                    html += f"""
            <div class="ui-element-label">{func.ui_element}</div>
            <div class="themes-grid">
"""
                    for theme_id in range(5):
                        if theme_id == 4:
                            color = flac_behavior['color_for_4']
                        else:
                            color = flac_behavior['color_for_other']
                        html += f"""
                <div class="theme-box">
                    <div class="theme-name">Theme {theme_id}</div>
                    <div class="color-swatch" style="background:{color_to_css(color)}" title="0x{color:04X}"></div>
                    <div class="color-value">0x{color:04X}</div>
                </div>
"""
                    html += """
            </div>
        </div>
"""

            elif func.pattern_type == "switch_case" and "FLAC" in func.ui_element:
                # FLAC String function (switch_case Pattern)
                # get colors using context detection
                from theme_extractor import ThemeDiscovery
                flac_context = ThemeDiscovery.detect_flac_by_context(self.decoder, func.addr)
                if flac_context['is_flac']:
                    html += f"""
            <div class="ui-element-label">{func.ui_element}</div>
            <div class="themes-grid">
"""
                    for theme_id in range(5):
                        if theme_id == 4:
                            color = flac_context['color_for_4']
                        else:
                            color = flac_context['color_for_other']
                        html += f"""
                <div class="theme-box">
                    <div class="theme-name">Theme {theme_id}</div>
                    <div class="color-swatch" style="background:{color_to_css(color)}" title="0x{color:04X}"></div>
                    <div class="color-value">0x{color:04X}</div>
                </div>
"""
                    html += """
            </div>
        </div>
"""

            elif func.pattern_type == "switch_case" and ("Progress" in func.ui_element or "Marquee" in func.ui_element):
                # Progress Bar Background or Marquee function
                html += f"""
            <div class="ui-element-label">{func.ui_element}</div>
            <div class="themes-grid">
"""
                # Get colors from preload_colors
                colors_list = list(func.preload_colors.values())
                for theme_id in range(min(5, len(colors_list))):
                    color = colors_list[theme_id] if theme_id < len(colors_list) else 0
                    html += f"""
                <div class="theme-box">
                    <div class="theme-name">Theme {theme_id}</div>
                    <div class="color-swatch" style="background:{color_to_css(color)}" title="0x{color:04X}"></div>
                    <div class="color-value">0x{color:04X}</div>
                </div>
"""
                html += """
            </div>
        </div>
"""

        html += f"""
        <footer>
            Generated at: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
            Tool: theme_extractor.py
        </footer>
    </div>
</body>
</html>
"""
        return html


class BatchAnalyzer:
    """Batch analyze multiple firmware versions"""

    def __init__(self, firmwares_dir: str):
        self.firmwares_dir = firmwares_dir

    def _analyze_theme_function_behavior(self, decoder: 'ThumbDecoder', addr: int, scan_range: int = 200) -> dict:
        """
        Analyze function behavior features to identify theme color functions

        Returns:
        - cmp_r12_count: Count of CMP R12, #0-4
        - distinct_colors: Count of distinct MOVW R0 color values
        - strh_count: STRH instructioncount
        - colors: Specific color value list
        """
        features = {
            'cmp_r12_count': 0,
            'distinct_colors': 0,
            'strh_count': 0,
            'colors': set(),
        }

        offset = 0
        while offset < scan_range:
            hw = decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # Count CMP R12, #0-4
            if 'CMP' in mn and 'R12' in ops:
                for i in range(5):
                    if f', #{i}' in ops or f', #0x0{i}' in ops:
                        features['cmp_r12_count'] += 1
                        break

            # Count MOVW R0 color values
            if 'MOVW' in mn and ('R0' in ops or 'R0,' in ops):
                if '#' in ops:
                    try:
                        val_str = ops.split('#')[1].split()[0].rstrip('}')
                        val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                        features['colors'].add(val)
                    except:
                        pass

            # Count STRH
            if 'STRH' in mn:
                features['strh_count'] += 1

            offset += 4 if is_32bit else 2

        features['distinct_colors'] = len(features['colors'])
        return features

    def _analyze_flac_function_behavior(self, decoder: 'ThumbDecoder', addr: int, scan_range: int = 100) -> dict:
        """
        Analyze FLAC String function behavior features

        FLAC function features:
        - CMP Rx, #4 (compare if theme value is 4)
        - twoconsecutive MOVW instruction (ITE conditional execution)
        - First MOVW is Theme 4 color
        - Second MOVW is other themes color

        Returns:
        - is_flac: notis FLAC function
        - color_for_4: Theme 4 color
        - color_for_other: other themes color
        - movw_addr_4, movw_instr_4: Theme 4  MOVW instructioninfo
        - movw_addr_other, movw_instr_other: othertheme MOVW instructioninfo
        """
        result = {
            'is_flac': False,
            'color_for_4': 0,
            'color_for_other': 0,
            'movw_addr_4': '',
            'movw_instr_4': '',
            'movw_addr_other': '',
            'movw_instr_other': '',
        }

        offset = 0
        found_cmp_4 = False
        cmp_4_offset = 0

        # Step 1: Find CMP Rx, #4
        while offset < scan_range:
            hw = decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # find CMP Rx, #4 (anywhatregister)
            # checkcheck instr.imm == 4 oreroperationasfunctionstringpackagecontain #4 or #0x4
            if 'CMP' in mn and (instr.imm == 4 or '#4' in ops or '#0x4' in ops):
                found_cmp_4 = True
                cmp_4_offset = offset
                break

            offset += 4 if is_32bit else 2

        if not found_cmp_4:
            return result

        # Step 2: Find two consecutive MOVW after CMP #4
        offset = cmp_4_offset + (4 if decoder.read16(addr + cmp_4_offset) >= 0xE800 else 2)

        movw_list = []
        while offset < scan_range and len(movw_list) < 2:
            hw = decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            if 'MOVW' in mn and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    movw_list.append({
                        'addr': f"0x{addr + offset:05X}",
                        'instr': f"{instr.mnemonic} {instr.operands}",
                        'color': val
                    })
                except:
                    pass

            offset += 4 if is_32bit else 2

        # FLAC feature: CMP #4 followed by two different MOVW
        if len(movw_list) == 2 and movw_list[0]['color'] != movw_list[1]['color']:
            result['is_flac'] = True
            result['color_for_4'] = movw_list[0]['color']  # First is Theme 4 (condition true)
            result['color_for_other'] = movw_list[1]['color']  # Second is others (condition false)
            result['movw_addr_4'] = movw_list[0]['addr']
            result['movw_instr_4'] = movw_list[0]['instr']
            result['movw_addr_other'] = movw_list[1]['addr']
            result['movw_instr_other'] = movw_list[1]['instr']

        return result

    def _collect_switch_case_movw_info(self, decoder: 'ThumbDecoder', func_addr: int, preload_colors: Dict[int, int], scan_range: int = 500) -> Dict[int, Dict]:
        """
        collect switch_case functionmiddleeachthemeCorresponding MOVW instructioninfo

        Returns: {theme_id: {"color": int, "movw_addr": str, "movw_instr": str}}
        """
        result = {}

        # build color -> theme_id mapping
        color_to_theme = {color: theme_id for theme_id, color in preload_colors.items()}

        offset = 0
        while offset < scan_range:
            hw = decoder.read16(func_addr + offset)
            is_32bit = hw >= 0xE800
            instr = decoder.decode(func_addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # detect MOVW instruction
            if 'MOVW' in mn and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)

                    # checkcheckthiscolorvaluenotin preload_colors middle
                    if val in color_to_theme:
                        theme_id = color_to_theme[val]
                        if theme_id not in result:  # onlyrecordfirst occurrence
                            result[theme_id] = {
                                "color": val,
                                "movw_addr": f"0x{func_addr + offset:05X}",
                                "movw_instr": f"{instr.mnemonic} {ops}",
                                "strh_addr": "-",
                                "strh_instr": "-"
                            }
                except:
                    pass

            offset += 4 if is_32bit else 2

        return result

    def analyze_all(self) -> Tuple[List[Dict], str]:
        """analysisallfirmware，Returnsresultlistandsummary HTML"""
        results = []

        versions = sorted([
            d for d in os.listdir(self.firmwares_dir)
            if os.path.isdir(os.path.join(self.firmwares_dir, d))
        ])

        for ver in versions:
            dir_path = os.path.join(self.firmwares_dir, ver)
            img_files = [f for f in os.listdir(dir_path) if f.endswith('.IMG')]

            if not img_files:
                continue

            img_path = os.path.join(dir_path, img_files[0])

            try:
                analyzer = ThemeColorAnalyzer(img_path)
                functions = analyzer.detector.scan_firmware()

                # extracttheme color
                theme_colors = {}
                flac_colors = {}
                progress_colors = {}
                marquee_colors = {}
                detailed_instructions = {}  # storedetailedinstruction {func_addr: {theme_id: [writes]}}

                for func in functions:
                    if func.pattern_type == "preload_store":
                        func_writes = {}
                        for theme_id in range(5):
                            _, writes, _ = analyzer.simulator.simulate(func, theme_id)
                            colors = {}
                            for w in writes:
                                # onlycollectset R1, R2, R3 color
                                if w.target_reg in [1, 2, 3]:
                                    colors[w.target_reg] = w.color_value
                            if colors:
                                theme_colors[theme_id] = colors
                            if writes:
                                func_writes[theme_id] = writes
                        if func_writes:
                            detailed_instructions[f"0x{func.addr:05X}"] = {
                                "pattern": "preload_store",
                                "ui_element": "Menu Text Colors",
                                "themes": func_writes
                            }

                    # extract FLAC String colors (ITE Pattern)
                    # FLAC function features: CMP Rx, #4 + twoconsecutive MOVW (oneuseat Theme 4，oneuseatitsother)
                    elif func.pattern_type == "ite":
                        # analysisFunction behaviorfeature
                        flac_behavior = self._analyze_flac_function_behavior(analyzer.decoder, func.addr)

                        if flac_behavior['is_flac']:
                            # Theme 4 use color_for_4, itsotheruse color_for_other
                            for theme_id in range(5):
                                if theme_id == 4:
                                    flac_colors[theme_id] = flac_behavior['color_for_4']
                                else:
                                    flac_colors[theme_id] = flac_behavior['color_for_other']

                            # storeinstructioninfo - forall 5  theme store
                            flac_func_writes = {}
                            for theme_id in range(5):
                                if theme_id == 4:
                                    flac_func_writes[theme_id] = {
                                        "color": flac_behavior['color_for_4'],
                                        "movw_addr": flac_behavior['movw_addr_4'],
                                        "movw_instr": flac_behavior['movw_instr_4'],
                                        "strh_addr": "-",
                                        "strh_instr": "-"
                                    }
                                else:
                                    flac_func_writes[theme_id] = {
                                        "color": flac_behavior['color_for_other'],
                                        "movw_addr": flac_behavior['movw_addr_other'],
                                        "movw_instr": flac_behavior['movw_instr_other'],
                                        "strh_addr": "-",
                                        "strh_instr": "-"
                                    }
                            detailed_instructions[f"0x{func.addr:05X}"] = {
                                "pattern": "ite",
                                "ui_element": "FLAC String",
                                "flac_writes": flac_func_writes
                            }

                    # extractProgress Bar BackgroundandMarqueecolor (switch_case Pattern)
                    # usingBehavior featuressplitclass，notrely on hardcodedEncodingcolorvalue
                    elif func.pattern_type == "switch_case":
                        preload = func.preload_colors

                        # analysisFunction behaviorfeature
                        behavior = self._analyze_theme_function_behavior(analyzer.decoder, func.addr)

                        # Theme color function features:
                        # 1. CMP R12, #0-4 outputnow 5 levelwithup (eachthemeonelevel)
                        # 2. has 5 differentcolorvalue
                        if behavior['cmp_r12_count'] >= 5 and behavior['distinct_colors'] == 5:
                            # collectset MOVW instructioninfo
                            movw_info = self._collect_switch_case_movw_info(analyzer.decoder, func.addr, preload)

                            if behavior['strh_count'] > 0:
                                # Has STRH write → enterdegreeitem (Color written to memory)
                                ui_element = "Progress Bar Background"
                                for reg_id, color in preload.items():
                                    progress_colors[reg_id] = color
                            else:
                                # No STRH write → Marquee (colorviaregisterReturns)
                                ui_element = "Marquee Overlay"
                                for reg_id, color in preload.items():
                                    marquee_colors[reg_id] = color

                            # storeinstructioninfo
                            if movw_info:
                                detailed_instructions[f"0x{func.addr:05X}"] = {
                                    "pattern": "switch_case",
                                    "ui_element": ui_element,
                                    "writes": movw_info
                                }

                results.append({
                    "version": ver,
                    "file": img_files[0],
                    "has_theme": bool(theme_colors) or bool(flac_colors),
                    "theme_colors": theme_colors,
                    "flac_colors": flac_colors,
                    "progress_colors": progress_colors,
                    "marquee_colors": marquee_colors,
                    "function_count": len(functions),
                    "theme_function": next(
                        (f"0x{f.addr:05X}" for f in functions if f.pattern_type == "preload_store"),
                        None
                    ),
                    "detailed_instructions": detailed_instructions
                })
            except Exception as e:
                results.append({
                    "version": ver,
                    "file": img_files[0],
                    "has_theme": False,
                    "error": str(e)
                })

        return results, self._generate_summary_html(results)

    def _generate_summary_html(self, results: List[Dict]) -> str:
        """generatesummary HTML report"""
        from datetime import datetime

        def color_to_css(val):
            if val == 0:
                return "#000000"
            r = (val >> 11) & 0x1F
            g = (val >> 5) & 0x3F
            b = val & 0x1F
            r = (r << 3) | (r >> 2)
            g = (g << 2) | (g >> 4)
            b = (b << 3) | (b >> 2)
            return f"rgb({r},{g},{b})"

        theme_versions = [r for r in results if r["has_theme"]]
        no_theme_versions = [r for r in results if not r["has_theme"]]

        def make_tooltip(color_val, movw_addr=None, movw_instr=None, strh_addr=None, strh_instr=None, label=""):
            """generatewith tooltip  color swatch HTML"""
            tooltip_content = f"<div class='instr-line'><span class='value'>{label}0x{color_val:04X}</span></div>"
            if movw_addr and movw_instr:
                tooltip_content += f"<div class='instr-line'><span class='addr'>{movw_addr}</span>: <span class='mnemonic'>{movw_instr}</span></div>"
            if strh_addr and strh_instr:
                tooltip_content += f"<div class='instr-line'><span class='addr'>{strh_addr}</span>: <span class='mnemonic'>{strh_instr}</span></div>"
            return f"""<div class="swatch-container">
                <div class="mini-swatch" style="background:{color_to_css(color_val)}"></div>
                <div class="tooltip">{tooltip_content}</div>
            </div>"""

        def get_instr_for_theme(detailed_instr, ui_element, theme_id):
            """from detailedinstructionmiddleget specifictheme instructioninfo"""
            for func_addr, data in detailed_instr.items():
                if data.get("ui_element") == ui_element:
                    if ui_element == "Menu Text Colors":
                        themes = data.get("themes", {})
                        writes = themes.get(theme_id, [])
                        # Returns R1, R2, R3  instruction
                        result = {}
                        for w in writes:
                            if w.target_reg in [1, 2, 3]:
                                if w.movw_instr:
                                    result[w.target_reg] = {
                                        "movw_addr": f"0x{w.movw_instr.addr:05X}",
                                        "movw_instr": f"{w.movw_instr.instr.mnemonic} {w.movw_instr.instr.operands}",
                                        "strh_addr": f"0x{w.addr:05X}",
                                        "strh_instr": f"{w.instr.mnemonic} {w.instr.operands}"
                                    }
                                else:
                                    # nothas MOVW instruction，cancanispreloadorinitialinitialvalue
                                    result[w.target_reg] = {
                                        "movw_addr": "(preload)",
                                        "movw_instr": "(preload)",
                                        "strh_addr": f"0x{w.addr:05X}",
                                        "strh_instr": f"{w.instr.mnemonic} {w.instr.operands}"
                                    }
                        return result
                    elif ui_element == "FLAC String":
                        flac_writes = data.get("flac_writes", {})
                        return flac_writes.get(theme_id)
                    elif ui_element in ["Progress Bar Background", "Marquee Overlay"]:
                        writes = data.get("writes", {})
                        return writes.get(theme_id)
            return None

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ECHO MINI allversionthemeAnalysis Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            font-size: 2.8em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #00d4ff, #00ff88, #ffaa00);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
            font-size: 1.1em;
        }}
        .stats-bar {{
            display: flex;
            justify-content: center;
            gap: 50px;
            background: rgba(0,212,255,0.1);
            border-radius: 20px;
            padding: 25px;
            margin-bottom: 30px;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 3em;
            font-weight: bold;
        }}
        .stat-value.ok {{ color: #00ff88; }}
        .stat-value.warn {{ color: #ffaa00; }}
        .stat-label {{
            color: #888;
            margin-top: 5px;
        }}
        h2 {{
            color: #00d4ff;
            margin: 30px 0 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(0,212,255,0.3);
        }}
        .version-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 20px;
        }}
        .version-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        .version-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 30px rgba(0,212,255,0.15);
        }}
        .version-card.no-theme {{
            opacity: 0.6;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .version-name {{
            font-size: 1.2em;
            font-weight: bold;
        }}
        .version-file {{
            font-size: 0.8em;
            color: #666;
        }}
        .badge {{
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.75em;
            font-weight: bold;
        }}
        .badge-ok {{ background: #00ff8833; color: #00ff88; }}
        .badge-no {{ background: #ffaa0033; color: #ffaa00; }}
        .themes-row {{
            display: flex;
            gap: 8px;
            margin-top: 15px;
        }}
        .theme-pill {{
            flex: 1;
            text-align: center;
            padding: 8px 5px;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
        }}
        .theme-num {{
            font-size: 0.7em;
            color: #666;
            margin-bottom: 5px;
        }}
        .color-swatches {{
            display: flex;
            justify-content: center;
            gap: 3px;
        }}
        .mini-swatch {{
            width: 24px;
            height: 24px;
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,0.2);
            position: relative;
            cursor: pointer;
        }}
        .mini-swatch:hover {{
            transform: scale(1.2);
            z-index: 10;
        }}
        /* Tooltip */
        .swatch-container {{
            position: relative;
            display: inline-block;
        }}
        .swatch-container .tooltip {{
            visibility: hidden;
            opacity: 0;
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.95);
            color: #fff;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.7em;
            white-space: nowrap;
            z-index: 100;
            margin-bottom: 5px;
            border: 1px solid rgba(0,212,255,0.3);
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            transition: opacity 0.2s;
            text-align: left;
            font-family: 'Monaco', 'Consolas', monospace;
            min-width: 200px;
        }}
        .swatch-container:hover .tooltip {{
            visibility: visible;
            opacity: 1;
        }}
        .tooltip .instr-line {{
            margin: 2px 0;
        }}
        .tooltip .addr {{ color: #00d4ff; }}
        .tooltip .mnemonic {{ color: #ffaa00; }}
        .tooltip .value {{ color: #00ff88; }}
        .func-addr {{
            font-family: monospace;
            color: #00d4ff;
            font-size: 0.85em;
            margin-top: 10px;
        }}
        .no-theme-msg {{
            color: #666;
            font-style: italic;
            text-align: center;
            padding: 20px;
        }}
        footer {{
            text-align: center;
            margin-top: 50px;
            padding: 30px;
            color: #555;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 ECHO MINI themeanalysis</h1>
        <p class="subtitle">All-version firmware theme color extraction report</p>

        <div class="stats-bar">
            <div class="stat">
                <div class="stat-value ok">{len(theme_versions)}</div>
                <div class="stat-label">supporttheme</div>
            </div>
            <div class="stat">
                <div class="stat-value warn">{len(no_theme_versions)}</div>
                <div class="stat-label">nonethemesystem</div>
            </div>
            <div class="stat">
                <div class="stat-value ok">{len(results)}</div>
                <div class="stat-label">totalversionnumber</div>
            </div>
        </div>

        <h2>✅ Supports theme systemversion ({len(theme_versions)})</h2>
        <div class="version-grid">
"""

        for r in theme_versions:
            html += f"""
            <div class="version-card">
                <div class="card-header">
                    <div>
                        <div class="version-name">{r['version']}</div>
                        <div class="version-file">{r['file']}</div>
                    </div>
                    <span class="badge badge-ok">OK</span>
                </div>
                <div style="margin-top: 10px; font-size: 0.85em; color: #888;">Menu Text Colors:</div>
                <div class="themes-row">
"""

            for t in range(5):
                colors = r["theme_colors"].get(t, {})
                r1 = colors.get(1, 0)
                r2 = colors.get(2, 0)
                r3 = colors.get(3, 0)

                # getselectinstructioninfo
                detailed = r.get("detailed_instructions", {})
                menu_instr = get_instr_for_theme(detailed, "Menu Text Colors", t)

                # generatewith tooltip colorblock
                r1_swatch = make_tooltip(r1, label="R1: ")
                r2_swatch = make_tooltip(r2, label="R2: ")
                r3_swatch = make_tooltip(r3, label="R3: ")

                if menu_instr:
                    if 1 in menu_instr:
                        r1_swatch = make_tooltip(r1, menu_instr[1]["movw_addr"], menu_instr[1]["movw_instr"],
                                                 menu_instr[1]["strh_addr"], menu_instr[1]["strh_instr"], "R1: ")
                    if 2 in menu_instr:
                        r2_swatch = make_tooltip(r2, menu_instr[2]["movw_addr"], menu_instr[2]["movw_instr"],
                                                 menu_instr[2]["strh_addr"], menu_instr[2]["strh_instr"], "R2: ")
                    if 3 in menu_instr:
                        r3_swatch = make_tooltip(r3, menu_instr[3]["movw_addr"], menu_instr[3]["movw_instr"],
                                                 menu_instr[3]["strh_addr"], menu_instr[3]["strh_instr"], "R3: ")

                html += f"""
                    <div class="theme-pill">
                        <div class="theme-num">T{t}</div>
                        <div class="color-swatches">
                            {r1_swatch}
                            {r2_swatch}
                            {r3_swatch}
                        </div>
                    </div>
"""

            # FLAC String colors
            flac_colors = r.get("flac_colors", {})
            if flac_colors:
                html += f"""
                </div>
                <div style="margin-top: 10px; font-size: 0.85em; color: #888;">FLAC String colors:</div>
                <div class="themes-row">
"""
                for t in range(5):
                    flac_c = flac_colors.get(t, 0)
                    # getselectinstructioninfo
                    flac_instr = get_instr_for_theme(detailed, "FLAC String", t)
                    flac_swatch = make_tooltip(flac_c, label="FLAC: ")
                    if flac_instr:
                        flac_swatch = make_tooltip(flac_c, flac_instr.get("movw_addr"), flac_instr.get("movw_instr"),
                                                   flac_instr.get("strh_addr"), flac_instr.get("strh_instr"), "FLAC: ")
                    html += f"""
                    <div class="theme-pill">
                        <div class="theme-num">T{t}</div>
                        <div class="color-swatches">
                            {flac_swatch}
                        </div>
                    </div>
"""

            # Progress Bar Backgroundcolor
            progress_colors = r.get("progress_colors", {})
            if progress_colors:
                html += f"""
                </div>
                <div style="margin-top: 10px; font-size: 0.85em; color: #888;">Progress Bar Backgroundcolor:</div>
                <div class="themes-row">
"""
                for t in range(5):
                    prog_c = progress_colors.get(t, 0)
                    # getselectinstructioninfo
                    prog_instr = get_instr_for_theme(detailed, "Progress Bar Background", t)
                    prog_swatch = make_tooltip(prog_c, label="Progress: ")
                    if prog_instr:
                        prog_swatch = make_tooltip(prog_c, prog_instr.get("movw_addr"), prog_instr.get("movw_instr"),
                                                   prog_instr.get("strh_addr"), prog_instr.get("strh_instr"), "Progress: ")
                    html += f"""
                    <div class="theme-pill">
                        <div class="theme-num">T{t}</div>
                        <div class="color-swatches">
                            {prog_swatch}
                        </div>
                    </div>
"""

            # Marqueecolor
            marquee_colors = r.get("marquee_colors", {})
            if marquee_colors:
                html += f"""
                </div>
                <div style="margin-top: 10px; font-size: 0.85em; color: #888;">Marquee Overlaycolor:</div>
                <div class="themes-row">
"""
                for t in range(5):
                    marq_c = marquee_colors.get(t, 0)
                    # getselectinstructioninfo
                    marq_instr = get_instr_for_theme(detailed, "Marquee Overlay", t)
                    marq_swatch = make_tooltip(marq_c, label="Marquee: ")
                    if marq_instr:
                        marq_swatch = make_tooltip(marq_c, marq_instr.get("movw_addr"), marq_instr.get("movw_instr"),
                                                   marq_instr.get("strh_addr"), marq_instr.get("strh_instr"), "Marquee: ")
                    html += f"""
                    <div class="theme-pill">
                        <div class="theme-num">T{t}</div>
                        <div class="color-swatches">
                            {marq_swatch}
                        </div>
                    </div>
"""

            html += f"""
                </div>
                <div class="func-addr">📍 Theme functions: {r.get('theme_function', 'N/A')}</div>
            </div>
"""

        html += f"""
        </div>

        <h2>⚪ Does not support theme systemversion ({len(no_theme_versions)})</h2>
        <div class="version-grid">
"""

        for r in no_theme_versions:
            html += f"""
            <div class="version-card no-theme">
                <div class="card-header">
                    <div>
                        <div class="version-name">{r['version']}</div>
                        <div class="version-file">{r['file']}</div>
                    </div>
                    <span class="badge badge-no">nonetheme</span>
                </div>
                <div class="no-theme-msg">thisversionDoes not support theme system</div>
            </div>
"""

        html += f"""
        </div>

        <footer>
            📊 Analysis completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
            Tool: theme_extractor.py | Analyzed total {len(results)} firmware versions
        </footer>
    </div>
</body>
</html>
"""
        return html


# ============================================================================
# mainanalysiser
# ============================================================================

class ThemeColorAnalyzer:
    """Theme Color Analyzer"""

    def __init__(self, firmware_path: str):
        self.firmware_path = firmware_path

        with open(firmware_path, 'rb') as f:
            self.data = f.read()

        self.decoder = ThumbDecoder(self.data)
        self.detector = ThemeFunctionDetector(self.decoder)
        self.simulator = ControlFlowSimulator(self.decoder)
        self.report = ReportGenerator(firmware_path, self.decoder)

    def _analyze_flac_function_behavior(self, addr: int, scan_range: int = 100) -> dict:
        """
        Analyze FLAC String function behavior features

        FLAC function features:
        - CMP Rx, #4 (compare if theme value is 4)
        - twoconsecutive MOVW instruction (ITE conditional execution)
        - First MOVW is Theme 4 color
        - Second MOVW is other themes color

        Returns:
        - is_flac: notis FLAC function
        - color_for_4: Theme 4 color
        - color_for_other: other themes color
        - movw_addr_4, movw_instr_4: Theme 4  MOVW instructioninfo
        - movw_addr_other, movw_instr_other: othertheme MOVW instructioninfo
        """
        result = {
            'is_flac': False,
            'color_for_4': 0,
            'color_for_other': 0,
            'movw_addr_4': '',
            'movw_instr_4': '',
            'movw_addr_other': '',
            'movw_instr_other': '',
        }

        offset = 0
        found_cmp_4 = False
        cmp_4_offset = 0

        # Step 1: Find CMP Rx, #4
        while offset < scan_range:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # find CMP Rx, #4 (anywhatregister)
            # checkcheck instr.imm == 4 oreroperationasfunctionstringpackagecontain #4 or #0x4
            if 'CMP' in mn and (instr.imm == 4 or '#4' in ops or '#0x4' in ops):
                found_cmp_4 = True
                cmp_4_offset = offset
                break

            offset += 4 if is_32bit else 2

        if not found_cmp_4:
            return result

        # Step 2: Find two consecutive MOVW after CMP #4
        offset = cmp_4_offset + (4 if self.decoder.read16(addr + cmp_4_offset) >= 0xE800 else 2)

        movw_list = []
        while offset < scan_range and len(movw_list) < 2:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            if 'MOVW' in mn and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    movw_list.append({
                        'addr': f"0x{addr + offset:05X}",
                        'instr': f"{instr.mnemonic} {instr.operands}",
                        'color': val
                    })
                except:
                    pass

            offset += 4 if is_32bit else 2

        # FLAC feature: CMP #4 followed by two different MOVW
        if len(movw_list) == 2 and movw_list[0]['color'] != movw_list[1]['color']:
            result['is_flac'] = True
            result['color_for_4'] = movw_list[0]['color']  # First is Theme 4 (condition true)
            result['color_for_other'] = movw_list[1]['color']  # Second is others (condition false)
            result['movw_addr_4'] = movw_list[0]['addr']
            result['movw_instr_4'] = movw_list[0]['instr']
            result['movw_addr_other'] = movw_list[1]['addr']
            result['movw_instr_other'] = movw_list[1]['instr']

        return result

    def _analyze_theme_function_behavior(self, addr: int, scan_range: int = 200) -> dict:
        """
        Analyze function behavior features to identify theme color functions

        Returns:
        - cmp_r12_count: Count of CMP R12, #0-4
        - distinct_colors: Count of distinct MOVW R0 color values
        - strh_count: STRH instructioncount
        - colors: Specific color value list
        """
        features = {
            'cmp_r12_count': 0,
            'distinct_colors': 0,
            'strh_count': 0,
            'colors': set(),
        }

        offset = 0
        colors = []

        while offset < scan_range:
            hw = self.decoder.read16(addr + offset)
            is_32bit = hw >= 0xE800
            instr = self.decoder.decode(addr + offset)
            mn = instr.mnemonic.upper()
            ops = instr.operands

            # Count CMP R12, #0-4 (packageinclude CMP.W format)
            if 'CMP' in mn and 'R12' in ops:
                # checkcheckImmediate valuenotin 0-4 rangeinside
                imm_val = instr.imm
                if 0 <= imm_val <= 4:
                    features['cmp_r12_count'] += 1

            # collectset MOVW R0 colorvalue
            if 'MOVW' in mn and 'R0' in ops and '#' in ops:
                try:
                    val_str = ops.split('#')[1].split()[0].rstrip('}')
                    val = int(val_str, 16) if val_str.startswith('0x') else int(val_str)
                    colors.append(val)
                except:
                    pass

            # Count STRH instruction
            if 'STRH' in mn:
                features['strh_count'] += 1

            offset += 4 if is_32bit else 2

        features['colors'] = set(colors)
        features['distinct_colors'] = len(set(colors))

        return features

    def analyze(self, verbose: bool = False) -> str:
        """executioncompleteanalysis"""
        if verbose:
            print(f"analysisfirmware: {self.firmware_path}")
            print(f"size: {len(self.data):,} bytes")

        # 0. dynamicstatefoundTheme count
        from theme_extractor import ThemeDiscovery
        self.theme_count, self.theme_names = ThemeDiscovery.discover_theme_count(self.data)
        if verbose:
            print(f"found {self.theme_count} theme: {self.theme_names}")

        # 1. detectTheme functions
        functions = self.detector.scan_firmware()

        if verbose:
            print(f"detectto {len(functions)} candidatesfunction")

        # 2. Check for existing patches
        patch_detector = PatchDetector(self.data, self.decoder)
        self.patch_info = patch_detector.detect_patch(functions)

        if verbose and self.patch_info.is_patched:
            print(f"Patch detected: {self.patch_info.patch_type} (confidence: {self.patch_info.confidence:.0%})")
            if self.patch_info.metadata:
                print(f"  Patch metadata found at 0x{self.patch_info.metadata.get('metadata_addr', 0):X}")

        # 3. simulationeachfunctions，andusingbehavioranalysisidentify UI Element
        for func in functions:
            theme_results = {}

            for theme_id in range(self.theme_count):
                _, writes, movw_records = self.simulator.simulate(func, theme_id)
                # savekeepallwrite，0 alsoisvalidcolorvalue
                theme_results[theme_id] = writes

            # usingbehavioranalysisidentify UI Element
            func.ui_element = self._identify_ui_element_by_behavior(func, theme_results)

            self.report.add_function(func, theme_results)

        # 4. Add patch info to report
        self.report.set_patch_info(self.patch_info)

        # 5. generatereport
        return self.report.generate_markdown()

    def _identify_ui_element_by_behavior(self, func: ThemeFunction, theme_results: Dict) -> str:
        """based onBehavior featuresidentify UI Element，not relying on hardcodedEncodingcolorvalue"""

        # forat ITE Pattern，checkchecknotis FLAC function
        # usingtwo typesMethoddetect:
        # 1. CMP #4 + IT + MOVW Pattern
        # 2. '|' charactercontext (changecanrely)
        if func.pattern_type == "ite":
            # firstfirsttrytestusingcontextdetect (has '|' character)
            from theme_extractor import ThemeDiscovery
            flac_context = ThemeDiscovery.detect_flac_by_context(self.decoder, func.addr)
            if flac_context['is_flac']:
                return "FLAC String Text"

            # returnexittoPatterndetect
            flac_behavior = self._analyze_flac_function_behavior(func.addr)
            if flac_behavior['is_flac']:
                return "FLAC String Text"

        # forat switch_case Pattern，alsocheckchecknothas FLAC contextfeature
        if func.pattern_type == "switch_case":
            # firstfirstcheckcheck FLAC context
            from theme_extractor import ThemeDiscovery
            flac_context = ThemeDiscovery.detect_flac_by_context(self.decoder, func.addr)
            if flac_context['is_flac']:
                return "FLAC String Text"

            # thenaftercheckcheckenterdegreeitem/Marqueefeature
            behavior = self._analyze_theme_function_behavior(func.addr)

            # theme colorfunctionfeature: CMP R12 #0-4 outputnow N levelwithup + N differentcolor (N = theme_count)
            if behavior['cmp_r12_count'] >= self.theme_count and behavior['distinct_colors'] == self.theme_count:
                if behavior['strh_count'] > 0:
                    return "Progress Bar Background"
                else:
                    return "Marquee/Scrolling Text Overlay"

        # forat preload_store pattern，checkchecknothastypicaltypemenusinglecolorPattern
        if func.pattern_type == "preload_store":
            # getselectallcolorvalue
            all_colors = set()
            for writes in theme_results.values():
                for w in writes:
                    all_colors.add(w.color_value)
            for c in func.preload_colors.values():
                all_colors.add(c)

            # Menu Text Colorsviaexceptionhasmanywrite to R1, R2, R3
            if any(w.target_reg in [1, 2, 3] for writes in theme_results.values() for w in writes):
                return "Menu Text Colors (Highlight/Normal/Second)"

        return "Unknown UI Element"


# ============================================================================
# Patch Detection
# ============================================================================


class PatchDetector:
    """Detect if firmware has been patched with custom theme colors"""

    # Known original instruction patterns
    FLAC_ORIGINAL = bytes.fromhex('04290CBF')  # CMP R1,#4 + ITE EQ
    MENU_ORIGINAL = bytes.fromhex('4FF0000C')  # MOV.W R12, #0

    # Patch metadata magic
    PATCH_MAGIC = b'ECHO'

    def __init__(self, firmware_data: bytes, decoder: ThumbDecoder):
        self.data = firmware_data
        self.decoder = decoder

    def detect_patch(self, theme_functions: List['ThemeFunction']) -> PatchInfo:
        """
        Detect if firmware has been patched

        Returns PatchInfo with detection results
        """
        info = PatchInfo()

        flac_funcs = [f for f in theme_functions if f.ui_element and 'FLAC' in f.ui_element]
        menu_funcs = [f for f in theme_functions if f.ui_element and 'Menu' in f.ui_element]

        # Check FLAC functions
        for func in flac_funcs:
            is_patched, target = self._check_flac_patched(func.addr)
            if is_patched:
                info.flac_patched = True
                info.patch_target_addr = target
                break

        # Check Menu functions
        for func in menu_funcs:
            is_patched, target = self._check_menu_patched(func.addr)
            if is_patched:
                info.menu_patched = True
                if not info.patch_target_addr:
                    info.patch_target_addr = target
                break

        # Check NOP region for code
        info.nop_has_code = self._check_nop_region_for_code()

        # Determine overall patch status
        if info.flac_patched and info.menu_patched:
            info.patch_type = "full"
            info.confidence = 0.95
        elif info.flac_patched:
            info.patch_type = "flac_only"
            info.confidence = 0.8
        elif info.menu_patched:
            info.patch_type = "menu_only"
            info.confidence = 0.8
        elif info.nop_has_code:
            info.patch_type = "unknown"
            info.confidence = 0.5
        else:
            info.patch_type = "none"
            info.confidence = 1.0

        info.is_patched = info.patch_type != "none"

        # Try to read patch metadata
        if info.is_patched:
            info.metadata = self._read_patch_metadata()

        return info

    def _check_flac_patched(self, func_addr: int) -> Tuple[bool, int]:
        """Check if FLAC function is patched"""
        # Find CMP+ITE pattern
        for offset in range(0, 500, 2):
            addr = func_addr + offset
            if addr + 4 > len(self.data):
                break

            if self.data[addr:addr+2] == bytes.fromhex('0429'):  # CMP R1,#4
                if self.data[addr+2:addr+4] == bytes.fromhex('0CBF'):  # ITE EQ
                    # Found the pattern, check what's there now
                    current = self.data[addr:addr+4]
                    if current == self.FLAC_ORIGINAL:
                        return False, 0
                    elif self._is_bl_instruction(addr):
                        # Decode BL target
                        target = self._decode_bl_target(addr)
                        return True, target
                    return False, 0

        return False, 0

    def _check_menu_patched(self, func_addr: int) -> Tuple[bool, int]:
        """Check if Menu function is patched"""
        # Find MOV.W R12, #0 pattern
        for offset in range(0, 200, 2):
            addr = func_addr + offset
            if addr + 4 > len(self.data):
                break

            if self.data[addr:addr+4] == self.MENU_ORIGINAL:
                # Found original, check what's there now
                current = self.data[addr:addr+4]
                if current == self.MENU_ORIGINAL:
                    return False, 0
                elif self._is_bl_instruction(addr):
                    target = self._decode_bl_target(addr)
                    return True, target
                return False, 0

        return False, 0

    def _is_bl_instruction(self, addr: int) -> bool:
        """Check if instruction at addr is a BL"""
        if addr + 4 > len(self.data):
            return False
        hw = self.data[addr] | (self.data[addr + 1] << 8)
        return (hw & 0xF800) == 0xF000

    def _decode_bl_target(self, addr: int) -> int:
        """Decode BL instruction target address"""
        if addr + 4 > len(self.data):
            return 0

        hw1 = self.data[addr] | (self.data[addr + 1] << 8)
        hw2 = self.data[addr + 2] | (self.data[addr + 3] << 8)

        # Decode BL: 11110 S imm10 11 J1 1 J2 imm11
        S = (hw1 >> 10) & 1
        imm10 = hw1 & 0x3FF
        J1 = (hw2 >> 13) & 1
        J2 = (hw2 >> 11) & 1
        imm11 = hw2 & 0x7FF

        I1 = (~(S ^ J1)) & 1
        I2 = (~(S ^ J2)) & 1

        imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1)

        if S:
            imm32 = imm32 - (1 << 25)

        return addr + 4 + imm32

    def _check_nop_region_for_code(self) -> bool:
        """Check if known NOP region has code"""
        # Check common NOP slide locations
        nop_regions = [
            (0x12BBFC, 64),  # 440 byte region
            (0x588A8, 64),   # 132KB region
        ]

        for start, size in nop_regions:
            if start + size <= len(self.data):
                region = self.data[start:start + size]
                if region != b'\x00' * size:
                    # Has non-zero bytes
                    non_zero = sum(1 for b in region if b != 0)
                    if non_zero > size // 2:
                        return True

        return False

    def _read_patch_metadata(self) -> Optional[Dict]:
        """Read patch metadata from NOP region"""
        # Try to find metadata at end of NOP regions
        metadata_locations = [
            0x12BDB4 - 51,  # End of 440 byte region minus metadata size
        ]

        for addr in metadata_locations:
            if addr < 0 or addr + 51 > len(self.data):
                continue

            data = self.data[addr:addr + 51]

            if data[0:4] != self.PATCH_MAGIC:
                continue

            try:
                import struct
                version = data[4]
                timestamp = struct.unpack('<I', data[5:9])[0]

                flac_colors = []
                for i in range(5):
                    offset = 9 + i * 2
                    flac_colors.append(struct.unpack('<H', data[offset:offset+2])[0])

                menu_colors = []
                for i in range(15):
                    offset = 19 + i * 2
                    menu_colors.append(struct.unpack('<H', data[offset:offset+2])[0])

                # Verify checksum
                stored_crc = struct.unpack('<H', data[49:51])[0]

                return {
                    'version': version,
                    'timestamp': timestamp,
                    'flac_colors': flac_colors,
                    'menu_colors': menu_colors,
                    'metadata_addr': addr
                }
            except:
                continue

        return None

    def extract_patched_colors(self, patch_target: int, func_type: str) -> Dict[int, int]:
        """
        Extract colors from patched code

        This traces into the NOP region and extracts colors from the patch code
        """
        colors = {}

        if patch_target == 0:
            return colors

        # Scan for MOVW instructions in the patched code region
        scan_start = patch_target
        scan_end = min(patch_target + 500, len(self.data))

        offset = scan_start
        while offset < scan_end:
            instr = self.decoder.decode(offset)
            if instr is None:
                offset += 2
                continue

            if instr.instr_type == InstructionType.MOVW:
                # Found a MOVW, this might be a color
                if instr.imm > 0:  # Non-zero immediate
                    # Determine theme ID from context
                    # This is simplified - full implementation would trace control flow
                    theme_id = len(colors)
                    if theme_id < 5:
                        colors[theme_id] = instr.imm

            offset += len(instr.raw_bytes)

        return colors


# ============================================================================
# Main Program
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python theme_extractor.py <firmware.img|firmwares_dir> [Options]")
        print("")
        print("Options:")
        print("  --verbose, -v    Show verbose output")
        print("  --html           Generate HTML report")
        print("  --batch          Batch analyze firmwares directory")
        print("")
        print("Examples:")
        print("  python theme_extractor.py HIFIEC10.IMG")
        print("  python theme_extractor.py HIFIEC10.IMG --html")
        print("  python theme_extractor.py firmwares/ --batch --html")
        sys.exit(1)

    target = sys.argv[1]
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    generate_html = '--html' in sys.argv
    batch_mode = '--batch' in sys.argv

    # batchPattern
    if batch_mode or os.path.isdir(target):
        # confirmconfirm firmwares itemrecord
        if os.path.isdir(target) and target != '.':
            firmwares_dir = target
        elif os.path.isdir(os.path.join(os.path.dirname(__file__), "firmwares")):
            firmwares_dir = os.path.join(os.path.dirname(__file__), "firmwares")
        else:
            firmwares_dir = target if os.path.isdir(target) else "."

        if not os.path.isdir(firmwares_dir):
            print(f"Error: Directory does not exist: {firmwares_dir}")
            sys.exit(1)

        print(f"Batch analysis: {firmwares_dir}")
        print()

        batch = BatchAnalyzer(firmwares_dir)
        results, summary_html = batch.analyze_all()

        # printsummary
        print("=" * 60)
        print("Analysis Results Summary")
        print("=" * 60)

        theme_versions = [r for r in results if r["has_theme"]]
        no_theme_versions = [r for r in results if not r["has_theme"]]

        print(f"\nSupports theme system ({len(theme_versions)} ):")
        for r in theme_versions:
            print(f"  ✓ {r['version']} - {r['file']}")

        print(f"\nDoes not support theme system ({len(no_theme_versions)} ):")
        for r in no_theme_versions:
            print(f"  ○ {r['version']} - {r['file']}")

        # Save HTML report (savestoreinfooterthisinitemrecord)
        if generate_html:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_path = os.path.join(script_dir, "theme_analysis_report.html")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(summary_html)
            print(f"\n✓ HTML report saved to: {output_path}")

        return

    # singletextfilePattern
    if not os.path.exists(target):
        print(f"Error: File does not exist: {target}")
        sys.exit(1)

    analyzer = ThemeColorAnalyzer(target)
    report = analyzer.analyze(verbose=verbose)

    if generate_html:
        html_report = analyzer.report.generate_html(os.path.basename(target))
        output_path = target.replace('.IMG', '_theme_report.html')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_report)
        print(f"✓ HTML report saved to: {output_path}")
    else:
        print(report)
        # Save Markdown report
        output_path = target.replace('.IMG', '_theme_report.md')
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nreportsaved to: {output_path}")


if __name__ == "__main__":
    main()
