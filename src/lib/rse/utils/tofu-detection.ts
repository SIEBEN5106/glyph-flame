/**
 * Tofu Detection Algorithm
 *
 * Pure TypeScript/JavaScript implementation of tofu detection algorithm.
 * Can be used in both main thread and workers.
 *
 * Algorithm:
 * 1. Render the character using the user's font (with tofu fallback)
 * 2. Compare against Adobe NotDef's .notdef glyph signature
 * 3. Use pattern sliding to find the best match position
 * 4. Check match ratio and black pixel ratio for accurate detection
 */

import { createOffscreenCanvas, get2dContext } from './worker-utils.js';
import { renderWithTofuPipeline, TOFU_SCALE, TOFU_PADDING, imageDataToPixels, type FontSize } from './glyph-renderer.js';

/**
 * Result of tofu detection analysis
 */
export interface TofuDetectionResult {
  /** Whether tofu pattern was detected (based on configured thresholds) */
  isMatch: boolean;
  /** Best match ratio found (0-1) - percentage of matching pixels */
  matchRatio: number;
  /** Position where best match was found (for debugging/bounding box) */
  matchPosition: { x: number; y: number } | null;
  /** Number of black pixels in tofu signature (constant per font size) */
  tofuPixelCount: number;
  /** Number of black pixels in rendered glyph */
  renderedPixelCount: number;
  /** Ratio: renderedPixelCount / tofuPixelCount (1.0 = identical pixel count) */
  blackPixelRatio: number;
}

/**
 * Options for tofu detection
 */
export interface TofuDetectionOptions {
  /** Minimum match ratio to consider as tofu (default: 0.92)
   * Pixel-by-pixel similarity - how many pixels match between rendered glyph and tofu signature.
   * Higher values require more identical pixels.
   */
  matchThreshold?: number;
  /** Minimum black pixel ratio for tofu detection (default: 0.5)
   * Ensures the rendered glyph has roughly the same amount of "ink" as the tofu signature.
   * Prevents false positives from blank or nearly-blank glyphs that might coincidentally match.
   * Calculated as: renderedBlackPixels / tofuSignatureBlackPixels
   */
  blackPixelThreshold?: number;
  /** Whether to require both thresholds (conservative mode, default: true)
   * When true, BOTH matchThreshold AND blackPixelThreshold must pass.
   * When false, EITHER threshold passing is sufficient (more permissive).
   */
  requireBothThresholds?: boolean;
}

/**
 * Default detection thresholds
 *
 * These thresholds were tuned empirically:
 * - 92% match: Allows for minor rendering differences while still detecting tofu
 * - 50% black pixel: Ensures the glyph has similar pixel density as tofu signature
 * - Both required: Conservative mode to minimize false positives
 */
export const TOFU_MATCH_THRESHOLD = 0.92;
export const TOFU_BLACK_PIXEL_THRESHOLD = 0.5;
export const TOFU_REQUIRE_BOTH = true;

/**
 * Default detection options (exported for reuse)
 */
export const DEFAULT_TOFU_OPTIONS: Required<TofuDetectionOptions> = {
  matchThreshold: TOFU_MATCH_THRESHOLD,
  blackPixelThreshold: TOFU_BLACK_PIXEL_THRESHOLD,
  requireBothThresholds: TOFU_REQUIRE_BOTH,
};

/**
 * Tofu signature for a specific font size
 */
export interface TofuSignature {
  /** Font size */
  fontSize: FontSize;
  /** 2D boolean pattern of the tofu glyph */
  pixels: boolean[][];
  /** Pattern dimensions (should be fontSize * TOFU_SCALE) */
  patternSize: number;
  /** Total black pixel count in the signature */
  blackPixelCount: number;
}

/**
 * Tofu detection context - manages signature cache and detection options
 */
export class TofuDetector {
  private signatureCache: Map<FontSize, TofuSignature> = new Map();
  private options: Required<TofuDetectionOptions>;

  constructor(options?: Partial<TofuDetectionOptions>) {
    this.options = { ...DEFAULT_TOFU_OPTIONS, ...options };
  }

  /**
   * Generate tofu signature for a specific font size
   * Uses OffscreenCanvas for worker compatibility
   */
  async generateSignature(fontSize: FontSize): Promise<TofuSignature> {
    const cached = this.signatureCache.get(fontSize);
    if (cached) return cached;

    const canvasSize = fontSize * TOFU_SCALE + TOFU_PADDING * 2;
    const canvas = createOffscreenCanvas(canvasSize, canvasSize);
    const ctx = get2dContext(canvas);

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.font = `${fontSize * TOFU_SCALE}px "Adobe-NotDef"`;
    ctx.textBaseline = 'top';
    ctx.textAlign = 'left';
    ctx.imageSmoothingEnabled = false;
    ctx.textRendering = 'geometricPrecision';
    ctx.fillStyle = '#000000';
    ctx.fillText('\uFFFD', TOFU_PADDING, TOFU_PADDING);

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const pixels = imageDataToPixels(imageData, 128);

    const patternSize = fontSize * TOFU_SCALE;
    const pattern: boolean[][] = [];
    let blackPixels = 0;

    for (let y = TOFU_PADDING; y < TOFU_PADDING + patternSize; y++) {
      const row: boolean[] = [];
      for (let x = TOFU_PADDING; x < TOFU_PADDING + patternSize; x++) {
        const p = pixels[y]?.[x] ?? false;
        if (p) blackPixels++;
        row.push(p);
      }
      pattern.push(row);
    }

    const signature: TofuSignature = {
      fontSize,
      pixels: pattern,
      patternSize,
      blackPixelCount: blackPixels,
    };

    this.signatureCache.set(fontSize, signature);
    return signature;
  }

  /**
   * Render a character and check if it's tofu
   * Returns the detection result along with rendered pixels for extraction
   */
  async detect(
    char: string,
    fontFamily: string,
    fontSize: FontSize,
  ): Promise<{
    isTofu: boolean;
    renderedPixels: boolean[][];
    detectionResult: TofuDetectionResult;
  }> {
    const signature = await this.generateSignature(fontSize);

    // Render character with tofu fallback
    const pixels = await renderWithTofuPipeline(
      char,
      `${fontFamily}, "Adobe-NotDef"`,
      fontSize,
      { returnType: 'full' },
    );

    // Detect tofu using the signature
    const result = this.detectInCanvas(pixels, signature);

    return {
      isTofu: result.isMatch,
      renderedPixels: pixels,
      detectionResult: result,
    };
  }

  /**
   * Detect tofu pattern in a rendered canvas using a pre-generated signature
   */
  detectInCanvas(
    rendered: boolean[][],
    signature: TofuSignature,
  ): TofuDetectionResult {
    return detectTofuPattern(rendered, signature.pixels, this.options);
  }

  /**
   * Extract glyph pixels from rendered canvas at the standard position
   * Used when character is NOT tofu (ready for firmware extraction)
   */
  extractGlyph(rendered: boolean[][]): boolean[][] {
    const patternSize = rendered.length - TOFU_PADDING * 2;
    const extracted: boolean[][] = [];

    for (let y = 0; y < patternSize; y += TOFU_SCALE) {
      const row: boolean[] = [];
      for (let x = 0; x < patternSize; x += TOFU_SCALE) {
        const canvasY = TOFU_PADDING + y;
        const canvasX = TOFU_PADDING + x;
        row.push(rendered[canvasY]?.[canvasX] ?? false);
      }
      extracted.push(row);
    }

    return extracted;
  }

  /**
   * Clear cached signatures
   */
  clearCache(): void {
    this.signatureCache.clear();
  }

  /**
   * Get detection options (for debugging)
   */
  getOptions(): Required<TofuDetectionOptions> {
    return { ...this.options };
  }
}

/**
 * Count black pixels in a pixel grid
 */
export function countBlackPixels(pixels: boolean[][]): number {
  let count = 0;
  for (const row of pixels) {
    for (const p of row) {
      if (p) count++;
    }
  }
  return count;
}

/**
 * Find bounding box of non-white pixels in a pixel grid
 */
export function findBoundingBox(pixels: boolean[][]): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  let minX = pixels[0]?.length || 0;
  let minY = pixels.length;
  let maxX = 0;
  let maxY = 0;
  let found = false;

  for (let y = 0; y < pixels.length; y++) {
    for (let x = 0; x < pixels[y].length; x++) {
      if (pixels[y][x]) {
        found = true;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
      }
    }
  }

  if (!found) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX + 1,
    height: maxY - minY + 1,
  };
}

/**
 * Scan for tofu pattern in rendered canvas
 *
 * Slides the tofu pattern across the rendered canvas to find the best match position.
 * This handles font metric variations where glyphs may be positioned differently.
 *
 * @param rendered - Rendered pixel grid (full padded canvas)
 * @param tofuPattern - 4x tofu pattern to scan for
 * @param options - Detection options
 * @returns TofuDetectionResult with match status, ratio, and pixel counts
 */
export function detectTofuPattern(
  rendered: boolean[][],
  tofuPattern: boolean[][],
  options?: TofuDetectionOptions,
): TofuDetectionResult {
  const opts = { ...DEFAULT_TOFU_OPTIONS, ...options };

  const patternHeight = tofuPattern.length;
  const patternWidth = tofuPattern[0]?.length || 4;
  const renderedHeight = rendered.length;
  const renderedWidth = rendered[0]?.length || 0;

  // Count black pixels for validation
  const tofuPixelCount = countBlackPixels(tofuPattern);
  const renderedPixelCount = countBlackPixels(rendered);
  const blackPixelRatio = tofuPixelCount > 0 ? renderedPixelCount / tofuPixelCount : 0;

  // Try every position where pattern could fit
  let bestMatchRatio = 0;
  let bestMatchPosition: { x: number; y: number } | null = null;

  for (let startY = 0; startY <= renderedHeight - patternHeight; startY++) {
    for (let startX = 0; startX <= renderedWidth - patternWidth; startX++) {
      let matches = 0;
      let total = 0;

      // Compare pattern at this position
      for (let py = 0; py < patternHeight; py++) {
        for (let px = 0; px < patternWidth; px++) {
          const renderedY = startY + py;
          const renderedX = startX + px;

          // Check bounds
          if (
            renderedY >= 0 &&
            renderedY < renderedHeight &&
            renderedX >= 0 &&
            renderedX < renderedWidth
          ) {
            const pRendered = rendered[renderedY]?.[renderedX] ?? false;
            const pPattern = tofuPattern[py]?.[px] ?? false;

            if (pRendered === pPattern) {
              matches++;
            }
            total++;
          }
        }
      }

      const matchRatio = total > 0 ? matches / total : 0;
      if (matchRatio > bestMatchRatio) {
        bestMatchRatio = matchRatio;
        bestMatchPosition = { x: startX, y: startY };
      }
    }
  }

  // Determine if it's tofu based on thresholds
  const matchPasses = bestMatchRatio >= opts.matchThreshold;
  const blackPixelPasses = blackPixelRatio >= opts.blackPixelThreshold;
  const isMatch = opts.requireBothThresholds
    ? matchPasses && blackPixelPasses
    : matchPasses || blackPixelPasses;

  return {
    isMatch,
    matchRatio: bestMatchRatio,
    matchPosition: bestMatchPosition,
    tofuPixelCount,
    renderedPixelCount,
    blackPixelRatio,
  };
}

/**
 * Compare two pixel grids for equality
 * Used for simple pixel-by-pixel comparison
 */
export function pixelsMatch(pixels1: boolean[][], pixels2: boolean[][]): boolean {
  if (pixels1.length !== pixels2.length) {
    return false;
  }

  for (let y = 0; y < pixels1.length; y++) {
    const row1 = pixels1[y];
    const row2 = pixels2[y];
    if (row1.length !== row2.length) {
      return false;
    }
    for (let x = 0; x < row1.length; x++) {
      if (row1[x] !== row2[x]) {
        return false;
      }
    }
  }

  return true;
}
