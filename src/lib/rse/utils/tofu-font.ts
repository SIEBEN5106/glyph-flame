/**
 * Tofu Fallback Font Utilities
 *
 * Uses Adobe NotDef font to detect missing characters.
 * Adobe NotDef is a special font that renders a distinctive .notdef glyph
 * for any character, allowing us to detect when a user's font is missing a glyph.
 *
 * This module now uses shared glyph rendering utilities from glyph-renderer.ts
 * for consistent pixel-perfect rendering across all font operations.
 */

import { getFontsContainer, getFontsReady } from "./worker-utils.js";
import {
  buildFontStackString,
  pixelsToDataURL,
  type FontSize,
  renderWithTofuPipeline,
  TOFU_SCALE,
  TOFU_PADDING,
} from "./glyph-renderer";
import {
  detectTofuPattern,
  findBoundingBox,
  DEFAULT_TOFU_OPTIONS,
  type TofuSignature,
} from "./tofu-detection";

/**
 * Registered tofu font state
 */
interface TofuFontState {
  /** FontFace object for Adobe NotDef */
  fontFace: FontFace | null;
  /** Font family name */
  fontFamily: string;
  /** Whether font is loaded */
  loaded: boolean;
  /** Cached signatures by font size (using FontSize as key) */
  signatures: Map<FontSize, TofuSignature>;
}

/**
 * Global tofu font state
 */
const tofuState: TofuFontState = {
  fontFace: null,
  fontFamily: "Adobe-NotDef",
  loaded: false,
  signatures: new Map(),
};

/**
 * Font family name for tofu fallback
 */
export const TOFU_FONT_FAMILY = "Adobe-NotDef";

/**
 * Default test character for tofu signature generation
 * Using a character that won't exist in most pixel fonts
 */
const DEFAULT_TOFU_TEST_CHAR = "\uFFFD"; // Replacement character

/**
 * Debug data for tofu detection comparison
 */
export interface TofuDebugData {
  /** Unicode code point */
  codePoint: number;
  /** Character string */
  char: string;
  /** Font size */
  fontSize: number;
  /** Rendered pixels from user font */
  renderedPixels: boolean[][];
  /** Tofu signature pixels */
  tofuPixels: boolean[][];
  /** Whether they match (is tofu) */
  match: boolean;
  /** Match percentage */
  matchPercentage: number;
  /** Bounding box of rendered pixels */
  boundingBox1: { x: number; y: number; width: number; height: number };
  /** Bounding box of tofu signature */
  boundingBox2: { x: number; y: number; width: number; height: number };
}

// Store debug data when debug mode is enabled
let debugDataCollection: TofuDebugData[] = [];
export let debugModeEnabled = false;

/**
 * Test characters used to verify tofu detection is working correctly
 * These characters are very unlikely to exist in typical pixel fonts
 */
export const RARE_TEST_CHARS: number[] = [
  0x0401, 0x0403, 0x05a5, 0x05a6, 0x0607, 0x0608, 0x0a01, 0x0e01, 0x0e02,
  0x1981, 0x1a01, 0x1a21,

  0x4e0c, 0x4e0d, 0x4e0e, 0x4e0f, 0x4e10, 0x4e11, 0x4e12, 0x4e13, 0x4e14,

  0x3331, 0x3300, 0x3400, 0x3130, 0x3100, 0x2072, 0x1a20, 0x1a00, 0x1980,
  0x0e00, 0x0a00, 0x0600,
];

/**
 * Check if a code point is one of rare test characters
 */
export function isTestChar(codePoint: number): boolean {
  return RARE_TEST_CHARS.includes(codePoint);
}

/**
 * Get category of a test character
 */
export function getTestCharCategory(codePoint: number): string {
  if (codePoint >= 0xff00) return "Fullwidth/Halfwidth";
  if (codePoint >= 0x2600) return "Symbols";
  if (codePoint >= 0x2500) return "Box/Block";
  if (codePoint >= 0x2300) return "Technical";
  if (codePoint >= 0x2190) return "Arrow/Math";
  if (codePoint >= 0x0180) return "Latin Extended";
  return "Other";
}

/**
 * Enable/disable tofu debug collection
 */
export function setTofuDebugMode(enabled: boolean): void {
  debugModeEnabled = enabled;
  if (enabled) {
    debugDataCollection = [];
  }
}

/**
 * Get collected debug data and clear collection
 */
export function getTofuDebugData(): TofuDebugData[] {
  const data = [...debugDataCollection];
  debugDataCollection = [];
  return data;
}

/**
 * Initialize tofu font system by loading Adobe NotDef
 * @returns Promise that resolves when initialized
 */
export async function loadTofuFont(): Promise<void> {
  if (tofuState.loaded) {
    return;
  }

  try {
    // Fetch Adobe NotDef font file
    const response = await fetch("/AND-Regular.ttf");
    if (!response.ok) {
      throw new Error(
        `Failed to fetch Adobe NotDef font: ${response.statusText}`,
      );
    }

    const buffer = await response.arrayBuffer();

    // Create FontFace object
    const fontFace = new FontFace(TOFU_FONT_FAMILY, buffer);

    // Load and add to fonts container (works in both worker and main thread)
    await fontFace.load();
    getFontsContainer().add(fontFace);
    // Wait for browser to finish processing font addition
    // Without this, canvas rendering may not recognize the new font immediately
    await getFontsReady();

    // Store in state
    tofuState.fontFace = fontFace;
    tofuState.loaded = true;
  } catch (error) {
    console.error("Failed to load Adobe NotDef font:", error);
    throw new Error(
      `Failed to load tofu font: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

/**
 * Generate an Adobe NotDef signature for a specific font size
 * @param fontSize - Font size in pixels
 * @param testChar - Optional test character (defaults to replacement character)
 * @returns The Adobe NotDef signature
 */
export async function generateTofuSignature(
  fontSize: FontSize,
  testChar = DEFAULT_TOFU_TEST_CHAR,
): Promise<TofuSignature> {
  // Check if already cached
  const cached = tofuState.signatures.get(fontSize);
  if (cached) {
    return cached;
  }

  if (!tofuState.loaded) {
    throw new Error("Tofu font not loaded. Call loadTofuFont() first.");
  }

  // Use unified tofu pipeline - returns full padded canvas for signature
  const fullPixels = await renderWithTofuPipeline(
    testChar,
    TOFU_FONT_FAMILY,
    fontSize as FontSize,
    { returnType: "full" },
  );

  // Extract the center pattern (same extraction as used in font extraction)
  const patternSize = fontSize * TOFU_SCALE;
  const padding = TOFU_PADDING;
  const pattern: boolean[][] = [];

  for (let y = padding; y < padding + patternSize; y++) {
    const row: boolean[] = [];
    for (let x = padding; x < padding + patternSize; x++) {
      row.push(fullPixels[y][x] ?? false);
    }
    pattern.push(row);
  }

  // Count black pixels for the signature
  const blackPixelCount = pattern.reduce((count, row) =>
    count + row.filter(p => p).length, 0);

  const signature: TofuSignature = {
    fontSize,
    pixels: pattern,
    patternSize,
    blackPixelCount,
  };

  // Cache signature
  tofuState.signatures.set(fontSize, signature);

  return signature;
}

/**
 * Get tofu signature for a font size
 * @param fontSize - Font size in pixels
 * @returns The tofu signature or null if not generated
 */
export function getTofuSignature(fontSize: FontSize): TofuSignature | null {
  return tofuState.signatures.get(fontSize) || null;
}

/**
 * Check if tofu font system is ready
 * @returns True if Adobe NotDef is loaded
 */
export function isTofuFontLoaded(): boolean {
  return tofuState.loaded;
}

/**
 * Get the tofu font family name for use in CSS font stacks
 * @returns The tofu font family name
 */
export function getTofuFontFamily(): string {
  return TOFU_FONT_FAMILY;
}

/**
 * Result of pattern scanning for tofu detection
 * @deprecated Use TofuDetectionResult from tofu-detection.ts instead
 */
export interface PatternScanResult extends ReturnType<typeof detectTofuPattern> {}

/**
 * Scan for tofu pattern in rendered canvas
 *
 * This is a re-export of detectTofuPattern from tofu-detection.ts for backward compatibility.
 * Slides the 4x tofu pattern across the rendered canvas looking for best match.
 *
 * @param rendered - Rendered pixel grid from user font (full padded canvas)
 * @param pattern - 4x tofu pattern to scan for
 * @param matchThreshold - Minimum match ratio to consider it tofu (default from tofu-detection.ts)
 * @returns PatternScanResult with match status, ratio, position, and pixel counts
 */
export function scanForTofuPattern(
  rendered: boolean[][],
  pattern: boolean[][],
  matchThreshold = DEFAULT_TOFU_OPTIONS.matchThreshold,
): ReturnType<typeof detectTofuPattern> {
  return detectTofuPattern(rendered, pattern, { matchThreshold });
}

/**
 * Unload tofu font and clean up resources
 */
export function unloadTofuFont(): void {
  if (tofuState.fontFace) {
    try {
      getFontsContainer().delete(tofuState.fontFace);
    } catch {
      // Ignore cleanup errors
    }
    tofuState.fontFace = null;
  }
  tofuState.loaded = false;
  tofuState.signatures.clear();
}

/**
 * Render a single character using user font with Adobe NotDef fallback
 * Now uses the unified tofu pipeline for consistent rendering
 * @param char - Character to render
 * @param fontFamily - Primary font family name
 * @param fontSize - Font size in pixels (12 or 16)
 * @returns Rendered pixel data (full padded canvas for tofu detection)
 */
export async function renderCharacterWithTofu(
  char: string,
  fontFamily: string,
  fontSize: 12 | 16,
): Promise<boolean[][]> {
  // Build font stack with tofu fallback
  const fontStack = tofuState.loaded
    ? buildFontStackString(fontFamily, TOFU_FONT_FAMILY)
    : buildFontStackString(fontFamily);

  // Use unified tofu pipeline - returns full padded canvas
  return await renderWithTofuPipeline(char, fontStack, fontSize as FontSize, {
    returnType: "full",
  });
}

/**
 * Result of checking if a character should be skipped during font replacement
 */
export interface SkipCharacterResult {
  /** Whether character should be skipped */
  readonly shouldSkip: boolean;
  /** Unicode code point of character */
  readonly codePoint: number;
  /** Character string */
  readonly char: string;
  /** Reason for skipping (if applicable) */
  readonly reason?: "missing_from_font" | "not_in_firmware" | null;
}

/**
 * Check if a character should be skipped during font replacement
 *
 * Checks by rendering the character and comparing against Adobe NotDef's .notdef glyph.
 * If they match (within tolerance), the character is missing from the user's font.
 *
 * @param codePoint - Unicode code point of character to check
 * @param fontFamily - Primary font family name
 * @param fontSize - Font size in pixels (12 or 16)
 * @param existsInFirmware - Optional callback to check if character exists in firmware address space
 * @returns SkipCharacterResult with skip decision and reason
 */
export async function shouldSkipCharacter(
  codePoint: number,
  fontFamily: string,
  fontSize: 12 | 16,
  existsInFirmware?: (codePoint: number) => boolean,
): Promise<SkipCharacterResult> {
  // Convert code point to string
  const char = String.fromCodePoint(codePoint);

  // Check if character exists in firmware (if callback provided)
  if (existsInFirmware) {
    const exists = existsInFirmware(codePoint);
    if (!exists) {
      return {
        shouldSkip: true,
        codePoint,
        char,
        reason: "not_in_firmware",
      };
    }
  }

  // Check if character is missing from font by comparing against Adobe NotDef
  if (tofuState.loaded) {
    // Get or generate tofu signature for this size
    let signature = getTofuSignature(fontSize);
    if (!signature) {
      signature = await generateTofuSignature(fontSize);
    }

    // Render character in padded canvas (will use Adobe NotDef if missing)
    const pixels = await renderCharacterWithTofu(char, fontFamily, fontSize);

    // Use pattern scanning to detect if tofu
    // This handles font metric variations by scanning for the pattern
    const result = scanForTofuPattern(pixels, signature.pixels);
    const isTofu = result.isMatch;

    // Collect debug data if debug mode is enabled
    if (debugModeEnabled) {
      const bbox1 = findBoundingBox(pixels);
      const bbox2 = findBoundingBox(signature.pixels);

      // Store the rendered pixels (padded canvas) and signature pattern (4x4)
      debugDataCollection.push({
        codePoint,
        char,
        fontSize,
        renderedPixels: pixels.map((row) => [...row]),
        tofuPixels: signature.pixels.map((row) => [...row]),
        match: isTofu,
        matchPercentage: result.matchRatio,
        boundingBox1: { ...bbox1 },
        boundingBox2: { ...bbox2 },
      });
    }

    if (isTofu) {
      return {
        shouldSkip: true,
        codePoint,
        char,
        reason: "missing_from_font",
      };
    }
  }

  return {
    shouldSkip: false,
    codePoint,
    char,
    reason: null,
  };
}

/**
 * Check if multiple characters should be skipped during font replacement
 *
 * Batch version of shouldSkipCharacter for processing multiple characters efficiently.
 *
 * @param codePoints - Array of Unicode code points to check
 * @param fontFamily - Primary font family name
 * @param fontSize - Font size in pixels (12 or 16)
 * @param existsInFirmware - Optional callback to check if character exists in firmware address space
 * @returns Array of SkipCharacterResult for each character
 */
export async function shouldSkipCharacters(
  codePoints: number[],
  fontFamily: string,
  fontSize: 12 | 16,
  existsInFirmware?: (codePoint: number) => boolean,
): Promise<{
  results: SkipCharacterResult[];
  skippedCharacters: number[];
  skippedReasons: Map<number, string>;
}> {
  const results: SkipCharacterResult[] = [];
  const skippedCharacters: number[] = [];
  const skippedReasons = new Map<number, string>();

  // Process each character
  for (const codePoint of codePoints) {
    const result = await shouldSkipCharacter(
      codePoint,
      fontFamily,
      fontSize,
      existsInFirmware,
    );
    results.push(result);

    if (result.shouldSkip) {
      skippedCharacters.push(codePoint);
      skippedReasons.set(codePoint, result.reason || "unknown");
    }
  }

  return {
    results,
    skippedCharacters,
    skippedReasons,
  };
}

// Export pixelsToDataURL for use in debug windows
export { pixelsToDataURL };
