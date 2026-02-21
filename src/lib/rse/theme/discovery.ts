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
	 * Detect Menu function by searching for MOV.W R12,#0 pattern
	 */
	static detectMenuFunction(
		data: Uint8Array,
		searchStart = 0x30000,
		searchEnd = 0x50000
	): [number, number] | null {
		const actualEnd = Math.min(searchEnd, data.length - 4);

		for (let addr = searchStart; addr < actualEnd; addr += 2) {
			// Check for MOV.W R12, #0 pattern
			if (data[addr] === MENU_SIGNATURE[0] &&
				data[addr + 1] === MENU_SIGNATURE[1] &&
				data[addr + 2] === MENU_SIGNATURE[2] &&
				data[addr + 3] === MENU_SIGNATURE[3]) {
				return [addr, addr];
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
			return { type: 'unknown' };
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
						return { type: 'standard' };
					}
				}
			}

			offset += is32bit ? 4 : 2;
		}

		return { type: 'unknown' };
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
 * Discover FLAC function using default parameters
 */
export function discoverFlacFunction(data: Uint8Array): [number, number] | null {
	return ThemeDiscovery.detectFlacFunction(data);
}

/**
 * Discover Menu function using default parameters
 */
export function discoverMenuFunction(data: Uint8Array): [number, number] | null {
	return ThemeDiscovery.detectMenuFunction(data);
}

/**
 * Find function start using default parameters
 */
export function findFunctionStart(data: Uint8Array, addr: number): number {
	return ThemeDiscovery.findFunctionStart(data, addr);
}
