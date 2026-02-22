/**
 * Theme Patcher
 *
 * Main patching module that applies theme color patches to firmware.
 * Uses detection, NOP slide finding, and instruction encoding to patch.
 */

import { encodeBl, encodeMovw, encodePush } from './thumb/encoders.js';
import { fileIO } from '../utils/file-io.js';
import { ThumbDecoder } from './thumb/index.js';
import { NopSlideFinder } from './nop-slide.js';
import { PatchDetector } from './detector.js';
import { createPatchMetadata, writePatchMetadata } from './metadata.js';
import { discoverFlacFunction, discoverMenuFunction, findFunctionStart } from './discovery.js';
import {
	type PatchResult,
	type PatchPoint,
	type PatchPointInfo,
	type PatchAnalysisResult,
	type NopSlide,
	type PatchMetadata,
	type PatchInfo
} from './types.js';
import {
	ThemeError,
	PatchError,
	ValidationError,
	AlreadyPatchedError,
	CapacityError,
	throwThemeError
} from './errors.js';

/**
 * Theme Patcher Class
 *
 * Patches firmware to use custom theme colors.
 */
export class ThemePatcher {
	private readonly data: Uint8Array;
	private readonly decoder: ThumbDecoder;
	private readonly detector: PatchDetector;
	private readonly finder: NopSlideFinder;
	readonly version: string;

	/**
	 * Create a new ThemePatcher
	 */
	constructor(firmwareData: Uint8Array, version = 'Unknown') {
		this.data = firmwareData;
		this.version = version;
		this.decoder = new ThumbDecoder(firmwareData);
		this.detector = new PatchDetector(firmwareData, version);
		this.finder = new NopSlideFinder(firmwareData);
	}

	/**
	 * Analyze firmware for patching
	 */
	analyze(): PatchAnalysisResult {
		const flacResult = discoverFlacFunction(this.data);
		const menuResult = discoverMenuFunction(this.data);

		const themeFunctions: PatchPointInfo[] = [];

		if (flacResult) {
			const [funcAddr, patchAddr] = flacResult;
			themeFunctions.push({
				type: 'flac',
				funcAddr,
				patchAddr,
				functionStart: findFunctionStart(this.data, funcAddr)
			});
		}

		if (menuResult) {
			const [funcAddr, patchAddr] = menuResult;
			themeFunctions.push({
				type: 'menu',
				funcAddr,
				patchAddr,
				functionStart: findFunctionStart(this.data, funcAddr)
			});
		}

		// Find NOP slides
		const nopSlides = this.finder.findAllSlides();

		// Check if already patched
		const flacAddr = flacResult ? flacResult[1] : null;
		const menuAddr = menuResult ? menuResult[1] : null;
		const patchStatus = this.detector.detectPatchStatus(flacAddr, menuAddr);

		return {
			version: this.version,
			themeFunctions,
			nopSlides,
			canPatch: themeFunctions.length > 0 && nopSlides.length > 0,
			patchStatus
		};
	}

	/**
	 * Patch firmware with custom colors
	 */
	patch(
		flacColors: number[],
		menuColors: number[],
		outputPath: string,
		writeFile = true
	): PatchResult {
		try {
			// Validate color counts
			if (flacColors.length !== 5) {
				throw new ValidationError('FLAC colors must have exactly 5 values');
			}
			if (menuColors.length !== 15) {
				throw new ValidationError('Menu colors must have exactly 15 values');
			}

			// Analyze firmware
			const analysis = this.analyze();

			if (!analysis.canPatch) {
				throw new PatchError('Firmware cannot be patched: theme functions or NOP slides not found');
			}

			// Check if already patched
			if (analysis.patchStatus.isPatched) {
				throw new AlreadyPatchedError('Firmware is already patched');
			}

			// Find best NOP slide
			// Need: FLAC (32 + 44) + Menu (128 + 124) + Metadata (51) = 379 bytes minimum
			// But we can overlap: max(32 + 44, 128 + 124) + 51 = 252 + 51 = 303 bytes
			const funcAddrs = analysis.themeFunctions.map(f => f.funcAddr);
			const requiredSize = 303; // Minimum size needed
			const nopSlide = this.finder.selectBestSlide(funcAddrs, requiredSize);

			if (!nopSlide) {
				throw new CapacityError('No suitable NOP slide found for patch code');
			}

			// Create patch data
			const patchData = this.createPatchData(flacColors, menuColors, nopSlide);

			// Apply patches
			const patchedData = new Uint8Array(this.data);
			const patchPoints: Record<string, PatchPoint> = {};

			// Patch FLAC function
			const flacFunc = analysis.themeFunctions.find(f => f.type === 'flac');
			if (flacFunc) {
				this.applyPatch(patchedData, flacFunc.patchAddr, patchData.flacCodeAddr);
				patchPoints['flac'] = {
					type: 'flac',
					funcAddr: flacFunc.funcAddr,
					patchAddr: flacFunc.patchAddr,
					originalBytes: this.bytesToHex(this.data.slice(flacFunc.patchAddr, flacFunc.patchAddr + 4)),
					newBytes: this.bytesToHex(patchedData.slice(flacFunc.patchAddr, flacFunc.patchAddr + 4))
				};
			}

			// Patch Menu function
			const menuFunc = analysis.themeFunctions.find(f => f.type === 'menu');
			if (menuFunc) {
				this.applyPatch(patchedData, menuFunc.patchAddr, patchData.menuCodeAddr);
				patchPoints['menu'] = {
					type: 'menu',
					funcAddr: menuFunc.funcAddr,
					patchAddr: menuFunc.patchAddr,
					originalBytes: this.bytesToHex(this.data.slice(menuFunc.patchAddr, menuFunc.patchAddr + 4)),
					newBytes: this.bytesToHex(patchedData.slice(menuFunc.patchAddr, menuFunc.patchAddr + 4))
				};
			}

			// Write patch code to NOP slide
			this.writePatchCode(patchedData, nopSlide, patchData);

			// Write metadata
			const metadata = createPatchMetadata(
				Math.floor(Date.now() / 1000),
				flacColors,
				menuColors
			);
			const metadataBytes = writePatchMetadata(metadata);
			const metadataAddr = nopSlide.end - 51;
			patchedData.set(metadataBytes, metadataAddr);

			// Write to file if requested
			if (writeFile) {
				fileIO.writeFileSync(outputPath, patchedData);
			}

			return {
				success: true,
				nopSlide,
				metadataAddr,
				patchPoints
			};
		} catch (error) {
			throwThemeError(error, PatchError, 'Failed to patch firmware');
		}
	}

	/**
	 * Create patch data structure
	 *
	 * Layout matches Python theme_patcher.py:
	 * - Offset 0-31: Reserved for protection instruction (32 bytes)
	 * - Offset 32: FLAC handler code
	 * - Offset 128: Menu handler code
	 * - End-51: Metadata
	 */
	private createPatchData(
		flacColors: number[],
		menuColors: number[],
		nopSlide: NopSlide
	): { flacCodeAddr: number; menuCodeAddr: number; code: Uint8Array } {
		// Reserve space for metadata at the end of NOP slide (51 bytes)
		const METADATA_SIZE = 51;
		const PROTECTION_SIZE = 32;

		// Match Python offsets exactly
		const flacCodeAddr = nopSlide.start + PROTECTION_SIZE;
		const menuCodeAddr = nopSlide.start + 128;

		// Generate handlers
		const flacHandler = this.generateFlacHandler(flacColors, flacCodeAddr);
		const menuHandler = this.generateMenuHandler(menuColors, menuCodeAddr);

		// Verify total code size fits in available space
		const maxCodeSize = nopSlide.size - METADATA_SIZE;
		const totalCodeSize = Math.max(flacHandler.length + PROTECTION_SIZE, menuHandler.length);
		if (totalCodeSize > maxCodeSize) {
			throw new ThemeError(
				`Patch code (${totalCodeSize} bytes) exceeds available NOP slide space (${maxCodeSize} bytes)`
			);
		}

		// Combine handlers with Python-compatible layout
		const code = new Uint8Array(nopSlide.size);
		code.set(flacHandler, PROTECTION_SIZE);
		code.set(menuHandler, 128);

		return {
			flacCodeAddr,
			menuCodeAddr,
			code
		};
	}

	/**
	 * Generate FLAC handler code
	 */
	private generateFlacHandler(colors: number[], returnAddr: number): Uint8Array {
		const code: number[] = [];

		// PUSH {LR}
		code.push(...encodePush([14]));

		// Load colors using MOVW+MOVT pairs
		for (let i = 0; i < colors.length; i++) {
			const reg = 4 + i; // R4-R8
			const color = colors[i];

			// MOVW R{i}, #color_low
			code.push(...encodeMovw(reg, color & 0xffff));

			// MOVT R{i}, #color_high
			const movt = this.encodeMovt(reg, (color >> 16) & 0xffff);
			code.push(...movt);
		}

		// POP {PC}
		code.push(...[0xbd, 0x00]); // POP {PC} is actually POP {LR} then BX LR, use BX LR instead
		code.pop();
		code.pop();
		code.push(0x70, 0x47); // BX LR

		return new Uint8Array(code);
	}

	/**
	 * Generate Menu handler code
	 */
	private generateMenuHandler(colors: number[], returnAddr: number): Uint8Array {
		const code: number[] = [];

		// PUSH {LR}
		code.push(...encodePush([14]));

		// Load colors using MOVW+MOVT pairs
		for (let i = 0; i < colors.length; i++) {
			const reg = i;
			const color = colors[i];

			// MOVW R{i}, #color_low
			code.push(...encodeMovw(reg, color & 0xffff));

			// MOVT R{i}, #color_high
			const movt = this.encodeMovt(reg, (color >> 16) & 0xffff);
			code.push(...movt);
		}

		// POP {PC}
		code.pop();
		code.pop();
		code.push(0x70, 0x47); // BX LR

		return new Uint8Array(code);
	}

	/**
	 * Encode MOVT instruction
	 */
	private encodeMovt(rd: number, imm16: number): Uint8Array {
		const i4 = (imm16 >> 12) & 0xf;
		const i3 = (imm16 >> 11) & 0x1;
		const imm8 = imm16 & 0xff;

		const hw1 = 0xf2c0 | ((i4 ^ 1) << 6) | (i3 << 5) | ((imm8 >> 4) & 0x7f);
		const hw2 = ((rd & 0xf) << 8) | ((imm8 & 0xf) << 4);

		return new Uint8Array([hw1 & 0xff, hw1 >> 8, hw2 & 0xff, hw2 >> 8]);
	}

	/**
	 * Apply patch at address
	 */
	private applyPatch(data: Uint8Array, patchAddr: number, targetAddr: number): void {
		const blInstruction = encodeBl(patchAddr, targetAddr);
		data.set(blInstruction, patchAddr);
	}

	/**
	 * Write patch code to NOP slide
	 */
	private writePatchCode(
		data: Uint8Array,
		nopSlide: NopSlide,
		patchData: { flacCodeAddr: number; menuCodeAddr: number; code: Uint8Array }
	): void {
		data.set(patchData.code, nopSlide.start);
	}

	/**
	 * Convert bytes to hex string
	 */
	private bytesToHex(bytes: Uint8Array): string {
		return Array.from(bytes)
			.map(b => b.toString(16).padStart(2, '0').toUpperCase())
			.join(' ');
	}
}

/**
 * Convenience function to patch firmware
 */
export function patchFirmware(
	firmwareData: Uint8Array,
	flacColors: number[],
	menuColors: number[],
	outputPath: string
): PatchResult {
	const patcher = new ThemePatcher(firmwareData);
	return patcher.patch(flacColors, menuColors, outputPath, true);
}

// Re-export types and functions for convenience
export type { NopSlide, PatchMetadata, PatchPoint, PatchResult, PatchPointInfo, PatchAnalysisResult, PatchInfo };
export { NopSlideFinder, PatchDetector };
