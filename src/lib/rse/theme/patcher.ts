/**
 * Theme Patcher
 *
 * Main patching module that applies theme color patches to firmware.
 * Uses detection, NOP slide finding, and instruction encoding to patch.
 */

import { encodeBl, encodeMovw, encodeMovt } from './thumb/encoders.js';
import { fileIO } from '../utils/file-io.js';
import { NopSlideFinder } from './nop-slide.js';
import { PatchDetector } from './detector.js';
import { createPatchMetadata, writePatchMetadata } from './metadata.js';
import { discoverFlacFunction, discoverMenuFunction, findFunctionStart, discoverPatchesBySignature } from './discovery.js';
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
	private readonly detector: PatchDetector;
	private readonly finder: NopSlideFinder;
	readonly version: string;

	/**
	 * Create a new ThemePatcher
	 */
	constructor(firmwareData: Uint8Array, version = 'Unknown') {
		this.data = firmwareData;
		this.version = version;
		this.detector = new PatchDetector(firmwareData, version);
		this.finder = new NopSlideFinder(firmwareData);
	}

	/**
	 * Analyze firmware for patching
	 */
	analyze(): PatchAnalysisResult {
		const flacResult = discoverFlacFunction(this.data, this.version);
		const menuResult = discoverMenuFunction(this.data, this.version);

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
	 * Find existing NOP slide from patched firmware
	 *
	 * Uses signature-based discovery to find our patch code and NOP slide.
	 */
	private findExistingNopSlide(): NopSlide | null {
		// Use signature-based discovery to find existing patches
		const patches = discoverPatchesBySignature(this.data);
		if (!patches) {
			return null;
		}

		const { nopSlideAddr } = patches;

		// Find NOP slide boundaries by searching for NOP bytes (0x00)
		// Start from the code location and search backward to find the start
		let start = nopSlideAddr;
		while (start > 0 && this.data[start - 1] === 0x00) {
			start--;
		}

		// For the end, search forward from beyond the handler code
		// (handlers are typically < 512 bytes)
		let end = nopSlideAddr + 512;
		while (end < this.data.length && this.data[end] === 0x00) {
			end++;
		}

		// Cap at a reasonable size (typical NOP slide is a few hundred bytes)
		const nopSlideSize = Math.min(end - start, 1024);  // Cap at 1KB for safety

		return {
			start,
			end: start + nopSlideSize,
			size: nopSlideSize,
			source: 'existing-patch',
			isActive: true,
			referenceCount: 0
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

			// Check if already patched - if so, find existing NOP slide for re-patching
			let nopSlide: NopSlide;
			let isRepatch = false;

			if (analysis.patchStatus.isPatched) {
				console.error('[INFO] Firmware is already patched - attempting re-patch');
				const existingNopSlide = this.findExistingNopSlide();
				if (!existingNopSlide) {
					throw new PatchError('Cannot re-patch: unable to locate existing NOP slide');
				}
				nopSlide = existingNopSlide;
				isRepatch = true;
				console.error(`[INFO] Re-using existing NOP slide: 0x${nopSlide.start.toString(16)} - 0x${nopSlide.end.toString(16)} (${nopSlide.size} bytes)`);
			} else {
				// Find best NOP slide
				// Calculate required size dynamically based on actual handler sizes
				// We'll generate handlers first to get their sizes
				const tempFlacHandler = this.generateFlacHandler(flacColors);
				const tempMenuHandler = this.generateMenuHandler(menuColors);
				const tempMetadata = createPatchMetadata(
					Math.floor(Date.now() / 1000),
					flacColors,
					menuColors
				);
				const tempMetadataBytes = writePatchMetadata(tempMetadata);

				// Calculate required size:
				// - FLAC handler: tempFlacHandler.length
				// - Menu handler: tempMenuHandler.length (aligned after FLAC)
				// - Metadata: tempMetadataBytes.length
				const PROTECTION_SIZE = 0;
				const ALIGNMENT = 4;
				const flacEnd = PROTECTION_SIZE + tempFlacHandler.length;
				const menuStart = Math.ceil(flacEnd / ALIGNMENT) * ALIGNMENT;
				const requiredSize = menuStart + tempMenuHandler.length + tempMetadataBytes.length;

				const funcAddrs = analysis.themeFunctions.map(f => f.funcAddr);
				const selectedSlide = this.finder.selectBestSlide(funcAddrs, requiredSize);

				if (!selectedSlide) {
					throw new CapacityError('No suitable NOP slide found for patch code');
				}

				nopSlide = selectedSlide;

				// DEBUG: Log selected NOP slide details
				console.error(`[DEBUG] Selected NOP slide: 0x${nopSlide.start.toString(16)} - 0x${nopSlide.end.toString(16)} (${nopSlide.size} bytes)`);
				console.error(`[DEBUG] Required size: ${requiredSize} bytes`);
			}

			// Create patch data (skip safety check for re-patch)
			const patchData = this.createPatchData(flacColors, menuColors, nopSlide, isRepatch);

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

			// Write metadata (using dynamic address from createPatchData)
			const metadata = createPatchMetadata(
				Math.floor(Date.now() / 1000),
				flacColors,
				menuColors
			);
			const metadataBytes = writePatchMetadata(metadata);
			patchedData.set(metadataBytes, patchData.metadataAddr);

			// Write to file if requested
			if (writeFile) {
				fileIO.writeFileSync(outputPath, patchedData);
			}

			return {
				success: true,
				nopSlide,
				metadataAddr: patchData.metadataAddr,
				patchPoints
			};
		} catch (error) {
			throwThemeError(error, PatchError, 'Failed to patch firmware');
		}
	}

	/**
	 * Create patch data structure
	 *
	 * Layout is dynamically calculated:
	 * - Start: Protection/reserved area (configurable, default 32 bytes for B instruction)
	 * - After protection: FLAC handler code
	 * - After FLAC (aligned): Menu handler code
	 * - End: Metadata
	 *
	 * @param isRepatch - Skip safety checks when re-patching existing firmware
	 */
	private createPatchData(
		flacColors: number[],
		menuColors: number[],
		nopSlide: NopSlide,
		isRepatch = false
	): { flacCodeAddr: number; menuCodeAddr: number; code: Uint8Array; metadataAddr: number } {
		// DEBUG: Log input NOP slide
		console.error(`[DEBUG] createPatchData: nopSlide.start = 0x${nopSlide.start.toString(16)}, size = ${nopSlide.size}`);

		// Calculate metadata size from the actual metadata structure
		const metadata = createPatchMetadata(
			Math.floor(Date.now() / 1000),
			flacColors,
			menuColors
		);
		const metadataBytes = writePatchMetadata(metadata);
		const METADATA_SIZE = metadataBytes.length;

		// No protection area - code starts at beginning of NOP slide
		const PROTECTION_SIZE = 0;

		// Alignment for Menu handler (4-byte alignment for ARM instructions)
		const ALIGNMENT = 4;

		// Generate handlers first so we know their sizes
		const flacHandler = this.generateFlacHandler(flacColors);
		const menuHandler = this.generateMenuHandler(menuColors);

		// Dynamically calculate offsets
		const flacCodeOffset = PROTECTION_SIZE;
		const flacCodeEnd = flacCodeOffset + flacHandler.length;

		// Align menu handler start
		const menuCodeOffset = Math.ceil(flacCodeEnd / ALIGNMENT) * ALIGNMENT;
		const menuCodeEnd = menuCodeOffset + menuHandler.length;

		// Metadata goes at the end
		const metadataOffset = nopSlide.size - METADATA_SIZE;

		// Calculate absolute addresses
		const flacCodeAddr = nopSlide.start + flacCodeOffset;
		const menuCodeAddr = nopSlide.start + menuCodeOffset;
		const metadataAddr = nopSlide.start + metadataOffset;

		// Verify everything fits
		if (menuCodeEnd > metadataOffset) {
			throw new CapacityError(
				`Not enough space in NOP slide:\n` +
				`  Available: ${nopSlide.size} bytes\n` +
				`  FLAC handler: ${flacHandler.length} bytes (offset ${flacCodeOffset})\n` +
				`  Menu handler: ${menuHandler.length} bytes (offset ${menuCodeOffset})\n` +
				`  Metadata: ${METADATA_SIZE} bytes (offset ${metadataOffset})\n` +
				`  Required: ${menuCodeEnd + METADATA_SIZE} bytes\n` +
				`  Short by: ${menuCodeEnd - metadataOffset} bytes`
			);
		}

		// SAFETY CHECK: Verify all bytes to be overwritten are NOPs (0x00)
		// Skip safety check when re-patching since we're overwriting our own code
		if (!isRepatch) {
			this.verifyNopSlideSafety(nopSlide, [
				{ start: nopSlide.start + flacCodeOffset, end: nopSlide.start + flacCodeEnd, name: 'FLAC handler' },
				{ start: nopSlide.start + menuCodeOffset, end: nopSlide.start + menuCodeEnd, name: 'Menu handler' },
				{ start: metadataAddr, end: nopSlide.end, name: 'metadata' }
			]);
		}

		// Build the complete code buffer
		const code = new Uint8Array(nopSlide.size);
		code.set(flacHandler, flacCodeOffset);
		code.set(menuHandler, menuCodeOffset);
		// Metadata will be written separately in patch() method

		return {
			flacCodeAddr,
			menuCodeAddr,
			code,
			metadataAddr
		};
	}

	/**
	 * Verify that all bytes to be written are NOPs (0x00)
	 *
	 * This ensures we don't overwrite non-NOP-slide code or data.
	 * Takes an array of ranges to check, making it flexible for different layouts.
	 */
	private verifyNopSlideSafety(
		nopSlide: NopSlide,
		ranges: { start: number; end: number; name: string }[]
	): void {
		const nonNopPositions: { offset: number; value: number; range: string }[] = [];

		for (const range of ranges) {
			// Clamp range to NOP slide boundaries
			const clampedStart = Math.max(range.start, nopSlide.start);
			const clampedEnd = Math.min(range.end, nopSlide.end);

			for (let offset = clampedStart; offset < clampedEnd; offset++) {
				if (this.data[offset] !== 0x00) {
					nonNopPositions.push({ offset, value: this.data[offset], range: range.name });
				}
			}
		}

		if (nonNopPositions.length > 0) {
			const message = `Safety check failed: NOP slide contains non-NOP bytes\n` +
				`NOP Slide: 0x${nopSlide.start.toString(16)} - 0x${nopSlide.end.toString(16)} (${nopSlide.size} bytes)\n` +
				`Found ${nonNopPositions.length} non-NOP bytes:\n` +
				nonNopPositions.slice(0, 10).map(p =>
					`  0x${p.offset.toString(16)}: 0x${p.value.toString(16).padStart(2, '0')} (${p.range})`
				).join('\n') +
				(nonNopPositions.length > 10 ? `\n  ... and ${nonNopPositions.length - 10} more` : '');
			throw new ThemeError(message);
		}
	}

	/**
	 * Generate FLAC handler code
	 */
	private generateFlacHandler(colors: number[]): Uint8Array {
		const code: number[] = [];

		// Load colors into R4-R8 using MOVW+MOVT pairs
		for (let i = 0; i < colors.length; i++) {
			const reg = 4 + i; // R4-R8
			const color = colors[i];

			// MOVW R{i}, #color_low
			code.push(...encodeMovw(reg, color & 0xffff));

			// MOVT R{i}, #color_high
			code.push(...encodeMovt(reg, (color >> 16) & 0xffff));
		}

		// Select color based on R1 (theme index in R1 when handler is called)
		// We cannot use IT blocks with MOV, so use conditional branches instead

	// CMP R1, #4
	code.push(0x04, 0x29);  // CMP R1, #4

	// B.EQ theme_4 (forward branch to MOV R0, R8 instruction)
	// Target is 2 instructions ahead (skip MOV R0, R4 and B), offset = 1 word
	// 16-bit conditional branch: offset is in words (2 bytes)
	code.push(0x01, 0xD0);  // B.EQ +1 word

	// Theme 0-3: Move R4 to R0
	// MOV R0, R4 (low registers)
	code.push(0x20, 0x1C);  // MOV R0, R4

	// B end (skip theme 4 code, branch to next instruction which is BX LR)
	code.push(0x00, 0xE0);  // B +0 (to BX LR)

	// theme_4: Move R8 to R0
	// MOV R0, R8 (high register move)
	code.push(0x40, 0x44);  // MOV R0, R8

	// end: BX LR
	code.push(0x70, 0x47); // BX LR

		return new Uint8Array(code);
	}

	/**
	 * Generate Menu handler code
	 */
	private generateMenuHandler(colors: number[]): Uint8Array {
		const code: number[] = [];

		// Load colors using MOVW+MOVT pairs
		for (let i = 0; i < colors.length; i++) {
			const reg = i;
			const color = colors[i];

			// MOVW R{i}, #color_low
			code.push(...encodeMovw(reg, color & 0xffff));

			// MOVT R{i}, #color_high
			code.push(...encodeMovt(reg, (color >> 16) & 0xffff));
		}

		// BX LR
		code.push(0x70, 0x47);

		return new Uint8Array(code);
	}

	/**
	 * Apply patch at address
	 */
	private applyPatch(data: Uint8Array, patchAddr: number, targetAddr: number): void {
		console.error(`[DEBUG] applyPatch: patchAddr=0x${patchAddr.toString(16)}, targetAddr=0x${targetAddr.toString(16)}`);
		const blInstruction = encodeBl(patchAddr, targetAddr);
		console.error(`[DEBUG] BL bytes: ${Array.from(blInstruction).map(b => '0x' + b.toString(16).padStart(2, '0')).join(' ')}`);
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
		console.error(`[DEBUG] writePatchCode: writing ${patchData.code.length} bytes to 0x${nopSlide.start.toString(16)}`);
		console.error(`[DEBUG] writePatchCode: first 8 bytes = ${Array.from(patchData.code.slice(0, 8)).map(b => '0x' + b.toString(16)).join(' ')}`);
		data.set(patchData.code, nopSlide.start);
		console.error(`[DEBUG] writePatchCode: done. First 8 bytes in data = ${Array.from(data.slice(nopSlide.start, nopSlide.start + 8)).map(b => '0x' + b.toString(16)).join(' ')}`);
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
