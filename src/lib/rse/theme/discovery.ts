/**
 * Theme Function Discovery
 *
 * Discovers theme-related functions in firmware by analyzing instruction patterns.
 * Ported from theme_extractor.py ThemeDiscovery class.
 */

import type { Instruction } from './thumb/index.js';
import { ThumbDecoder } from './thumb/index.js';
import type { ThemeFunction, FlacBehavior } from './types.js';
import { DiscoveryError } from './errors.js';

/**
 * Pattern matching results for function discovery
 */
interface PatternMatch {
	readonly addr: number;
	readonly confidence: number;
	readonly patternType: 'switch_case' | 'ite' | 'preload_store';
	readonly metadata: PatternMetadata;
}

interface PatternMetadata {
	readonly cmpCount?: number;
	readonly movwColors: readonly number[];
	readonly hasSeparator?: boolean;
	readonly register?: number;
}

/**
 * FLAC function signature bytes
 */
const FLAC_SIGNATURE = new Uint8Array([0x04, 0x29, 0x0c, 0xbf]); // CMP R1,#4 + ITE EQ
const MENU_SIGNATURE = new Uint8Array([0x4f, 0xf0, 0x00, 0x0c]); // MOV.W R12, #0

/**
 * Check if instruction at addr is a MOVW (32-bit Thumb instruction)
 * MOVW: first halfword starts with 11110 i 100100 (0xF2xx or 0xF6xx)
 */
function isMovwInstruction(data: Uint8Array, addr: number): boolean {
	if (addr + 4 > data.length) return false;
	const hw = data[addr] | (data[addr + 1] << 8);
	return (hw & 0xfb00) === 0xf200;
}

/**
 * Discover theme count by analyzing CMP patterns in firmware
 */
export function discoverThemeCount(data: Uint8Array): [number, string[]] {
	const decoder = new ThumbDecoder(data);
	const themeCountFreq = analyzeCmpPatterns(decoder, data);

	// Find the theme count with the highest frequency
	let bestEntry: [number, number] | null = null;
	for (const [k, v] of themeCountFreq.entries()) {
		if (k >= 5 && (!bestEntry || v > bestEntry[1])) {
			bestEntry = [k, v];
		}
	}

	if (bestEntry) {
		return [bestEntry[0], []];
	}

	// Fallback to checking for 4-theme support
	for (const [k, v] of themeCountFreq.entries()) {
		if (k >= 4 && (!bestEntry || v > bestEntry[1])) {
			bestEntry = [k, v];
		}
	}

	return bestEntry ? [bestEntry[0], []] : [5, ['Fallback - assuming 5 themes']];
}

/**
 * Analyze CMP patterns in firmware to determine theme count
 */
function analyzeCmpPatterns(decoder: ThumbDecoder, data: Uint8Array): Map<number, number> {
	const themeCountFreq = new Map<number, number>();
	const searchStart = 0x20000;
	const searchEnd = Math.min(0x150000, data.length);

	for (let addr = searchStart; addr < searchEnd; addr += 2) {
		const hw = decoder['readU16'](addr);
		if (hw === 0) continue;

		// Look for PUSH instructions as function boundaries
		const isPush = (hw & 0xff00) === 0xb500 || (hw & 0xffff0000) === 0x92d0000e;
		if (isPush) {
			const count = countThemeIndicesInFunction(decoder, addr);
			if (count > 0) {
				themeCountFreq.set(count, (themeCountFreq.get(count) ?? 0) + 1);
			}
		}
	}

	return themeCountFreq;
}

/**
 * Count theme indices in a function by analyzing CMP instructions
 */
function countThemeIndicesInFunction(decoder: ThumbDecoder, funcAddr: number): number {
	const themeIndices = new Set<number>();
	const maxScan = 500;

	for (let offset = 0; offset < maxScan;) {
		const hw = decoder['readU16'](funcAddr + offset);
		const is32bit = hw >= 0xe800;
		const instr = decoder.decode(funcAddr + offset);
		const mn = instr.mnemonic.toUpperCase();

		if (mn.includes('CMP')) {
			const imm = instr.imm;
			if (imm >= 0 && imm <= 15) {
				themeIndices.add(imm);
			}
		}

		offset += is32bit ? 4 : 2;
	}

	if (themeIndices.size === 0) return 0;

	// Find longest consecutive sequence
	let maxConsecutive = 0;
	const sortedIndices = Array.from(themeIndices).sort((a, b) => a - b);

	for (const start of sortedIndices) {
		let count = 0;
		for (let i = start; i <= Math.max(...themeIndices); i++) {
			if (themeIndices.has(i)) {
				count++;
			} else {
				break;
			}
		}
		if (count > maxConsecutive) {
			maxConsecutive = count;
		}
	}

	return maxConsecutive >= 2 ? maxConsecutive : 0;
}

/**
 * Theme Discovery Class
 */
export class ThemeDiscovery {
	constructor(private readonly decoder: ThumbDecoder) {}

	/**
	 * Detect FLAC function by searching for CMP+ITE pattern
	 */
	static detectFlacFunction(
		data: Uint8Array,
		searchStart = 0x80000,
		searchEnd = 0x100000
	): [number, number] | null {
		const actualEnd = Math.min(searchEnd, data.length - 4);

		for (let addr = searchStart; addr < actualEnd; addr += 2) {
			// Check for CMP R1,#4 pattern
			if (data[addr] === FLAC_SIGNATURE[0] &&
				data[addr + 1] === FLAC_SIGNATURE[1] &&
				data[addr + 2] === FLAC_SIGNATURE[2] &&
				data[addr + 3] === FLAC_SIGNATURE[3]) {
				return [addr, addr];
			}
		}

		return null;
	}

	/**
	 * Detect Menu function by searching for MOV.W R12,#0 pattern followed by MOVW instructions
	 *
	 * The theme menu function has the signature: MOV.W R12, #0 followed by MOVW instructions
	 * that load theme color addresses. We distinguish it from other functions by checking
	 * for the MOVW pattern.
	 */
	static detectMenuFunction(
		data: Uint8Array,
		searchStart = 0x30000,
		searchEnd = 0x50000
	): [number, number] | null {
		const actualEnd = Math.min(searchEnd, data.length - 20); // Need space for MOVW check

		for (let addr = searchStart; addr < actualEnd; addr += 2) {
			// Check for MOV.W R12, #0 pattern
			if (data[addr] === MENU_SIGNATURE[0] &&
				data[addr + 1] === MENU_SIGNATURE[1] &&
				data[addr + 2] === MENU_SIGNATURE[2] &&
				data[addr + 3] === MENU_SIGNATURE[3]) {
				// Check for MOVW instructions in the next few instructions
				let hasMovw = false;
				for (const checkOffset of [4, 6, 8, 10, 12]) {
					const checkAddr = addr + checkOffset;
					if (isMovwInstruction(data, checkAddr)) {
						hasMovw = true;
						break;
					}
				}

				if (hasMovw) {
					return [addr, addr];
				}
			}
		}

		return null;
	}

	/**
	 * Find function start by tracing back to PUSH instruction
	 */
	static findFunctionStart(data: Uint8Array, addr: number, maxBack = 200): number {
		for (let back = addr; back >= Math.max(0, addr - maxBack); back -= 2) {
			const hw = data[back] | (data[back + 1] << 8);

			// Check for PUSH patterns
			if ((hw & 0xfe00) === 0xb400 ||    // PUSH {Rlist}
			    (hw & 0xff00) === 0xb500 ||    // PUSH {Rlist, LR}
			    hw === 0xe92d) {                // STMDB SP!, {...}
				return back;
			}
		}

		return addr;
	}

	/**
	 * Detect FLAC function by analyzing behavior
	 */
	static detectFlacByContext(decoder: ThumbDecoder, funcAddr: number): FlacBehavior {
		const data = decoder.getData();
		let foundSeparator = false;
		const scanRange = 1200;

		// Step 1: Search for '|' character operation (MOVS Rx, #0x7C = 124 '|')
		for (let offset = 0; offset < scanRange;) {
			const hw = decoder.readU16(funcAddr + offset);
			const is32bit = hw >= 0xe800;
			const instr = decoder.decode(funcAddr + offset);

			if (instr.mnemonic.toUpperCase() === 'MOVS' && instr.imm === 0x7c) {
				foundSeparator = true;
				break;
			}

			offset += is32bit ? 4 : 2;
		}

		if (!foundSeparator) {
			return {
				type: 'unknown',
				isFlac: false,
				colorFor4: 0,
				colorForOther: 0,
				movwAddr4: '',
				movwInstr4: '',
				movwAddrOther: '',
				movwInstrOther: ''
			};
		}

		// Step 2: Search for FLAC color pattern after separator
		for (let offset = 0; offset < scanRange;) {
			const hw = decoder.readU16(funcAddr + offset);
			const is32bit = hw >= 0xe800;
			const instr = decoder.decode(funcAddr + offset);

			// Look for CMP Rx, #4 followed by IT
			if (instr.mnemonic.toUpperCase().includes('CMP') && instr.imm === 4) {
				// Check for IT instruction next
				if (offset + 4 <= scanRange) {
					const nextHw = decoder.readU16(funcAddr + offset + (is32bit ? 4 : 2));
					if ((nextHw & 0xff00) === 0xbf00 && (nextHw & 0xf) !== 0) {
						// Found CMP + IT pattern - this is standard FLAC behavior
						return {
							type: 'standard',
							isFlac: false,
							colorFor4: 0,
							colorForOther: 0,
							movwAddr4: '',
							movwInstr4: '',
							movwAddrOther: '',
							movwInstrOther: ''
						};
					}
				}
			}

			offset += is32bit ? 4 : 2;
		}

		return {
			type: 'unknown',
			isFlac: false,
			colorFor4: 0,
			colorForOther: 0,
			movwAddr4: '',
			movwInstr4: '',
			movwAddrOther: '',
			movwInstrOther: ''
		};
	}

	/**
	 * Detect switch_case pattern functions (Progress Bar and Marquee)
	 *
	 * Scans for CMP R0, #0-4 sequences followed by MOVW color loads.
	 * Distinguishes Progress Bar (has STRH) from Marquee (no STRH).
	 */
	detectSwitchCasePatterns(data: Uint8Array, seenAddrs: Set<number>): ThemeFunction[] {
		const functions: ThemeFunction[] = [];
		const searchEnd = Math.min(0x100000, data.length);

		// Collect CMP R0, #0-9 candidates
		const cmpCandidates: Array<{ addr: number; imm: number }> = [];

		for (let addr = 0; addr < searchEnd; addr += 2) {
			const hw = data[addr] | (data[addr + 1] << 8);

			// 16-bit CMP R0, #imm8: Encoding 00101 Rn imm8 (bits[15:11] = 00101)
			if ((hw >> 11) === 0b00101) {
				const rd = (hw >> 8) & 0x7;
				const imm = hw & 0xff;
				if (rd === 0 && imm < 10) {
					cmpCandidates.push({ addr, imm });
				}
			}
			// 32-bit CMP.W R0, #imm: F1BC 0Fxx
			else if (hw === 0xF1BC) {
				const hw2 = data[addr + 2] | (data[addr + 3] << 8);
				if ((hw2 & 0xFF00) === 0x0F00) {
					const imm = hw2 & 0xFF;
					if (imm < 10) {
						cmpCandidates.push({ addr, imm });
					}
				}
			}
		}

		// Group consecutive CMPs (within 20 bytes)
		let i = 0;
		while (i < cmpCandidates.length) {
			const consecutive = [cmpCandidates[i]];
			let j = i + 1;

			while (j < cmpCandidates.length) {
				if (cmpCandidates[j].addr - consecutive[consecutive.length - 1].addr <= 20) {
					consecutive.push(cmpCandidates[j]);
					j++;
				} else {
					break;
				}
			}

			// Need at least 3 consecutive CMPs with different immediates (0-4)
			if (consecutive.length >= 3) {
				const imms = new Set(consecutive.map(c => c.imm));
				if (imms.size >= 3 && Array.from(imms).every(v => v <= 4)) {
					const funcStart = ThemeDiscovery.findFunctionStart(data, consecutive[0].addr);

					if (funcStart && !seenAddrs.has(funcStart)) {
						seenAddrs.add(funcStart);

						// Collect MOVW color values from function
						const cmpStart = consecutive[0].addr;
						const funcEnd = consecutive[consecutive.length - 1].addr + 100;
						const preloadColors: Record<number, number> = {};

						let colorIdx = 0;
						for (let addr = cmpStart; addr < funcEnd && addr + 4 <= data.length;) {
							const hw = data[addr] | (data[addr + 1] << 8);

							// Check if MOVW (32-bit): (hw & 0xFBF0) == 0xF240
							if ((hw & 0xFBF0) === 0xF240) {
								const hw2 = data[addr + 2] | (data[addr + 3] << 8);
								const imm4 = hw & 0xF;
								const iBit = (hw >> 10) & 1;
								const imm3 = (hw2 >> 12) & 0x7;
								const rd = (hw2 >> 8) & 0xF;
								const imm8 = hw2 & 0xFF;
								const imm16 = (iBit << 11) | (imm4 << 12) | (imm3 << 8) | imm8;

								// Only collect MOVW to R0 (color register)
								if (rd === 0) {
									preloadColors[colorIdx++] = imm16;
								}
								addr += 4;
							} else {
								// Check if 32-bit instruction
								const is32bit = hw >= 0xe800;
								addr += is32bit ? 4 : 2;
							}
						}

						// Analyze behavior to determine UI element type
						const behavior = this.analyzeSwitchCaseBehavior(funcStart);

						// Distinguish Progress Bar vs Marquee by STRH presence
						let uiElement = 'Unknown UI Element';
						let funcType: 'progress' | 'marquee' | 'unknown' = 'unknown';

						if (behavior.cmpR12Count >= 5 && behavior.distinctColors === 5) {
							if (behavior.strhCount > 0) {
								uiElement = 'Progress Bar Background';
								funcType = 'progress';
							} else {
								uiElement = 'Marquee/Scrolling Text Overlay';
								funcType = 'marquee';
							}
						}

						functions.push({
							addr: funcStart,
							endAddr: funcEnd,
							patternType: 'switch_case',
							type: funcType,
							colorWrites: [],
							preloadColors,
							uiElement
						});
					}
				}
			}

			i = j > i + 1 ? j : i + 1;
		}

		return functions;
	}

	/**
	 * Analyze switch_case function behavior to distinguish Progress Bar from Marquee
	 */
	private analyzeSwitchCaseBehavior(funcAddr: number): {
		cmpR12Count: number;
		distinctColors: number;
		strhCount: number;
		colors: Set<number>;
	} {
		const scanRange = 200;
		const result = {
			cmpR12Count: 0,
			distinctColors: 0,
			strhCount: 0,
			colors: new Set<number>()
		};

		for (let offset = 0; offset < scanRange;) {
			const hw = this.decoder.readU16(funcAddr + offset);
			const is32bit = hw >= 0xe800;
			const instr = this.decoder.decode(funcAddr + offset);
			const mn = instr.mnemonic.toUpperCase();
			const ops = instr.operands;

			// Count CMP R12, #0-4
			if (mn.includes('CMP') && ops.includes('R12')) {
				const imm = instr.imm;
				if (imm >= 0 && imm <= 4) {
					result.cmpR12Count++;
				}
			}

			// Count MOVW R0 color values
			if (mn.includes('MOVW') && ops.includes('R0')) {
				const imm = instr.imm;
				if (imm !== undefined) {
					result.colors.add(imm);
				}
			}

			// Count STRH instructions
			if (mn.includes('STRH')) {
				result.strhCount++;
			}

			offset += is32bit ? 4 : 2;
		}

		result.distinctColors = result.colors.size;
		return result;
	}

	/**
	 * Find all theme functions in firmware
	 */
	scanFirmware(maxScanSize = 0x100000): ThemeFunction[] {
		const data = this.decoder.getData();
		const functions: ThemeFunction[] = [];
		const seenAddrs = new Set<number>();

		// Search for FLAC function
		const flacResult = ThemeDiscovery.detectFlacFunction(data);
		if (flacResult) {
			const [addr] = flacResult;
			const funcStart = ThemeDiscovery.findFunctionStart(data, addr);
			if (!seenAddrs.has(funcStart)) {
				seenAddrs.add(funcStart);
				const funcEnd = this.findFunctionEnd(funcStart, 500);
				const flacBehavior = ThemeDiscovery.detectFlacByContext(this.decoder, funcStart);

				functions.push({
					addr: funcStart,
					endAddr: funcEnd,
					patternType: 'ite',
					type: 'flac',
					colorWrites: [],
					preloadColors: {},
					uiElement: flacBehavior.type !== 'unknown' ? 'FLAC String Text' : 'Unknown UI Element'
				});
			}
		}

		// Search for Menu function
		const menuResult = ThemeDiscovery.detectMenuFunction(data);
		if (menuResult) {
			const [addr] = menuResult;
			const funcStart = ThemeDiscovery.findFunctionStart(data, addr);
			if (!seenAddrs.has(funcStart)) {
				seenAddrs.add(funcStart);
				const funcEnd = this.findFunctionEnd(funcStart, 500);

				functions.push({
					addr: funcStart,
					endAddr: funcEnd,
					patternType: 'preload_store',
					type: 'menu',
					colorWrites: [],
					preloadColors: {},
					uiElement: 'Menu Text Colors'
				});
			}
		}

		// Search for switch_case pattern functions (Progress Bar and Marquee)
		const switchCaseFunctions = this.detectSwitchCasePatterns(data, seenAddrs);
		for (const func of switchCaseFunctions) {
			functions.push(func);
		}

		return functions;
	}

	/**
	 * Find function end by searching for POP + BX LR sequence
	 */
	private findFunctionEnd(addr: number, maxSearch = 400): number {
		const data = this.decoder.getData();
		const searchEnd = Math.min(addr + maxSearch, data.length);
		let itBlockRemaining = 0;
		let lastPopBxAddr = 0;

		while (addr < searchEnd) {
			const hw = this.decoder.readU16(addr);
			const is32bit = hw >= 0xe800;
			const instrSize = is32bit ? 4 : 2;

			// Handle IT block
			if (itBlockRemaining > 0) {
				itBlockRemaining--;
				addr += instrSize;
				continue;
			}

			// Check IT instruction
			if ((hw & 0xff00) === 0xbf00) {
				const mask = hw & 0xf;
				if (mask !== 0) {
					// Calculate IT block size from mask
					if (mask & 0x1) itBlockRemaining = 4;
					else if (mask & 0x2) itBlockRemaining = 3;
					else if (mask & 0x4) itBlockRemaining = 2;
					else itBlockRemaining = 1;
				}
				addr += instrSize;
				continue;
			}

			// Check POP + BX LR sequence
			if ((hw & 0xff00) === 0xbc00) {
				const nextAddr = addr + 2;
				if (nextAddr + 2 <= data.length) {
					const nextHw = this.decoder.readU16(nextAddr);
					if (nextHw === 0x4770) {
						lastPopBxAddr = nextAddr + 2;
					}
				}
			}

			addr += instrSize;
		}

		return lastPopBxAddr > 0 ? lastPopBxAddr : addr;
	}

	/**
	 * Check if instruction at address is 32-bit
	 */
	private is32BitInstruction(addr: number): boolean {
		if (addr + 2 > this.decoder['getData']().length) return false;
		const hw = this.decoder['readU16'](addr);
		return (hw & 0xf800) === 0xe800 || (hw & 0xf800) === 0xf000 || (hw & 0xf800) === 0xf800;
	}
}

/**
 * Check if data at address is a BL instruction
 */
function isBlInstruction(data: Uint8Array, addr: number): boolean {
	if (addr + 4 > data.length) return false;
	const hw1 = data[addr] | (data[addr + 1] << 8);
	const hw2 = data[addr + 2] | (data[addr + 3] << 8);
	return (hw1 & 0xf800) === 0xf000 && (hw2 & 0xd000) === 0xd000;
}

/**
 * Discover FLAC function using default parameters
 *
 * First tries signature-based detection for patched firmware, then falls back to
 * CMP+ITE pattern search for unpatched firmware.
 */
export function discoverFlacFunction(data: Uint8Array, version?: string): [number, number] | null {
	// Try signature-based detection first (for patched firmware)
	const patches = discoverPatchesBySignature(data);
	if (patches) {
		// For patched firmware, both funcAddr and patchAddr are the BL address
		return [patches.flacBlAddr, patches.flacBlAddr];
	}

	// Fall back to CMP+ITE pattern search (for unpatched firmware)
	const result = ThemeDiscovery.detectFlacFunction(data);
	if (result) {
		return result;
	}

	return null;
}

/**
 * Discover Menu function using default parameters
 *
 * First tries signature-based detection for patched firmware, then falls back to
 * MOV.W pattern search for unpatched firmware.
 */
export function discoverMenuFunction(data: Uint8Array, version?: string): [number, number] | null {
	// Try signature-based detection first (for patched firmware)
	const patches = discoverPatchesBySignature(data);
	if (patches) {
		// For patched firmware, both funcAddr and patchAddr are the BL address
		return [patches.menuBlAddr, patches.menuBlAddr];
	}

	// Fall back to MOV.W pattern search (for unpatched firmware)
	const result = ThemeDiscovery.detectMenuFunction(data);
	if (result) {
		return result;
	}

	return null;
}

/**
 * Find function start using default parameters
 */
export function findFunctionStart(data: Uint8Array, addr: number): number {
	return ThemeDiscovery.findFunctionStart(data, addr);
}

/**
 * Check if code at addr has the signature of our generated patch code.
 *
 * Our patch code has distinctive MOVW/MOVT instruction pairs in sequence.
 * Normal firmware code rarely has this pattern.
 */
function isPatchCodeSignature(data: Uint8Array, addr: number): boolean {
	if (addr + 64 > data.length) return false;

	// Count MOVW/MOVT pairs (MOVW followed by MOVT for same register)
	let pairCount = 0;

	// Iterate by 4 bytes since MOVW/MOVT are 32-bit instructions
	for (let i = addr; i < Math.min(addr + 64, data.length - 7); i += 4) {
		const hw1 = data[i] | (data[i + 1] << 8);
		const hw2 = data[i + 2] | (data[i + 3] << 8);

		// Check if first instruction is MOVW
		if ((hw1 & 0xf800) === 0xf000) {
			const opcode1 = (hw1 >> 4) & 0xf;
			if (opcode1 === 0x4) {  // MOVW
				const rd1 = (hw2 >> 8) & 0xf;

				// Check if next instruction is MOVT for same register
				const hw1Next = data[i + 4] | (data[i + 5] << 8);
				const hw2Next = data[i + 6] | (data[i + 7] << 8);

				if ((hw1Next & 0xf800) === 0xf000) {
					const opcode2 = (hw1Next >> 4) & 0xf;
					if (opcode2 === 0xc) {  // MOVT
						const rd2 = (hw2Next >> 8) & 0xf;
						if (rd1 === rd2) {  // Same register = MOVW/MOVT pair
							pairCount++;
						}
					}
				}
			}
		}
	}

	// Our patch code has 6+ MOVW/MOVT pairs in first 64 bytes
	return pairCount >= 6;
}

/**
 * Decode BL instruction target address.
 */
function decodeBlTarget(data: Uint8Array, addr: number): number {
	const hw1 = data[addr] | (data[addr + 1] << 8);
	const hw2 = data[addr + 2] | (data[addr + 3] << 8);

	const S = (hw1 >> 10) & 1;
	const J1 = (hw2 >> 13) & 1;
	const J2 = (hw2 >> 11) & 1;
	const imm10 = hw1 & 0x3ff;
	const imm11 = hw2 & 0x7ff;

	const I1 = (~(J1 ^ S)) & 1;
	const I2 = (~(J2 ^ S)) & 1;

	const imm25 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1);
	let imm32 = imm25 << 1;

	if (S) {
		imm32 |= 0xfe000000;
	}

	return addr + 4 + imm32;
}

/**
 * Discover patches by searching for BL instructions that branch to our patch code.
 *
 * Returns both the BL addresses and the NOP slide address if found.
 */
export function discoverPatchesBySignature(data: Uint8Array): {
	flacBlAddr: number;
	menuBlAddr: number;
	nopSlideAddr: number;
} | null {
	const blInstructions: Array<{ blAddr: number; target: number }> = [];

	// Find all BL instructions
	for (let i = 0; i < data.length - 4; i += 2) {
		const hw1 = data[i] | (data[i + 1] << 8);
		const hw2 = data[i + 2] | (data[i + 3] << 8);

		if ((hw1 & 0xf800) === 0xf000 && (hw2 & 0xd000) === 0xd000) {
			const target = decodeBlTarget(data, i);
			if (target >= 0 && target < data.length) {
				// Check if target has our patch code signature
				if (isPatchCodeSignature(data, target)) {
					blInstructions.push({ blAddr: i, target });
				}
			}
		}
	}

	// We should have exactly 2 BLs pointing to our patch code (FLAC and Menu)
	if (blInstructions.length >= 2) {
		// Sort by target address (FLAC is usually first)
		blInstructions.sort((a, b) => a.target - b.target);

		const flacBl = blInstructions[0].blAddr;
		const nopSlide = blInstructions[0].target;

		// Menu BL should be the second one (higher target address within same NOP slide)
		let menuBl = 0;
		for (const { blAddr, target } of blInstructions.slice(1)) {
			if (Math.abs(target - nopSlide) < 1024) {  // Same NOP slide
				menuBl = blAddr;
				break;
			}
		}

		return { flacBlAddr: flacBl, menuBlAddr: menuBl, nopSlideAddr: nopSlide };
	}

	return null;
}
