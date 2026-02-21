/**
 * Patch Detector
 *
 * Detects existing patches in firmware and analyzes patch status.
 */

import type { Instruction } from './thumb/index.js';
import { ThumbDecoder } from './thumb/index.js';
import type { PatchInfo, NopSlide, PatchMetadata } from './types.js';
import { readPatchMetadata, crc16 } from './metadata.js';

/** Original FLAC instruction bytes (CMP R1,#4 + ITE EQ) */
const FLAC_ORIGINAL = new Uint8Array([0x04, 0x29, 0x0c, 0xbf]);

/** Original Menu instruction bytes (MOV.W R12, #0) */
const MENU_ORIGINAL = new Uint8Array([0x4f, 0xf0, 0x00, 0x0c]);

/**
 * Patch detection result
 */
interface DetectionResult {
	isPatched: boolean;
	status: string;
	patchType: PatchType;
	flacPatched: boolean;
	menuPatched: boolean;
	nopHasCode: boolean;
	confidence: number;
	metadata?: PatchMetadata;
}

type PatchType = 'none' | 'flac_only' | 'menu_only' | 'full' | 'unknown';

/**
 * Patch Detector Class
 */
export class PatchDetector {
	private readonly data: Readonly<Uint8Array>;
	readonly version: string;

	constructor(firmwareData: Uint8Array, version = 'Unknown') {
		this.data = firmwareData;
		this.version = version;
	}

	/**
	 * Check if instruction at addr is a BL instruction
	 */
	isBlInstruction(addr: number): boolean {
		if (addr + 4 > this.data.length) return false;

		const hw1 = this.data[addr] | (this.data[addr + 1] << 8);
		const hw2 = this.data[addr + 2] | (this.data[addr + 3] << 8);

		return (hw1 & 0xf800) === 0xf000 && (hw2 & 0xd000) === 0xd000;
	}

	/**
	 * Decode BL instruction to get target address
	 */
	decodeBlTarget(addr: number): number {
		if (addr + 4 > this.data.length) return 0;

		const hw1 = this.data[addr] | (this.data[addr + 1] << 8);
		const hw2 = this.data[addr + 2] | (this.data[addr + 3] << 8);

		const S = (hw1 >> 10) & 1;
		const imm10 = hw1 & 0x3ff;
		const J1 = (hw2 >> 13) & 1;
		const J2 = (hw2 >> 11) & 1;
		const imm11 = hw2 & 0x7ff;

		const I1 = ~(J1 ^ S) & 1;
		const I2 = ~(J2 ^ S) & 1;

		// imm10 is at bits [21:12], so shift by 12
		let imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | imm11;
		if (S) {
			imm32 = imm32 | 0xfe000000;
		}

		// Convert to signed 32-bit
		if (imm32 & 0x80000000) {
			imm32 = imm32 - 0x100000000;
		}

		return (addr + 4 + imm32) >>> 0;
	}

	/**
	 * Detect if FLAC function is patched
	 */
	detectFlacPatch(flacAddr: number): [boolean, string] {
		// Check if there's a BL instruction at FLAC address
		if (this.isBlInstruction(flacAddr)) {
			const target = this.decodeBlTarget(flacAddr);
			if (target > 0x100000 && target < 0x2000000) {
				return [true, `Patched (BL at 0x${flacAddr.toString(16).toUpperCase()} -> 0x${target.toString(16).toUpperCase()})`];
			}
		}

		// Check for original signature
		if (flacAddr + 4 <= this.data.length) {
			const currentBytes = this.data.slice(flacAddr, flacAddr + 4);
			if (this.bytesEqual(currentBytes, FLAC_ORIGINAL)) {
				return [false, 'Original'];
			}
		}

		// Scan forward for patch
		for (let offset = 0; offset < 500; offset += 2) {
			const checkAddr = flacAddr + offset;
			if (checkAddr + 4 > this.data.length) break;

			const currentBytes = this.data.slice(checkAddr, checkAddr + 4);

			if (this.bytesEqual(currentBytes, FLAC_ORIGINAL)) {
				return [false, 'Original'];
			} else if (this.isBlInstruction(checkAddr)) {
				const target = this.decodeBlTarget(checkAddr);
				if (target > 0x100000 && target < 0x2000000) {
					return [true, `Patched (BL at 0x${checkAddr.toString(16).toUpperCase()})`];
				}
			}
		}

		return [false, 'CMP+ITE pattern not found'];
	}

	/**
	 * Detect if Menu function is patched
	 */
	detectMenuPatch(menuAddr: number): [boolean, string] {
		// Check for BL instruction at Menu address
		if (this.isBlInstruction(menuAddr)) {
			const target = this.decodeBlTarget(menuAddr);
			if (target > 0x100000 && target < 0x2000000) {
				return [true, `Patched (BL at 0x${menuAddr.toString(16).toUpperCase()} -> 0x${target.toString(16).toUpperCase()})`];
			}
		}

		// Check for original signature
		if (menuAddr + 4 <= this.data.length) {
			const currentBytes = this.data.slice(menuAddr, menuAddr + 4);
			if (this.bytesEqual(currentBytes, MENU_ORIGINAL)) {
				return [false, 'Original'];
			}
		}

		// Scan forward for patch
		for (let offset = 0; offset < 200; offset += 2) {
			const checkAddr = menuAddr + offset;
			if (checkAddr + 4 > this.data.length) break;

			const currentBytes = this.data.slice(checkAddr, checkAddr + 4);

			if (this.bytesEqual(currentBytes, MENU_ORIGINAL)) {
				return [false, 'Original'];
			} else if (this.isBlInstruction(checkAddr)) {
				const target = this.decodeBlTarget(checkAddr);
				if (target > 0x100000 && target < 0x2000000) {
					return [true, `Patched (BL at 0x${checkAddr.toString(16).toUpperCase()})`];
				}
			}
		}

		return [false, 'MOVW R12 pattern not found'];
	}

	/**
	 * Read patch metadata from NOP region
	 */
	readPatchMetadata(nopSlide: NopSlide): PatchMetadata | null {
		const metadataStart = nopSlide.end - 51;
		if (metadataStart < 0) return null;

		return readPatchMetadata(this.data, metadataStart);
	}

	/**
	 * Detect patch status from firmware
	 */
	detectPatchStatus(flacAddr: number | null, menuAddr: number | null): DetectionResult {
		const result: DetectionResult = {
			isPatched: false,
			status: 'Not patched',
			patchType: 'none',
			flacPatched: false,
			menuPatched: false,
			nopHasCode: false,
			confidence: 0
		};

		// Check FLAC
		if (flacAddr !== null) {
			const [isPatched, status] = this.detectFlacPatch(flacAddr);
			result.flacPatched = isPatched;
		}

		// Check Menu
		if (menuAddr !== null) {
			const [isPatched, status] = this.detectMenuPatch(menuAddr);
			result.menuPatched = isPatched;
		}

		// Determine patch type
		const hasFlac = flacAddr !== null;
		const hasMenu = menuAddr !== null;
		const flacPatched = result.flacPatched;
		const menuPatched = result.menuPatched;

		if (!hasFlac && !hasMenu) {
			result.status = 'No theme functions found';
			result.patchType = 'none';
		} else if (flacPatched && menuPatched) {
			result.isPatched = true;
			result.status = 'Fully patched (FLAC + Menu)';
			result.patchType = 'full';
			result.confidence = 1.0;
		} else if (flacPatched) {
			result.isPatched = true;
			result.status = 'Partially patched (FLAC only)';
			result.patchType = 'flac_only';
			result.confidence = 0.8;
		} else if (menuPatched) {
			result.isPatched = true;
			result.status = 'Partially patched (Menu only)';
			result.patchType = 'menu_only';
			result.confidence = 0.8;
		} else {
			result.status = 'Theme functions detected, not patched';
			result.patchType = 'none';
			result.confidence = 0.0;
		}

		return result;
	}

	/**
	 * Check if NOP region has code (not all zeros)
	 */
	checkNopRegionHasCode(start: number, end: number): boolean {
		if (end > this.data.length) return false;

		for (let i = start; i < end; i++) {
			if (this.data[i] !== 0x00) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Find patch metadata in NOP slides
	 */
	findPatchMetadata(nopSlides: readonly NopSlide[]): PatchMetadata | null {
		for (const slide of nopSlides) {
			const metadata = this.readPatchMetadata(slide);
			if (metadata) {
				return metadata;
			}
		}
		return null;
	}

	/**
	 * Check if bytes are equal
	 */
	private bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
		if (a.length !== b.length) return false;

		for (let i = 0; i < a.length; i++) {
			if (a[i] !== b[i]) return false;
		}

		return true;
	}
}

/**
 * Create patch info from detection result
 */
export function createPatchInfo(detection: DetectionResult, patchTargetAddr = 0): PatchInfo {
	return {
		isPatched: detection.isPatched,
		patchType: detection.patchType,
		flacPatched: detection.flacPatched,
		menuPatched: detection.menuPatched,
		nopHasCode: false,
		patchTargetAddr,
		confidence: detection.confidence,
		metadata: null
	};
}

/**
 * Detect if firmware is patched by analyzing signature patterns
 */
export function detectFirmwarePatched(data: Uint8Array): boolean {
	// Count CMP+ITE patterns (FLAC signature)
	let cmpIteCount = 0;
	const searchEnd = Math.min(0x150000, data.length);

	for (let addr = 0x80000; addr < searchEnd; addr += 2) {
		if (data[addr] === 0x04 && data[addr + 1] === 0x29) {
			if (data[addr + 2] === 0x0c && data[addr + 3] === 0xbf) {
				cmpIteCount++;
			}
		}
	}

	// Count MOV.W R12,#0 + MOVW patterns (Menu signature)
	let menuPatternCount = 0;
	const menuSearchEnd = Math.min(0x60000, data.length);

	for (let addr = 0x30000; addr < menuSearchEnd; addr += 2) {
		if (
			data[addr] === 0x4f &&
			data[addr + 1] === 0xf0 &&
			data[addr + 2] === 0x00 &&
			data[addr + 3] === 0x0c
		) {
			// Check for MOVW within range
			for (const checkOffset of [4, 6, 8, 10, 12]) {
				const checkAddr = addr + checkOffset;
				if (checkAddr + 4 <= data.length) {
					const hw = data[checkAddr] | (data[checkAddr + 1] << 8);
					// MOVW: first halfword starts with 11110 i 100100 (0xF2xx or 0xF6xx)
					if ((hw & 0xfb00) === 0xf200) {
						menuPatternCount++;
						break;
					}
				}
			}
		}
	}

	// Firmware is considered patched if signatures are missing
	return cmpIteCount < 2 || menuPatternCount < 1;
}
