/**
 * Switch-Case Function Patcher
 *
 * Patches Progress Bar and Marquee functions by modifying MOVW instructions directly.
 * These functions use a switch_case pattern (CMP R12, #0-4) to select colors.
 *
 * Unlike FLAC/Menu which use BL instructions and NOP slides, switch_case functions
 * are patched by finding and replacing the MOVW immediate values.
 */

import type { ThemeFunction } from './types.js';
import { encodeMovw } from './thumb/encoders.js';
import { PatchError } from './errors.js';

/**
 * Result of patching a switch_case function
 */
export interface SwitchCasePatchResult {
	/** Function address */
	funcAddr: number;
	/** Whether patching was successful */
	success: boolean;
	/** Number of MOVW instructions patched */
	patchesApplied: number;
	/** Original colors */
	originalColors: number[];
	/** New colors */
	newColors: number[];
}

/**
 * Find MOVW instructions that load color values in a switch_case function
 *
 * Strategy:
 * - Colors 1-4 are in IT EQ blocks, appearing shortly after their respective CMP R12 instructions
 * - Color 0 is at a BEQ target (default case) after CMP R12, #0
 * - Track BEQ targets and look for MOVW at those addresses for color 0
 */
function findColorMovwInstructions(
	data: Uint8Array,
	funcAddr: number,
	maxScan = 500
): Array<{ offset: number; imm: number; colorIndex: number }> {
	const result: Array<{ offset: number; imm: number; colorIndex: number }> = [];
	let lastCmpIndex = -1;
	let lastCmpAddr = 0;
	let beqTargetForColor0 = 0;

	for (let offset = 0; offset < maxScan;) {
		const addr = funcAddr + offset;
		const hw1 = data[addr] | (data[addr + 1] << 8);

		// Check for CMP.W R12, #imm (F1BC 0Fmm)
		if (hw1 === 0xF1BC) {
			const hw2 = data[addr + 2] | (data[addr + 3] << 8);
			if ((hw2 & 0xFF00) === 0x0F00) {
				const imm = hw2 & 0xFF;
				if (imm >= 0 && imm <= 4) {
					lastCmpIndex = imm;
					lastCmpAddr = addr;
				}
			}
			offset += 4;
			continue;
		}

		// Check for BEQ instruction (D0xx or conditional 16-bit branch)
		// BEQ is typically D0xx in Thumb (16-bit) or F0xx 8xxx in Thumb-2 (32-bit)
		// For simplicity, we check for the common pattern: D0xx (16-bit BEQ)
		if ((hw1 & 0xF000) === 0xD000 && lastCmpIndex === 0 && beqTargetForColor0 === 0) {
			// Extract branch offset for 16-bit BEQ
			const offsetByte = hw1 & 0xFF;
			// Sign-extend the offset
			const signedOffset = offsetByte < 128 ? offsetByte : offsetByte - 256;
			// BEQ target is current address + 4 + (offset * 2)
			beqTargetForColor0 = addr + 4 + (signedOffset * 2);
		}

		// Check if this address is the BEQ target for color 0
		const isAtBeqTarget = addr === beqTargetForColor0 && beqTargetForColor0 > 0;

		// Check if we're close to the last CMP (for colors 1-4)
		const distFromCmp = addr - lastCmpAddr;
		const isNearCmp = distFromCmp > 0 && distFromCmp <= 15;

		// Check for MOVW R0, #imm
		if ((hw1 & 0xF800) === 0xF000 && (isNearCmp || isAtBeqTarget)) {
			const opcode = (hw1 >> 4) & 0xF;
			if (opcode === 0x4) { // MOVW
				const hw2 = data[addr + 2] | (data[addr + 3] << 8);
				const rd = (hw2 >> 8) & 0xF;

				if (rd === 0) {
					// Extract immediate value
					// MOVW encoding: imm4 in bits [3:0] of hw1, i in bit 10 of hw1
					// imm3 in bits [14:12] of hw2, imm8 in bits [7:0] of hw2
					const i_bit = (hw1 >> 10) & 1;
					const imm4 = hw1 & 0xF;  // imm4 is in bits [3:0]
					const imm3 = (hw2 >> 12) & 0x7;
					const imm8 = hw2 & 0xFF;
					const imm = (imm4 << 12) | (i_bit << 11) | (imm3 << 8) | imm8;

					// Use the tracked CMP index, or 0 if at BEQ target
					const colorIndex = isAtBeqTarget ? 0 : lastCmpIndex;

					if (colorIndex >= 0) {
						result.push({ offset: addr, imm, colorIndex });

						// Only reset if not tracking color 0
						if (colorIndex !== 0) {
							lastCmpIndex = -1;
							lastCmpAddr = 0;
						}
					}
				}
			}
		}

		// Move to next instruction
		const is32bit = hw1 >= 0xE800;
		offset += is32bit ? 4 : 2;
	}

	// We expect exactly 5 colors (indices 0-4)
	if (result.length !== 5) {
		console.error(`Expected 5 color MOVW instructions, found ${result.length}`);
		return [];
	}

	// Sort by color index
	result.sort((a, b) => a.colorIndex - b.colorIndex);

	return result;
}

/**
 * Patch a switch_case function (Progress Bar or Marquee) with custom colors
 *
 * @param data Firmware data (will be modified in-place)
 * @param func The switch_case function to patch
 * @param newColors Array of 5 color values (for themes 0-4)
 * @returns Patch result with details
 */
export function patchSwitchCaseFunction(
	data: Uint8Array,
	func: ThemeFunction,
	newColors: number[]
): SwitchCasePatchResult {
	if (func.patternType !== 'switch_case') {
		throw new PatchError(
			`Function at 0x${func.addr.toString(16)} is not a switch_case function (type: ${func.patternType})`
		);
	}

	if (newColors.length !== 5) {
		throw new PatchError(
			`Switch-case functions require exactly 5 colors (got ${newColors.length})`
		);
	}

	// Find MOVW instructions
	const movwInstructions = findColorMovwInstructions(data, func.addr);

	if (movwInstructions.length === 0) {
		throw new PatchError(
			`No color MOVW instructions found in switch_case function at 0x${func.addr.toString(16)}`
		);
	}

	if (movwInstructions.length !== 5) {
		throw new PatchError(
			`Expected 5 color MOVW instructions but found ${movwInstructions.length} in function at 0x${func.addr.toString(16)}`
		);
	}

	// Extract original colors (already sorted by colorIndex)
	const originalColors = movwInstructions.map(m => m.imm);

	// Patch each MOVW instruction
	let patchesApplied = 0;
	for (const { offset, imm, colorIndex } of movwInstructions) {
		const newColor = newColors[colorIndex];

		if (newColor === undefined) {
			throw new PatchError(`Missing color for index ${colorIndex}`);
		}

		// Only patch if the color is different
		if (imm !== newColor) {
			// Encode new MOVW instruction
			const newMovw = encodeMovw(0, newColor);

			// Replace the 4-byte instruction
			data.set(newMovw, offset);
			patchesApplied++;
		}
	}

	return {
		funcAddr: func.addr,
		success: true,
		patchesApplied,
		originalColors,
		newColors
	};
}

/**
 * Extract current colors from a switch_case function
 *
 * @param data Firmware data
 * @param func The switch_case function
 * @returns Array of 5 color values
 */
export function extractSwitchCaseColors(
	data: Uint8Array,
	func: ThemeFunction
): number[] {
	if (func.patternType !== 'switch_case') {
		throw new PatchError(
			`Function at 0x${func.addr.toString(16)} is not a switch_case function`
		);
	}

	const movwInstructions = findColorMovwInstructions(data, func.addr);

	if (movwInstructions.length === 0) {
		// Return default colors if extraction fails
		return [0, 0, 0, 0, 0];
	}

	// Sort by color index and return colors
	movwInstructions.sort((a, b) => a.colorIndex - b.colorIndex);
	return movwInstructions.map(m => m.imm);
}
