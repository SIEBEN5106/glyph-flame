/**
 * NOP Slide Finder
 *
 * Finds unused regions in firmware that can be used for patch code.
 *
 * SAFETY: Avoids font data storage zones by using heuristics:
 * - Only considers regions in code section (<0x100000)
 * - Rejects very large regions (>64KB) likely to be font storage
 * - Prefers smaller regions (<10KB) typical of NOP slides
 */

import type { NopSlide } from './types.js';

/** Maximum size for a region to be considered a NOP slide (larger = likely font storage) */
const MAX_SAFE_SLIDE_SIZE = 65536; // 64KB

/** Code section boundary (font data typically above this) */
const CODE_SECTION_END = 0x100000;

/**
 * NOP Slide Finder Class
 */
export class NopSlideFinder {
	private readonly data: Readonly<Uint8Array>;
	readonly MIN_SLIDE_SIZE = 128;

	constructor(firmwareData: Uint8Array) {
		this.data = firmwareData;
	}

	/**
	 * Check if a region is safe to use as a NOP slide (not font storage)
	 */
	private isSafeNopSlide(start: number, size: number): boolean {
		// Rule 1: Must be in code section, not font storage area
		if (start >= CODE_SECTION_END) {
			return false; // Too high - likely font storage zone
		}

		// Rule 2: Reject very large regions (likely font data)
		if (size > MAX_SAFE_SLIDE_SIZE) {
			return false; // Too large - probably font storage, not NOP slide
		}

		return true;
	}

	/**
	 * Find all NOP slide regions in firmware
	 */
	findAllSlides(): NopSlide[] {
		const slides: NopSlide[] = [];
		let i = 0;
		const n = this.data.length;

		while (i < n) {
			// Look for zero bytes
			if (this.data[i] === 0x00) {
				const start = i;

				// Count consecutive zeros
				while (i < n && this.data[i] === 0x00) {
					i++;
				}

				const size = i - start;

				// Apply safety checks to avoid font storage zones
				if (size >= this.MIN_SLIDE_SIZE && this.isSafeNopSlide(start, size)) {
					slides.push({
						start,
						end: i,
						size,
						source: 'dynamic',
						isActive: false,
						referenceCount: 0
					});
				}
			} else {
				i++;
			}
		}

		// Sort by size descending (keep original behavior for selectBestSlide)
		return slides.sort((a, b) => b.size - a.size);
	}

	/**
	 * Select best NOP slide for patching
	 *
	 * @param funcAddrs - Addresses of functions that will link to this slide
	 * @param requiredSize - Minimum size needed
	 */
	selectBestSlide(funcAddrs: number[], requiredSize: number): NopSlide | null {
		const slides = this.findAllSlides();
		const candidates: Array<{
			slide: NopSlide;
			utilization: number;
			maxDistance: number;
		}> = [];

		for (const slide of slides) {
			// Enforce 4-byte alignment for BL targets (ARM Thumb2 requirement)
			const alignedStart = (slide.start + 3) & ~3;
			const adjustedSize = slide.end - alignedStart;

			if (adjustedSize < requiredSize) continue;

			// Check distance to theme functions
			const distances = funcAddrs.map((f) => Math.abs(alignedStart - f));
			const maxDistance = distances.length > 0 ? Math.max(...distances) : 0;

			// Must be within BL range (±16MB)
			if (maxDistance > 16777216) continue;

			candidates.push({
				slide: {
					...slide,
					start: alignedStart,
					end: alignedStart + requiredSize,
					size: requiredSize,
					source: 'selected'
				},
				utilization: requiredSize / adjustedSize,
				maxDistance
			});
		}

		if (candidates.length === 0) return null;

		// Sort by: closest to 100% utilization, then by distance
		candidates.sort((a, b) => {
			const utilDiff = Math.abs(1 - a.utilization) - Math.abs(1 - b.utilization);
			if (utilDiff !== 0) return utilDiff;
			return a.maxDistance - b.maxDistance;
		});

		// Return a copy with updated source
		const best = candidates[0].slide;
		return {
			...best,
			source: 'selected' as const
		};
	}

	/**
	 * Find NOP slides near a specific address
	 */
	findSlidesNearAddress(targetAddr: number, searchRange = 0x10000): NopSlide[] {
		const start = Math.max(0, targetAddr - searchRange);
		const end = Math.min(this.data.length, targetAddr + searchRange);

		const slides: NopSlide[] = [];
		let i = start;

		while (i < end) {
			if (this.data[i] === 0x00) {
				const slideStart = i;

				while (i < end && this.data[i] === 0x00) {
					i++;
				}

				const size = i - slideStart;
				if (size >= this.MIN_SLIDE_SIZE) {
					slides.push({
						start: slideStart,
						end: i,
						size,
						source: 'near',
						isActive: false,
						referenceCount: 0
					});
				}
			} else {
				i++;
			}
		}

		return slides.sort((a, b) => b.size - a.size);
	}

	/**
	 * Verify a NOP slide is actually all zeros
	 */
	verifySlide(slide: NopSlide): boolean {
		if (slide.end > this.data.length) return false;

		for (let i = slide.start; i < slide.end; i++) {
			if (this.data[i] !== 0x00) {
				return false;
			}
		}

		return true;
	}

	/**
	 * Calculate distance from NOP slide to target addresses
	 */
	calculateDistances(slide: NopSlide, targets: number[]): Map<number, number> {
		const distances = new Map<number, number>();

		for (const target of targets) {
			const dist = Math.abs(slide.start - target);
			distances.set(target, dist);
		}

		return distances;
	}
}
