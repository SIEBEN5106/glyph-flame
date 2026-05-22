/**
 * Shared metadata extraction utilities
 * Used by both ResourceExtractor and firmware-worker
 *
 * IMPORTANT: Bootloader Field Reorganization
 * ===========================================
 * Flash metadata stores width/height fields in Entry[i+1], not Entry[i].
 * This is NOT corruption - it's the Bootloader's runtime construction pattern:
 *   Flash Entry[i+1].width  → runtime descriptor[i].width
 *   Flash Entry[i+1].height → runtime descriptor[i].height
 */

import type { BitmapFileInfo } from '../types/index.js';
import { readU32LE, findBytes } from './struct.js';

// Constants
export const METADATA_ENTRY_SIZE = 108;
export const ROCK26_ENTRY_SIZE = 16;
export const ROCK26_SIGNATURE = new TextEncoder().encode('ROCK26IMAGERES');

export interface MetadataEntry {
	name: string;
	offset: number;
	width: number;
	height: number;
}

export interface MisalignmentDetection {
	misalignment: number;
	firstValidEntry: number;
	detectionInfo: {
		rock26Count: number;
		rock26SampleOffsets: number[];
		metadataCount: number;
		conclusion: string;
	};
}

/**
 * Decode ASCII string from bytes, ignoring non-ASCII bytes
 * Matches Python's decode('ascii', errors='ignore') behavior
 */
export function decodeASCII(nameBytes: Uint8Array): string {
	const validBytes = nameBytes.filter(b => b < 128);
	return String.fromCharCode(...validBytes);
}

/**
 * Decode ASCII string from null-terminated bytes
 */
export function decodeNullTerminatedASCII(nameBytes: Uint8Array): string {
	const nullIdx = nameBytes.indexOf(0);
	if (nullIdx >= 0) {
		return decodeASCII(nameBytes.slice(0, nullIdx));
	}
	return decodeASCII(nameBytes);
}

/**
 * Check if string contains only printable characters
 * Matches Python logic: all(c.isprintable() or c in '._-(), ' for c in test_name)
 */
export function isPrintable(str: string): boolean {
	const extraChars = new Set(['.', '_', '-', '(', ')', ',', ' ']);
	for (const c of str) {
		const code = c.charCodeAt(0);
		// Must be either printable OR in extra characters set
		const isPrintableChar = code >= 32 && code <= 126;
		const isExtraChar = extraChars.has(c);
		if (!isPrintableChar && !isExtraChar) {
			return false;
		}
	}
	return true;
}

/**
 * Find metadata table using ROCK26 anchor method
 * @param part5Data - Part 5 firmware data
 * @param rock26Offset - Offset of ROCK26 table within part5Data
 * @returns Table offset within Part 5, or null if not found
 */
export function findMetadataTableByRock26Anchor(
	part5Data: Uint8Array,
	rock26Offset: number
): number | null {
	const rock26EntriesStart = rock26Offset + 32;
	const anchorOffset = readU32LE(part5Data, rock26EntriesStart + 12);

	// Search for all matching positions in Part 5
	const matchingPositionsInPart5: number[] = [];

	for (let pos = 0; pos < part5Data.length - METADATA_ENTRY_SIZE; pos += 4) {
		try {
			const entryOffset = readU32LE(part5Data, pos + 20);

			if (entryOffset === anchorOffset) {
				// Verify it's a valid metadata entry
				const nameBytes = part5Data.slice(pos + 32, pos + 96);
				const nullIdx = nameBytes.indexOf(0);
				const name = decodeNullTerminatedASCII(nameBytes);

				if (name.endsWith('.BMP') && name.length >= 3) {
					matchingPositionsInPart5.push(pos);
				}
			}
		} catch {
			continue;
		}
	}

	if (matchingPositionsInPart5.length === 0) {
		return null;
	}

	// Find the earliest valid entry by scanning backwards
	const firstMatch = Math.min(...matchingPositionsInPart5);
	let tableStart = firstMatch;

	while (tableStart >= METADATA_ENTRY_SIZE) {
		const testPos = tableStart - METADATA_ENTRY_SIZE;
		const testEntry = part5Data.slice(testPos, testPos + METADATA_ENTRY_SIZE);
		const testName = decodeNullTerminatedASCII(testEntry.slice(32, 96));

		if (testName && testName.endsWith('.BMP') && testName.length >= 3 && isPrintable(testName)) {
			tableStart = testPos;
		} else {
			break;
		}
	}

	return tableStart;
}

/**
 * Parse metadata table from Part 5
 * @param part5Data - Part 5 firmware data
 * @param tableStart - Starting offset of the table (relative to Part 5)
 * @returns Array of metadata entries
 */
export function parseMetadataTable(
	part5Data: Uint8Array,
	tableStart: number
): MetadataEntry[] {
	const entries: MetadataEntry[] = [];
	let pos = tableStart;

	while (pos + METADATA_ENTRY_SIZE <= part5Data.length) {
		const nameBytes = part5Data.slice(pos + 32, pos + 96);
		const name = decodeNullTerminatedASCII(nameBytes);

		if (!name || name.length < 3) {
			break;
		}

		const offset = readU32LE(part5Data, pos + 20);
		const width = readU32LE(part5Data, pos + 24);
		const height = readU32LE(part5Data, pos + 28);

		entries.push({
			name,
			offset,
			width,
			height
		});

		pos += METADATA_ENTRY_SIZE;
	}

	return entries;
}

/**
 * Detect offset misalignment using statistical analysis
 * @param metadataEntries - Parsed metadata entries
 * @param part5Data - Part 5 firmware data
 * @param rock26Offset - Offset of ROCK26 table within part5Data
 * @returns Misalignment detection result
 */
export function detectOffsetMisalignment(
	metadataEntries: readonly MetadataEntry[],
	part5Data: Uint8Array,
	rock26Offset: number
): MisalignmentDetection {
	const rock26Count = readU32LE(part5Data, rock26Offset + 16);

	// Read first N ROCK26 entry offsets from part5Data
	const rock26Offsets: number[] = [];
	const rock26EntriesStart = rock26Offset + 32;

	const sampleCount = Math.min(20, rock26Count);
	for (let i = 0; i < sampleCount; i++) {
		const entryOffset = rock26EntriesStart + i * ROCK26_ENTRY_SIZE;
		const offset = readU32LE(part5Data, entryOffset + 12);
		rock26Offsets.push(offset);
	}

	const offsetShiftVotes = new Map<number, number>();

	for (let rock26Idx = 0; rock26Idx < Math.min(20, rock26Offsets.length); rock26Idx++) {
		const rock26OffsetVal = rock26Offsets[rock26Idx];

		for (let shift = -3; shift <= 3; shift++) {
			const metadataIdx = rock26Idx + shift;

			if (metadataIdx >= 0 && metadataIdx < metadataEntries.length) {
				const metadataOffsetVal = metadataEntries[metadataIdx].offset;

				if (metadataOffsetVal === rock26OffsetVal) {
					offsetShiftVotes.set(shift, (offsetShiftVotes.get(shift) ?? 0) + 1);
				}
			}
		}
	}

	let misalignment = 0;
	let firstValidEntry = 0;
	let conclusion = '';

	if (offsetShiftVotes.size > 0) {
		// Find shift with most votes
		let bestShift = 0;
		let confidence = 0;
		for (const [shift, votes] of offsetShiftVotes.entries()) {
			if (votes > confidence) {
				confidence = votes;
				bestShift = shift;
			}
		}

		// Check for Flash metadata structure pattern
		// Entry 0 offset appears invalid because fields are stored in Entry[1]
		const entry0 = metadataEntries[0];
		const hasFlashMetadataStructure =
			entry0.offset === 0 ||
			entry0.offset >= part5Data.length ||
			entry0.offset === 0xf564f564 ||
			entry0.offset === 0xb7b5d7b5 ||
			entry0.offset === 0x00000000 ||
			entry0.offset === 0xc308c308 ||
			entry0.offset === 0x45294529;

		if (bestShift === 1) {
			misalignment = 1;
			firstValidEntry = 1;
			conclusion = `Detected +1 index misalignment (statistical confidence: ${confidence}/${Math.min(20, rock26Offsets.length)} samples match)`;
		} else if (bestShift === 0) {
			misalignment = 0;
			firstValidEntry = 0;
			conclusion = `No misalignment detected (statistical confidence: ${confidence}/${Math.min(20, rock26Offsets.length)} samples match)`;
		} else {
			misalignment = bestShift;
			firstValidEntry = Math.max(1, 1 - misalignment);
			conclusion = `Detected ${misalignment >= 0 ? '+' : ''}${misalignment} index misalignment (statistical confidence: ${confidence}/${Math.min(20, rock26Offsets.length)} samples match)`;
		}
	} else {
		conclusion = 'Statistical analysis failed, unable to detect misalignment';
	}

	return {
		misalignment,
		firstValidEntry,
		detectionInfo: {
			rock26Count,
			rock26SampleOffsets: rock26Offsets.slice(0, 5),
			metadataCount: metadataEntries.length,
			conclusion
		}
	};
}

/**
 * Build list of bitmap files from firmware metadata
 * Shared function used by both ResourceExtractor and firmware-worker
 *
 * @param firmwareData - Full firmware data
 * @param includeOffset - Whether to include offset in results (default: false)
 * @returns Array of bitmap file information
 */

/**
 * Build bitmap list from a simple ROCK26 index (Echo non-Mini format).
 *
 * Echo non-Mini stores everything directly in the ROCK26 block:
 *   [0x00] "ROCK26IMAGERES  " (16 bytes magic)
 *   [0x10] count              (uint32 LE)
 *   [0x14] reserved           (12 bytes)
 *   [0x20] entries × count, each 16 bytes:
 *            width  (uint16 LE)
 *            height (uint16 LE)
 *            unk1   (uint16 LE)
 *            unk2   (uint16 LE)
 *            size   (uint32 LE)   — always width*height*2
 *            offset (uint32 LE)   — relative to start of part5Data
 */
function buildBitmapListFromRock26Index(
	part5Data: Uint8Array,
	rock26Offset: number,
	includeOffset: boolean
): BitmapFileInfo[] {
	const count = readU32LE(part5Data, rock26Offset + 16);
	if (count === 0 || count > 100000) return [];

	const INDEX_START = rock26Offset + 0x20;
	const ENTRY = 16;
	const files: BitmapFileInfo[] = [];

	for (let i = 0; i < count; i++) {
		const base = INDEX_START + i * ENTRY;
		if (base + ENTRY > part5Data.length) break;

		const w      = part5Data[base]     | (part5Data[base + 1] << 8);
		const h      = part5Data[base + 2] | (part5Data[base + 3] << 8);
		const size   = readU32LE(part5Data, base + 8);
		const offset = readU32LE(part5Data, base + 12);

		if (w === 0 || h === 0 || w > 10000 || h > 10000 || offset === 0) continue;

		files.push({
			name: `IMG_${String(i).padStart(4, '0')}_${w}x${h}.BMP`,
			width: w,
			height: h,
			size,
			...(includeOffset && { offset })
		});
	}

	return files;
}

/**
 * Build list of bitmap files from firmware metadata.
 * Supports both Echo Mini (named metadata table) and Echo non-Mini (direct ROCK26 index).
 */
export function buildBitmapListFromMetadata(
	firmwareData: Uint8Array,
	includeOffset = false
): BitmapFileInfo[] {
	const part5Offset = readU32LE(firmwareData, 0x14c);
	const part5Size = readU32LE(firmwareData, 0x150);
	const part5Data = firmwareData.slice(part5Offset, part5Offset + part5Size);

	const rock26Offset = findBytes(part5Data, ROCK26_SIGNATURE);
	if (rock26Offset === -1) return [];

	// --- Echo Mini path: separate named metadata table ---
	const tableStart = findMetadataTableByRock26Anchor(part5Data, rock26Offset);
	if (tableStart !== null) {
		const metadataEntries = parseMetadataTable(part5Data, tableStart);
		const { misalignment } = detectOffsetMisalignment(metadataEntries, part5Data, rock26Offset);

		const files: BitmapFileInfo[] = [];
		const endIndex = metadataEntries.length - (misalignment > 0 ? 1 : 0);

		for (let i = 0; i < endIndex; i++) {
			const entry = metadataEntries[i];

			let offset: number;
			if (misalignment > 0) {
				const targetIndex = i + misalignment;
				if (targetIndex >= metadataEntries.length) continue;
				offset = metadataEntries[targetIndex].offset;
			} else if (misalignment < 0) {
				const targetIndex = i + misalignment;
				if (targetIndex < 0) continue;
				offset = metadataEntries[targetIndex].offset;
			} else {
				offset = entry.offset;
			}

			let width: number;
			let height: number;
			if (i + 1 < metadataEntries.length) {
				width = metadataEntries[i + 1].width;
				height = metadataEntries[i + 1].height;
			} else {
				width = entry.width;
				height = entry.height;
			}

			const size = width * height * 2;
			if (offset === 0 || width <= 0 || height <= 0 || width > 10000 || height > 10000) continue;

			files.push({
				name: entry.name,
				width,
				height,
				size,
				...(includeOffset && { offset })
			});
		}

		return files;
	}

	// --- Echo non-Mini fallback: direct ROCK26 index ---
	return buildBitmapListFromRock26Index(part5Data, rock26Offset, includeOffset);
}
