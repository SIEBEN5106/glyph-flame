/**
 * Theme Color Extractor
 *
 * Main extraction module that analyzes firmware to discover theme colors.
 * Uses function discovery and control flow simulation to extract color values.
 */

import { ThumbDecoder } from './thumb/index.js';
import { ThemeDiscovery } from './discovery.js';
import { ControlFlowSimulator } from './simulator.js';
import { BehaviorAnalyzer } from './behavior.js';
import { createColorMap, type ThemeFunction, type AnalysisResult, type FlacBehavior } from './types.js';
import {
	ThemeError,
	NotFoundError,
	AnalysisError,
	throwThemeError
} from './errors.js';

/**
 * Theme Color Extractor Class
 *
 * Analyzes firmware to discover and extract theme color values.
 */
export class ThemeColorExtractor {
	private readonly decoder: ThumbDecoder;
	private readonly discovery: ThemeDiscovery;
	private readonly behaviorAnalyzer: BehaviorAnalyzer;

	/**
	 * Create a new ThemeColorExtractor
	 */
	constructor(firmwareData: Uint8Array) {
		this.decoder = new ThumbDecoder(firmwareData);
		this.discovery = new ThemeDiscovery(this.decoder);
		this.behaviorAnalyzer = new BehaviorAnalyzer(this.decoder);
	}

	/**
	 * Extract theme colors from firmware
	 */
	extract(): AnalysisResult {
		try {
			// Discover theme functions
			const functions = this.discovery.scanFirmware();

			if (functions.length === 0) {
				return {
					version: 'Unknown',
					themeFunctions: [],
					colors: createColorMap(),
					flacBehavior: { type: 'unknown' },
					canPatch: false
				};
			}

			// Analyze each function
			const mergedColors = createColorMap();

			for (const func of functions) {
				const simulator = new ControlFlowSimulator(this.decoder);
				const [registers] = simulator.simulate(
					func.addr,
					func.endAddr || func.addr + 500,
					4
				);

				// Extract colors from registers (R4-R8 for FLAC, R0-R14 for Menu)
				for (const [reg, value] of registers.entries()) {
					if (value !== 0) {
						if (!mergedColors.has(reg)) {
							mergedColors.set(reg, []);
						}
						mergedColors.get(reg)!.push(value);
					}
				}
			}

			// Determine FLAC behavior using behavior analysis
			const flacBehavior = this.analyzeFlacBehavior(functions);

			return {
				version: 'Unknown',
				themeFunctions: functions,
				colors: mergedColors,
				flacBehavior,
				canPatch: functions.length > 0
			};
		} catch (error) {
			throwThemeError(error, AnalysisError, 'Failed to extract theme colors');
		}
	}

	/**
	 * Analyze FLAC behavior using behavior analyzer
	 */
	private analyzeFlacBehavior(functions: ThemeFunction[]): FlacBehavior {
		const flacFunc = functions.find(f => f.type === 'flac');

		if (!flacFunc) {
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

		// Use behavior analyzer for detailed analysis
		return this.behaviorAnalyzer.analyzeFlacFunction(flacFunc.addr, 100);
	}

	/**
	 * Get specific colors for a function type
	 */
	getColorsForFunction(funcType: 'flac' | 'menu'): number[] {
		const result = this.extract();
		const func = result.themeFunctions.find(f => f.type === funcType);

		if (!func) {
			throw new NotFoundError(`${funcType} function not found`);
		}

		const simulator = new ControlFlowSimulator(this.decoder);
		const [registers] = simulator.simulate(
			func.addr,
			func.endAddr || func.addr + 500,
			4
		);

		// Extract colors in expected order
		if (funcType === 'flac') {
			// FLAC uses R4-R8 (5 colors)
			const flacColors: number[] = [];
			for (const reg of [4, 5, 6, 7, 8]) {
				const value = registers.get(reg) || 0;
				flacColors.push(value);
			}
			return flacColors;
		} else {
			// Menu uses R0-R14 (15 colors typically)
			const menuColors: number[] = [];
			for (let reg = 0; reg <= 14; reg++) {
				const value = registers.get(reg) || 0;
				menuColors.push(value);
			}
			return menuColors;
		}
	}
}

/**
 * Convenience function to extract colors from firmware
 */
export function extractThemeColors(firmwareData: Uint8Array): AnalysisResult {
	const extractor = new ThemeColorExtractor(firmwareData);
	return extractor.extract();
}
