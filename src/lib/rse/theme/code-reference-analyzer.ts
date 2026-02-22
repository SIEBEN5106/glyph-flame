/**
 * Code Reference Analyzer
 *
 * Performs comprehensive analysis of firmware code to identify:
 * 1. All branch targets (BL, B, CBZ, CBNZ, etc.)
 * 2. All landing points in NOP slides
 * 3. NOP slide usage patterns (functional vs unused)
 * 4. Safe injection points with protective jump generation
 *
 * This replaces heuristic-based NOP slide selection with data-driven analysis.
 */

import { ThumbDecoder } from './thumb/index.js';
import type { Instruction } from './thumb/index.js';

/** Branch target information */
export interface BranchTarget {
	readonly sourceAddr: number;
	readonly targetAddr: number;
	readonly branchType: BranchType;
	readonly instruction: string;
}

/** Landing point analysis */
export interface LandingPoint {
	readonly addr: number;
	readonly referenceCount: number;
	readonly sources: readonly number[];
	readonly inNopSlide: boolean;
	readonly nopSlideStart?: number;
	readonly nopSlideEnd?: number;
	readonly isProtected: boolean;
}

/** NOP slide analysis result */
export interface NopSlideAnalysis {
	readonly start: number;
	readonly end: number;
	readonly size: number;
	readonly type: 'functional' | 'unused' | 'unknown';
	readonly landingPoints: readonly number[];
	readonly referenceCount: number;
	readonly canInjectSafely: boolean;
	readonly protectionRequired: boolean;
	/** Where to inject code (for functional NOP slides) */
	readonly injectionAddr?: number;
	/** Where the protection jump should land (skip injected code) */
	readonly protectionJump?: number;
	/** Available space for injection (after accounting for protection jumps) */
	readonly safeZoneSize?: number;
}

/** Branch instruction types */
export type BranchType =
	| 'bl'          // Branch with link
	| 'blx'         // Branch with link switch
	| 'b'           // Unconditional branch
	| 'b_cond'      // Conditional branch
	| 'cbz'         // Compare and branch on zero
	| 'cbnz'        // Compare and branch on non-zero
	| 'pop_pc'      // POP {..., PC} (return)
	| 'ldm_pc'      // LDM {..., PC} (return)
	| 'unknown';

/**
 * Code Reference Analyzer Class
 */
export class CodeReferenceAnalyzer {
	private readonly decoder: ThumbDecoder;
	private readonly data: Uint8Array;
	private branchTargets: BranchTarget[] | null = null;
	private landingPoints: Map<number, LandingPoint> | null = null;
	private nopSlides: Map<number, NopSlideAnalysis> | null = null;
	private _analysis: {
		branchTargets: readonly BranchTarget[];
		landingPoints: readonly LandingPoint[];
		nopSlides: readonly NopSlideAnalysis[];
	} | null = null;

	constructor(firmwareData: Uint8Array, private readonly options: {
		/** Scan range start (default: 0x0) */
		scanStart?: number;
		/** Scan range end (default: end of firmware) */
		scanEnd?: number;
		/** Automatically analyze on construction (default: false) */
		analyzeOnConstruct?: boolean;
	} = {}) {
		this.data = firmwareData;
		this.decoder = new ThumbDecoder(firmwareData);

		if (options.analyzeOnConstruct) {
			this.analyze();
		}
	}

	/**
	 * Perform full analysis of firmware code references
	 * Results are cached for subsequent calls
	 */
	analyze(): {
		branchTargets: readonly BranchTarget[];
		landingPoints: readonly LandingPoint[];
		nopSlides: readonly NopSlideAnalysis[];
	} {
		// Return cached result if available
		if (this._analysis) {
			return this._analysis;
		}

		// Initialize collections
		this.branchTargets = [];
		this.landingPoints = new Map();
		this.nopSlides = new Map();

		// Step 1: Find all branch targets
		this.scanAllBranches();

		// Step 2: Build landing point map
		this.buildLandingPointMap();

		// Step 3: Analyze NOP slides
		this.analyzeNopSlides();

		// Cache and return result
		this._analysis = {
			branchTargets: this.branchTargets,
			landingPoints: Array.from(this.landingPoints.values()).sort((a, b) => b.referenceCount - a.referenceCount),
			nopSlides: Array.from(this.nopSlides.values()).sort((a, b) => b.referenceCount - a.referenceCount)
		};

		return this._analysis;
	}

	/**
	 * Ensure analysis has been run
	 */
	private ensureAnalyzed(): void {
		if (!this._analysis) {
			this.analyze();
		}
	}

	/**
	 * Scan entire firmware for branch instructions
	 */
	private scanAllBranches(): void {
		// Scan code regions (typically 0x0 to end of firmware)
		// Focus on regions with actual code (non-zero, aligned)
		const scanStart = this.options.scanStart ?? 0x0;
		const scanEnd = this.options.scanEnd ?? this.data.length;

		// Limit scan range to reasonable code regions for performance
		// Most firmware code is in the first few MB
		const maxScanEnd = Math.min(scanEnd, 0x500000); // Max 5MB scan
		const actualScanEnd = Math.min(scanEnd, maxScanEnd);

		for (let addr = scanStart; addr < actualScanEnd - 4; addr += 2) {
			// Skip if clearly not code (large zero regions)
			if (this.isLikelyNotCode(addr)) {
				addr = this.skipZeroRegion(addr, actualScanEnd);
				continue;
			}

			const branch = this.decodeBranch(addr);
			if (branch) {
				this.branchTargets!.push(branch);
			}
		}
	}

	/**
	 * Check if address is likely not code (in large zero region)
	 */
	private isLikelyNotCode(addr: number): boolean {
		// If we're in a large zero region (>1KB of zeros), skip it
		if (addr + 1024 > this.data.length) return false;

		for (let i = 0; i < 1024; i += 2) {
			if (this.data[addr + i] !== 0 || this.data[addr + i + 1] !== 0) {
				return false;
			}
		}
		return true;
	}

	/**
	 * Skip zero region and return next address to check
	 */
	private skipZeroRegion(addr: number, maxEnd: number): number {
		let end = addr + 1024;
		while (end < maxEnd && this.data[end] === 0 && this.data[end + 1] === 0) {
			end += 2;
		}
		return end;
	}

	/**
	 * Decode instruction at address as branch if applicable
	 */
	private decodeBranch(addr: number): BranchTarget | null {
		if (addr + 4 > this.data.length) return null;

		const hw = this.decoder.readU16(addr);
		const is32bit = hw >= 0xE800;

		try {
			const instr = this.decoder.decode(addr);
			const mnem = instr.mnemonic.toUpperCase();

			// Check for BL (32-bit)
			if (mnem === 'BL' || mnem === 'BLX') {
				const target = this.decodeBlTarget(addr);
				if (target > 0 && target < this.data.length) {
					return {
						sourceAddr: addr,
						targetAddr: target,
						branchType: mnem === 'BL' ? 'bl' : 'blx',
						instruction: instr.toString()
					};
				}
			}

			// Check for B (conditional or unconditional)
			if (mnem === 'B' || mnem.includes('B.')) {
				const target = this.decodeBTarget(addr, is32bit);
				if (target > 0 && target < this.data.length) {
					return {
						sourceAddr: addr,
						targetAddr: target,
						branchType: 'b_cond',
						instruction: instr.toString()
					};
				}
			}

			// Check for CBZ/CBNZ
			if (mnem === 'CBZ' || mnem === 'CBNZ') {
				const target = this.decodeCbzTarget(addr);
				if (target > 0 && target < this.data.length) {
					return {
						sourceAddr: addr,
						targetAddr: target,
						branchType: mnem === 'CBZ' ? 'cbz' : 'cbnz',
						instruction: instr.toString()
					};
				}
			}

			// Check for POP {..., PC}
			if (mnem === 'POP' && instr.registers?.includes(15)) { // PC is R15
				return {
					sourceAddr: addr,
					targetAddr: 0, // Will be determined at runtime
					branchType: 'pop_pc',
					instruction: instr.toString()
				};
			}

		} catch {
			// Not a valid instruction or decode error
		}

		return null;
	}

	/**
	 * Decode BL instruction target address
	 */
	private decodeBlTarget(addr: number): number {
		if (addr + 4 > this.data.length) return 0;

		const hw1 = this.decoder.readU16(addr);
		const hw2 = this.decoder.readU16(addr + 2);

		// BL encoding: 11110 S imm10 | 11 J1 1 J2 imm11
		if ((hw1 & 0xF800) !== 0xF000) return 0;
		if ((hw2 & 0xD000) !== 0xD000) return 0;

		const S = (hw1 >> 10) & 1;
		const imm10 = hw1 & 0x3FF;
		const J1 = (hw2 >> 13) & 1;
		const J2 = (hw2 >> 11) & 1;
		const imm11 = hw2 & 0x7FF;

		const I1 = ~(S ^ J1) & 1;
		const I2 = ~(S ^ J2) & 1;

		let imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1);
		if (S) {
			imm32 |= 0xFE000000; // Sign extend
		}

		// Sign extend to 32 bits
		imm32 = imm32 | (imm32 & 0x10000000 ? 0xFE000000 : 0);

		return (addr + 4 + imm32) & 0xFFFFFFFF;
	}

	/**
	 * Decode B instruction target address
	 */
	private decodeBTarget(addr: number, is32bit: boolean): number {
		if (is32bit) {
			// 32-bit B: similar to BL but different second halfword encoding
			if (addr + 4 > this.data.length) return 0;

			const hw1 = this.decoder.readU16(addr);
			const hw2 = this.decoder.readU16(addr + 2);

			if ((hw1 & 0xF800) !== 0xF000) return 0;
			if ((hw2 & 0xD000) !== 0x9000) return 0; // B has bit 12 = 0, BL has bit 12 = 1

			const S = (hw1 >> 10) & 1;
			const imm10 = hw1 & 0x3FF;
			const J1 = (hw2 >> 13) & 1;
			const J2 = (hw2 >> 11) & 1;
			const imm11 = hw2 & 0x7FF;

			const I1 = ~(S ^ J1) & 1;
			const I2 = ~(S ^ J2) & 1;

			let imm32 = (S << 24) | (I1 << 23) | (I2 << 22) | (imm10 << 12) | (imm11 << 1);
			if (S) imm32 |= 0xFE000000;

			imm32 = imm32 | (imm32 & 0x10000000 ? 0xFE000000 : 0);

			return (addr + 4 + imm32) & 0xFFFFFFFF;
		} else {
			// 16-bit B
			const hw = this.decoder.readU16(addr);
			if ((hw & 0xF800) !== 0xE000) return 0;

			const imm11 = hw & 0x7FF;
			let offset = imm11 << 1;
			// Sign extend
			if (offset & 0x1000) offset |= 0xFFFFF000;

			return (addr + 4 + offset) & 0xFFFFFFFF;
		}
	}

	/**
	 * Decode CBZ/CBNZ target address
	 */
	private decodeCbzTarget(addr: number): number {
		if (addr + 2 > this.data.length) return 0;

		const hw = this.decoder.readU16(addr);
		// CBZ/CBNZ: 1011 x011 iiii iiii nnnn
		if ((hw & 0xF850) !== 0xB100 && (hw & 0xF850) !== 0xB900) return 0;

		const imm5 = (hw >> 3) & 0x1F;
		const imm3 = hw & 0x7;
		let offset = (imm5 << 1) | (imm3 << 4);
		// Sign extend
		if (offset & 0x100) offset |= 0xFFFFFE00;

		return (addr + 4 + offset) & 0xFFFFFFFF;
	}

	/**
	 * Build landing point map from branch targets
	 */
	private buildLandingPointMap(): void {
		// Count references to each target
		const refCounts = new Map<number, number[]>();
		for (const bt of this.branchTargets) {
			if (bt.targetAddr > 0) {
				if (!refCounts.has(bt.targetAddr)) {
					refCounts.set(bt.targetAddr, []);
				}
				refCounts.get(bt.targetAddr)!.push(bt.sourceAddr);
			}
		}

		// Find NOP slides
		const nopSlideMap = this.findNopSlides();

		// Create landing points
		for (const [target, sources] of refCounts.entries()) {
			const inNopSlide = this.isInNopSlide(target, nopSlideMap);

			this.landingPoints.set(target, {
				addr: target,
				referenceCount: sources.length,
				sources,
				inNopSlide,
				nopSlideStart: inNopSlide ? nopSlideMap.get(target)!.start : undefined,
				nopSlideEnd: inNopSlide ? nopSlideMap.get(target)!.end : undefined,
				isProtected: false // Will be updated later
			});
		}
	}

	/**
	 * Find all NOP slide regions (zero-filled regions)
	 */
	private findNopSlides(): Map<number, {start: number; end: number}> {
		const slides = new Map<number, {start: number; end: number}>();
		const minSize = 128;

		let i = 0;
		const n = this.data.length;

		while (i < n) {
			if (this.data[i] === 0x00) {
				const start = i;
				while (i < n && this.data[i] === 0x00) {
					i++;
				}
				const size = i - start;
				if (size >= minSize) {
					// Map all addresses in this slide to the slide info
					for (let addr = start; addr < i; addr += 2) {
						slides.set(addr, { start, end: i });
					}
				}
			} else {
				i++;
			}
		}

		return slides;
	}

	/**
	 * Check if address is in a NOP slide
	 */
	private isInNopSlide(addr: number, nopSlideMap: Map<number, {start: number; end: number}>): boolean {
		return nopSlideMap.has(addr);
	}

	/**
	 * Analyze NOP slides to determine if functional or unused
	 */
	private analyzeNopSlides(): void {
		// Group landing points by NOP slide
		const slideLandings = new Map<number, number[]>();

		for (const lp of this.landingPoints.values()) {
			if (lp.inNopSlide && lp.nopSlideStart !== undefined) {
				if (!slideLandings.has(lp.nopSlideStart)) {
					slideLandings.set(lp.nopSlideStart, []);
				}
				slideLandings.get(lp.nopSlideStart)!.push(lp.addr);
			}
		}

		// Analyze each NOP slide
		const allSlides = this.findNopSlides();
		const processedSlides = new Set<number>();

		// Extract unique slide start positions
		const uniqueSlides = new Map<number, {start: number; end: number}>();
		for (const slideInfo of allSlides.values()) {
			if (!uniqueSlides.has(slideInfo.start)) {
				uniqueSlides.set(slideInfo.start, slideInfo);
			}
		}

		for (const {start, end} of uniqueSlides.values()) {
			if (processedSlides.has(start)) continue;
			processedSlides.add(start);

			const size = end - start;
			const landings = slideLandings.get(start) || [];
			const refCount = landings.reduce((sum, addr) => {
				const lp = this.landingPoints.get(addr);
				return sum + (lp?.referenceCount || 0);
			}, 0);

			// Determine type
			let type: 'functional' | 'unused' | 'unknown' = 'unknown';

			if (landings.length === 0) {
				type = 'unused';
			} else if (refCount > 50) {
				// High reference count suggests functional NOP slide
				type = 'functional';
			} else if (refCount > 0) {
				// Some references but not many - could be partial usage
				type = 'functional';
			}

			// IMPORTANT: Functional NOP slides are SAFER than unused ones!
			// We understand how they work and can add protective jumps
			// Unused slides have unknown behavior (could be data, runtime use, etc.)
			const canInjectSafely = (type === 'functional' && size >= 512) ||
				(type === 'unused' && size >= 256);

			// For functional NOP slides, calculate injection strategy
			const protectionRequired = type === 'functional' && landings.length > 0;
			let injectionAddr: number | undefined;
			let protectionJump: number | undefined;
			let safeZoneSize: number | undefined;

			if (protectionRequired && landings.length > 0) {
				// Sort landing points to find gaps
				const sortedLandings = [...landings].sort((a, b) => a - b);

				// Strategy 1: Inject BEFORE first landing point
				// Put B instruction at start to jump over our code
				const firstLanding = sortedLandings[0];

				// Need space for:
				// - Protection B instruction (2-4 bytes)
				// - Our injected code (requiredSize)
				// - Final B to first landing point (2-4 bytes)
				const protectionSize = 8; // Max 2 B instructions

				// Check if we have space before first landing
				const availableBeforeFirst = firstLanding - start;

				if (availableBeforeFirst >= protectionSize) {
					// Inject at start, add B to skip our code
					injectionAddr = start;
					protectionJump = firstLanding;
					safeZoneSize = availableBeforeFirst - protectionSize;
				} else {
					// Strategy 2: Find gap BETWEEN landing points
					for (let i = 0; i < sortedLandings.length - 1; i++) {
						const gap = sortedLandings[i + 1] - sortedLandings[i];
						if (gap >= protectionSize) {
							// Inject in this gap
							// Need B before gap to skip it, B after to return to flow
							injectionAddr = sortedLandings[i];
							protectionJump = sortedLandings[i + 1];
							safeZoneSize = gap - protectionSize;
							break;
						}
					}
				}
			}

			this.nopSlides.set(start, {
				start,
				end,
				size,
				type,
				landingPoints: landings,
				referenceCount: refCount,
				canInjectSafely,
				protectionRequired,
				injectionAddr,
				protectionJump,
				safeZoneSize
			});
		}
	}

	/**
	 * Get best NOP slide for injection
	 *
	 * IMPORTANT: Prefers functional NOP slides because:
	 * - We understand their behavior (reverse engineered)
	 * - We know all landing points
	 * - We can add protective jumps
	 * - Unused slides have unknown behavior (could be data, runtime use, etc.)
	 */
	getBestNopSlide(minSize: number, nearAddr?: number): NopSlideAnalysis | null {
		this.ensureAnalyzed();

		const candidates = Array.from(this.nopSlides!.values())
			.filter(nop => {
				// Check if safe to inject
				if (!nop.canInjectSafely) return false;

				// Check size requirement
				// For functional NOP slides, check safe zone size
				const availableSize = nop.safeZoneSize ?? nop.size;
				return availableSize >= minSize;
			});

		if (candidates.length === 0) return null;

		// Sort by: functional first, then by distance, then by size
		candidates.sort((a, b) => {
			// Priority 1: Functional NOP slides (safer - we understand them)
			if (a.type === 'functional' && b.type !== 'functional') return -1;
			if (a.type !== 'functional' && b.type === 'functional') return 1;

			// Priority 2: Distance to target (if specified)
			if (nearAddr !== undefined) {
				const distA = Math.abs(a.start - nearAddr);
				const distB = Math.abs(b.start - nearAddr);
				if (distA !== distB) return distA - distB;
			}

			// Priority 3: Size (prefer smaller for efficient use)
			return a.size - b.size;
		});

		return candidates[0];
	}

	/**
	 * Generate protection code for functional NOP slide
	 * Returns B instruction bytes that jump over injected code
	 */
	generateProtectionCode(fromAddr: number, toAddr: number): Uint8Array {
		const offset = toAddr - (fromAddr + 4);

		// Use 16-bit B if range allows
		if (offset >= -2048 && offset <= 2046) {
			const imm11 = (offset >> 1) & 0x7FF;
			const opcode = 0xE000 | imm11;
			return new Uint8Array([opcode & 0xFF, (opcode >> 8) & 0xFF]);
		}

		// Use 32-bit B for larger offsets
		if (offset > -16777216 && offset < 16777214) {
			const imm25 = (offset >> 1) & 0x1FFFFFF;
			const S = offset < 0 ? 1 : 0;

			// Sign extend and calculate J1, J2
			const signExtended = offset < 0 ? (imm25 | 0xFE000000) : imm25;
			const I1 = (signExtended >> 23) & 1;
			const I2 = (signExtended >> 22) & 1;
			const imm10 = (signExtended >> 12) & 0x3FF;
			const imm11_32bit = signExtended & 0x7FF;

			const J1 = ~(S ^ I1) & 1;
			const J2 = ~(S ^ I2) & 1;

			const hw1 = 0xF000 | (S << 10) | imm10;
			const hw2 = 0x9000 | (J1 << 13) | (1 << 12) | (J2 << 11) | imm11_32bit;

			return new Uint8Array([
				hw1 & 0xFF,
				(hw1 >> 8) & 0xFF,
				hw2 & 0xFF,
				(hw2 >> 8) & 0xFF
			]);
		}

		throw new Error(`Offset ${offset} out of range for B instruction`);
	}

	/**
	 * Generate complete injection strategy for a functional NOP slide
	 * Returns the protection code and where to place injected code
	 */
	generateInjectionStrategy(slide: NopSlideAnalysis, injectedCodeSize: number): {
		/** Where to place the entry protection B instruction */
		entryProtectionAddr: number;
		/** The entry protection B instruction bytes */
		entryProtectionBytes: Uint8Array;
		/** Where to place the injected code */
		injectionAddr: number;
		/** Where to place the exit protection B instruction (after injected code) */
		exitProtectionAddr: number;
		/** The exit protection B instruction bytes */
		exitProtectionBytes: Uint8Array;
		/** Total size required */
		totalSize: number;
	} | null {
		if (slide.type !== 'functional' || !slide.injectionAddr || !slide.protectionJump) {
			return null;
		}

		const entryAddr = slide.start;
		const injectionStart = slide.injectionAddr + 4; // After entry B
		const exitAddr = injectionStart + injectedCodeSize;

		// Generate entry protection: B from start to protectionJump
		const entryBytes = this.generateProtectionCode(entryAddr, slide.protectionJump);

		// Generate exit protection: B from after our code to protectionJump
		const exitBytes = this.generateProtectionCode(exitAddr, slide.protectionJump);

		return {
			entryProtectionAddr: entryAddr,
			entryProtectionBytes: entryBytes,
			injectionAddr: injectionStart,
			exitProtectionAddr: exitAddr,
			exitProtectionBytes: exitBytes,
			totalSize: entryBytes.length + injectedCodeSize + exitBytes.length
		};
	}
}

/**
 * Analyze firmware code references
 */
export function analyzeCodeReferences(firmwareData: Uint8Array): {
	branchTargets: readonly BranchTarget[];
	landingPoints: readonly LandingPoint[];
	nopSlides: readonly NopSlideAnalysis[];
} {
	const analyzer = new CodeReferenceAnalyzer(firmwareData);
	return analyzer.analyze();
}
