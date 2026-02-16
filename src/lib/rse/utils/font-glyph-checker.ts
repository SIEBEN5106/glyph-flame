/**
 * Font Glyph Checker
 *
 * Uses the Font Loading API (document.fonts.check()) to detect whether
 * a font contains glyphs for specific characters. This is more robust
 * than canvas-based tofu detection as it directly queries the font engine.
 *
 * Key advantages:
 * - No canvas rendering required
 * - Direct check of font glyph availability
 * - No fallback to system fonts (strict mode)
 * - Faster than pixel-based detection
 */

import { getFontsContainer } from './worker-utils.js';

/**
 * Result of glyph availability check
 */
export interface GlyphCheckResult {
	/** Whether the glyph exists in the font */
	hasGlyph: boolean;
	/** The font family used for checking */
	fontFamily: string;
	/** Font size used for checking */
	fontSize: number;
	/** Character that was checked */
	character: string;
}

/**
 * Options for glyph checking
 */
export interface GlyphCheckOptions {
	/** Font size in pixels (default: 12) */
	fontSize?: 12 | 16;
	/** Whether to verify font is loaded before checking (default: true) */
	verifyLoaded?: boolean;
}

/**
 * Font glyph availability checker using Font Loading API
 *
 * Uses document.fonts.check() to determine if a font contains glyphs
 * for specific characters. This method is more reliable than canvas-based
 * detection because it queries the font engine directly.
 */
export class FontGlyphChecker {
	private fontFamily: string;
	private fontSize: number;

	/**
	 * Create a new FontGlyphChecker
	 * @param fontFamily - The font family name to check against
	 * @param fontSize - Font size in pixels (12 or 16)
	 */
	constructor(fontFamily: string, fontSize: 12 | 16 = 12) {
		this.fontFamily = fontFamily;
		this.fontSize = fontSize;
	}

	/**
	 * Check if the font has a glyph for a specific character
	 *
	 * Uses document.fonts.check() which:
	 * - Returns true only if the glyph exists in the specified font
	 * - Does NOT fallback to system fonts
	 * - Is a direct query to the font engine
	 *
	 * @param char - Character to check
	 * @param options - Optional checking configuration
	 * @returns Result indicating whether glyph exists
	 */
	check(char: string, options?: GlyphCheckOptions): GlyphCheckResult {
		const opts = {
			fontSize: this.fontSize,
			verifyLoaded: true,
			...options,
		};

		const fonts = getFontsContainer();

		// Check if font is loaded (optional verification)
		if (opts.verifyLoaded && !fonts.check(`1px "${this.fontFamily}"`)) {
			// Font is not registered, return false
			return {
				hasGlyph: false,
				fontFamily: this.fontFamily,
				fontSize: opts.fontSize,
				character: char,
			};
		}

		// Use document.fonts.check() to verify glyph availability
		// The font string format is: "<size>px <font-family>"
		const fontString = `${opts.fontSize}px "${this.fontFamily}"`;
		const hasGlyph = fonts.check(fontString, char);

		return {
			hasGlyph,
			fontFamily: this.fontFamily,
			fontSize: opts.fontSize,
			character: char,
		};
	}

	/**
	 * Check multiple characters at once
	 * @param chars - Array of characters to check
	 * @param options - Optional checking configuration
	 * @returns Map of character to glyph availability
	 */
	checkMultiple(chars: string[], options?: GlyphCheckOptions): Map<string, boolean> {
		const results = new Map<string, boolean>();
		for (const char of chars) {
			results.set(char, this.check(char, options).hasGlyph);
		}
		return results;
	}

	/**
	 * Get all characters that are missing (tofu) in the font
	 * @param chars - Array of characters to check
	 * @param options - Optional checking configuration
	 * @returns Array of characters missing from the font
	 */
	getMissingGlyphs(chars: string[], options?: GlyphCheckOptions): string[] {
		const missing: string[] = [];
		for (const char of chars) {
			if (!this.check(char, options).hasGlyph) {
				missing.push(char);
			}
		}
		return missing;
	}

	/**
	 * Get all characters that exist in the font
	 * @param chars - Array of characters to check
	 * @param options - Optional checking configuration
	 * @returns Array of characters present in the font
	 */
	getExistingGlyphs(chars: string[], options?: GlyphCheckOptions): string[] {
		const existing: string[] = [];
		for (const char of chars) {
			if (this.check(char, options).hasGlyph) {
				existing.push(char);
			}
		}
		return existing;
	}

	/**
	 * Update the font family being checked
	 * @param fontFamily - New font family name
	 */
	setFontFamily(fontFamily: string): void {
		this.fontFamily = fontFamily;
	}

	/**
	 * Update the font size being checked
	 * @param fontSize - New font size (12 or 16)
	 */
	setFontSize(fontSize: 12 | 16): void {
		this.fontSize = fontSize;
	}

	/**
	 * Get current configuration
	 */
	getConfig(): { fontFamily: string; fontSize: number } {
		return {
			fontFamily: this.fontFamily,
			fontSize: this.fontSize,
		};
	}
}

/**
 * Helper function to create a FontGlyphChecker from a FontFace object
 * @param fontFace - The FontFace object to check
 * @param fontSize - Font size in pixels
 * @returns Configured FontGlyphChecker instance
 */
export function createGlyphCheckerFromFontFace(
	fontFace: FontFace,
	fontSize: 12 | 16 = 12,
): FontGlyphChecker {
	return new FontGlyphChecker(fontFace.family, fontSize);
}

/**
 * Check if a character is tofu (missing glyph) in a font
 * @param char - Character to check
 * @param fontFamily - Font family name
 * @param fontSize - Font size in pixels
 * @returns True if the character is tofu (glyph missing)
 */
export function isTofu(
	char: string,
	fontFamily: string,
	fontSize: 12 | 16 = 12,
): boolean {
	const checker = new FontGlyphChecker(fontFamily, fontSize);
	return !checker.check(char).hasGlyph;
}

/**
 * Batch check characters for tofu status
 * @param chars - Characters to check
 * @param fontFamily - Font family name
 * @param fontSize - Font size in pixels
 * @returns Set of characters that are tofu (missing glyphs)
 */
export function findTofuChars(
	chars: string[],
	fontFamily: string,
	fontSize: 12 | 16 = 12,
): Set<string> {
	const checker = new FontGlyphChecker(fontFamily, fontSize);
	const tofu = new Set<string>();

	for (const char of chars) {
		if (!checker.check(char).hasGlyph) {
			tofu.add(char);
		}
	}

	return tofu;
}
