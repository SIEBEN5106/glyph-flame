// src/lib/rse/bdf-parser.ts
export interface BDFGlyph {
    unicode: number;
    name: string;
    width: number;
    height: number;
    pixels: boolean[][];
}

/**
 * efont-unicode など Unicode直接エンコーディング対応版
 */
export function parseBDF(content: string): BDFGlyph[] {
    const lines = content.split(/\r?\n/);
    const glyphs: BDFGlyph[] = [];
    let current: Partial<BDFGlyph> | null = null;
    let bitmapLines: string[] = [];
    let inBitmap = false;

    for (let line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith('STARTCHAR')) {
            current = { name: trimmed.slice(9).trim() };
            bitmapLines = [];
            inBitmap = false;
        }
        else if (trimmed.startsWith('ENCODING') && current) {
            const match = trimmed.match(/ENCODING\s+(-?\d+)/);
            if (match) {
                const code = parseInt(match[1]);
                if (code >= 0) {
                    current.unicode = code;   // Unicode直接使用
                }
            }
        }
        else if (trimmed.startsWith('BBX') && current) {
            const parts = trimmed.split(/\s+/);
            current.width = parseInt(parts[1]) || 16;
            current.height = parseInt(parts[2]) || 16;
        }
        else if (trimmed === 'BITMAP') {
            inBitmap = true;
            bitmapLines = [];
        }
        else if (trimmed === 'ENDCHAR' && current && current.unicode !== undefined) {
            if (bitmapLines.length > 0) {
                const pixels = convertBitmapToPixels(bitmapLines, current.width!);
                current.pixels = pixels;
                glyphs.push(current as BDFGlyph);
            }
            current = null;
            inBitmap = false;
        }
        else if (inBitmap && /^[0-9A-Fa-f]+$/.test(trimmed)) {
            bitmapLines.push(trimmed);
        }
    }

    console.log(`BDF解析完了: ${glyphs.length}文字 (Unicode直接モード)`);
    return glyphs;
}

function convertBitmapToPixels(hexLines: string[], glyphWidth: number): boolean[][] {
    const pixels: boolean[][] = [];
    for (const hexRow of hexLines) {
        const row: boolean[] = [];
        for (let i = 0; i < hexRow.length; i++) {
            const hex = parseInt(hexRow[i], 16);
            for (let bit = 3; bit >= 0; bit--) {
                row.push(((hex >> bit) & 1) === 1);
            }
        }
        pixels.push(row.slice(0, glyphWidth));
    }
    return pixels;
}
