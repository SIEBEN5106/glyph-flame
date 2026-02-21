/**
 * NOP Slide Finder
 *
 * Finds unused regions in firmware that can be used for patch code.
 */

import type { NopSlide } from './types.js';

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

				// Only consider regions large enough
				if (size >= this.MIN_SLIDE_SIZE) {
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

		// Sort by size descending
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
			if (slide.size < requiredSize) continue;

			// Check BL range (±16MB)
			const distances = funcAddrs.map((f) => Math.abs(slide.start - f));
			const maxDistance = distances.length > 0 ? Math.max(...distances) : 0;

			if (maxDistance > 16777216) continue;

			candidates.push({
				slide,
				utilization: requiredSize / slide.size,
				maxDistance
			});
		}

		if (candidates.length === 0) return null;

		// Sort by utilization (prefer well-utilized slides) then by distance (prefer closer)
		candidates.sort((a, b) => {
			const utilDiff = Math.abs(1 - a.utilization) - Math.abs(1 - b.utilization);
			if (utilDiff !== 0) return utilDiff;
			return a.maxDistance - b.maxDistance;
		});

		const best = candidates[0].slide;
		return {
			...best,
			source: 'selected'
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
