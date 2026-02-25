/**
 * Theme Behavior Analyzer
 *
 * Analyzes function behavior to identify theme-specific characteristics.
 * Port of Python's _analyze_flac_function_behavior and _analyze_theme_function_behavior.
 */

import { ThumbDecoder } from './thumb/index.js';
import type { FlacBehavior, MenuBehavior } from './types.js';

/**
 * Behavior Analyzer Class
 *
 * Analyzes theme functions to extract detailed behavior information.
 */
export class BehaviorAnalyzer {
	private readonly decoder: ThumbDecoder;

	constructor(decoder: ThumbDecoder) {
		this.decoder = decoder;
	}

	/**
	 * Read FLAC patch metadata from NOP slide
	 * Returns colors if valid metadata found, null otherwise
	 */
	private readFlacPatchMetadata(data: Uint8Array): { flacColors: number[] } | null {
		// Find the LAST occurrence of metadata magic string 'ECHO' in the firmware
		// There may be multiple ECHO strings in the firmware, but our patch metadata is the last one written
		// Version must be 1 (our metadata version)
		let metadataAddr = -1;

		// Search from the end backwards for 'ECHO' followed by valid version byte
		for (let offset = data.length - 51; offset >= 0; offset--) {
			// Check for magic string 'ECHO'
			if (data[offset] === 0x45 && // E
			    data[offset + 1] === 0x43 && // C
			    data[offset + 2] === 0x48 && // H
			    data[offset + 3] === 0x4f) { // O

				// Check for valid version (must be 1 for our patch metadata)
				const version = data[offset + 4];
				if (version === 1) {
					// Found valid patch metadata
					metadataAddr = offset;
					break;
				}
			}
		}

		if (metadataAddr < 0) {
			return null;
		}

		// Read FLAC colors (5 * uint16 = 10 bytes, starting at offset 9)
		// Offset breakdown: magic(4) + version(1) + timestamp(4) = 9
		const flacColors: number[] = [];
		for (let i = 0; i < 5; i++) {
			const offset = metadataAddr + 9 + i * 2;
			if (offset + 2 > data.length) break;
			const color = data[offset] | (data[offset + 1] << 8);
			flacColors.push(color);
		}

		if (flacColors.length !== 5) {
			return null;
		}

		return { flacColors };
	}

	/**
	 * Analyze FLAC function behavior
	 *
	 * FLAC function features:
	 * - CMP Rx, #4 (compare if theme value is 4)
	 * - two consecutive MOVW instructions (ITE conditional execution)
	 * - First MOVW is Theme 4 color
	 * - Second MOVW is other themes color
	 *
	 * @param addr - Function address to analyze
	 * @param scanRange - Number of bytes to scan
	 * @returns FLAC behavior analysis result
	 */
	analyzeFlacFunction(addr: number, scanRange = 100): FlacBehavior {
		// Check for patch metadata first (for patched firmware)
		const data = this.decoder.getData();
		const metadata = this.readFlacPatchMetadata(data);
		if (metadata && metadata.flacColors.length === 5) {
			// Firmware is patched - use metadata colors
			return {
				type: 'standard',
				isFlac: true,
				colorFor4: metadata.flacColors[4],
				colorForOther: metadata.flacColors[0],
				flacColors: metadata.flacColors,
				movwAddr4: '(patch)',
				movwInstr4: '(patched)',
				movwAddrOther: '(patch)',
				movwInstrOther: '(patched)'
			};
		}

		// No patch metadata - scan for MOVW instructions (unpatched firmware)
		const result: FlacBehavior = {
			type: 'unknown',
			isFlac: false,
			colorFor4: 0,
			colorForOther: 0,
			movwAddr4: '',
			movwInstr4: '',
			movwAddrOther: '',
			movwInstrOther: ''
		};

		let offset = 0;
		let foundCmp4 = false;
		let cmp4Offset = 0;

		// Step 1: Find CMP Rx, #4
		while (offset < scanRange) {
			const hw = this.decoder.readU16(addr + offset);
			const is32bit = hw >= 0xe800;
			const instr = this.decoder.decode(addr + offset);
			const mnemonic = instr.mnemonic.toUpperCase();
			const operands = instr.operands;

			// Find CMP Rx, #4 (any register)
			// Check if instr.imm == 4 or operands string contains #4 or #0x4
			if (mnemonic.includes('CMP') && (instr.imm === 4 || operands.includes('#4') || operands.includes('#0x4'))) {
				foundCmp4 = true;
				cmp4Offset = offset;
				break;
			}

			offset += is32bit ? 4 : 2;
		}

		if (!foundCmp4) {
			return result;
		}

		// Step 2: Find two consecutive MOVW after CMP #4
		const cmpHw = this.decoder.readU16(addr + cmp4Offset);
		offset = cmp4Offset + (cmpHw >= 0xe800 ? 4 : 2);

		const movwList: Array<{ addr: string; instr: string; color: number }> = [];

		while (offset < scanRange && movwList.length < 2) {
			const hw = this.decoder.readU16(addr + offset);
			const is32bit = hw >= 0xe800;
			const instr = this.decoder.decode(addr + offset);
			const mnemonic = instr.mnemonic.toUpperCase();
			const operands = instr.operands;

			if (mnemonic.includes('MOVW') && operands.includes('#')) {
				try {
					const hashIndex = operands.indexOf('#');
					const valStr = operands.slice(hashIndex + 1).split(/\s/)[0].replace('}', '');
					const val = valStr.startsWith('0x') ? Number.parseInt(valStr, 16) : Number.parseInt(valStr, 10);
					movwList.push({
						addr: `0x${(addr + offset).toString(16).toUpperCase().padStart(5, '0')}`,
						instr: `${instr.mnemonic} ${instr.operands}`,
						color: val
					});
				} catch {
					// Skip invalid parsing
				}
			}

			offset += is32bit ? 4 : 2;
		}

		// FLAC feature: CMP #4 followed by two different MOVW
		if (movwList.length === 2 && movwList[0].color !== movwList[1].color) {
			result.type = 'standard';
			result.isFlac = true;
			result.colorFor4 = movwList[0].color; // First is Theme 4 (condition true)
			result.colorForOther = movwList[1].color; // Second is others (condition false)
			result.movwAddr4 = movwList[0].addr;
			result.movwInstr4 = movwList[0].instr;
			result.movwAddrOther = movwList[1].addr;
			result.movwInstrOther = movwList[1].instr;
		}

		return result;
	}

	/**
	 * Analyze Menu/Theme function behavior
	 *
	 * Returns:
	 * - cmpR12Count: Count of CMP R12, #0-4
	 * - distinctColors: Count of distinct MOVW R0 color values
	 * - strhCount: STRH instruction count
	 * - colors: Set of specific color values
	 *
	 * @param addr - Function address to analyze
	 * @param scanRange - Number of bytes to scan
	 * @returns Menu behavior analysis result
	 */
	analyzeMenuFunction(addr: number, scanRange = 200): MenuBehavior {
		const result: MenuBehavior = {
			cmpR12Count: 0,
			distinctColors: 0,
			strhCount: 0,
			colors: new Set<number>()
		};

		const colors: number[] = [];
		let offset = 0;

		while (offset < scanRange) {
			const hw = this.decoder.readU16(addr + offset);
			const is32bit = hw >= 0xe800;
			const instr = this.decoder.decode(addr + offset);
			const mnemonic = instr.mnemonic.toUpperCase();
			const operands = instr.operands;

			// Count CMP R12, #0-4 (including CMP.W format)
			if (mnemonic.includes('CMP') && operands.includes('R12')) {
				// Check immediate value is in 0-4 range
				const immVal = instr.imm;
				if (immVal >= 0 && immVal <= 4) {
					result.cmpR12Count++;
				}
			}

			// Collect MOVW R0 color values
			if (mnemonic.includes('MOVW') && operands.includes('R0') && operands.includes('#')) {
				try {
					const hashIndex = operands.indexOf('#');
					const valStr = operands.slice(hashIndex + 1).split(/\s/)[0].replace('}', '');
					const val = valStr.startsWith('0x') ? Number.parseInt(valStr, 16) : Number.parseInt(valStr, 10);
					colors.push(val);
				} catch {
					// Skip invalid parsing
				}
			}

			// Count STRH instructions
			if (mnemonic.includes('STRH')) {
				result.strhCount++;
			}

			offset += is32bit ? 4 : 2;
		}

		result.colors = new Set(colors);
		result.distinctColors = result.colors.size;

		return result;
	}

	/**
	 * Check if instruction is MOVW
	 *
	 * @param data - Firmware data
	 * @param addr - Address to check
	 * @returns True if MOVW instruction
	 */
	isMovwInstruction(data: Uint8Array, addr: number): boolean {
		if (addr + 4 > data.length) return false;

		const hw1 = data[addr] | (data[addr + 1] << 8);
		const hw2 = data[addr + 2] | (data[addr + 3] << 8);

		// MOVW encoding: 0xF240-0xF27F for first halfword, 0x0000-0xF0FF for second
		return (hw1 & 0xf800) === 0xf240 && (hw2 & 0x8000) === 0;
	}
}
