/**
 * Patch Metadata
 *
 * Handles reading/writing patch metadata stored in patched firmware.
 */

import type { PatchMetadata } from './types.js';

/** Magic number for patch metadata */
const PATCH_MAGIC = 'ECHO';
/** Current metadata version */
const METADATA_VERSION = 1;

/**
 * Patch metadata implementation
 */
class PatchMetadataImpl implements PatchMetadata {
	readonly magic = PATCH_MAGIC;
	version = METADATA_VERSION;
	timestamp = 0;
	flacColors: number[] = [];
	menuColors: number[] = [];
	checksum = 0;

	toBytes(): Uint8Array {
		const data: number[] = [];

		// Magic (4 bytes)
		for (let i = 0; i < PATCH_MAGIC.length; i++) {
			data.push(PATCH_MAGIC.charCodeAt(i));
		}

		// Version (1 byte)
		data.push(this.version);

		// Timestamp (4 bytes, little-endian)
		data.push(this.timestamp & 0xff);
		data.push((this.timestamp >> 8) & 0xff);
		data.push((this.timestamp >> 16) & 0xff);
		data.push((this.timestamp >> 24) & 0xff);

		// FLAC colors (5 * 2 bytes = 10 bytes)
		for (const c of this.flacColors) {
			data.push(c & 0xff);
			data.push((c >> 8) & 0xff);
		}

		// Menu colors (15 * 2 bytes = 30 bytes)
		for (const c of this.menuColors) {
			data.push(c & 0xff);
			data.push((c >> 8) & 0xff);
		}

		// Calculate checksum (CRC16 of everything so far)
		this.checksum = crc16(new Uint8Array(data));
		data.push(this.checksum & 0xff);
		data.push((this.checksum >> 8) & 0xff);

		return new Uint8Array(data);
	}

	static fromBytes(data: Uint8Array, offset = 0): PatchMetadataImpl | null {
		const requiredSize = 4 + 1 + 4 + 10 + 30 + 2; // 51 bytes
		if (data.length - offset < requiredSize) {
			return null;
		}

		// Check magic
		if (
			data[offset] !== 0x45 || // E
			data[offset + 1] !== 0x43 || // C
			data[offset + 2] !== 0x48 || // H
			data[offset + 3] !== 0x4f    // O
		) {
			return null;
		}

		const metadata = new PatchMetadataImpl();

		// Version
		metadata.version = data[offset + 4];

		// Timestamp
		metadata.timestamp =
			data[offset + 5] |
			(data[offset + 6] << 8) |
			(data[offset + 7] << 16) |
			(data[offset + 8] << 24);

		// FLAC colors
		metadata.flacColors = [];
		for (let i = 0; i < 5; i++) {
			const colorOffset = offset + 9 + i * 2;
			const color = data[colorOffset] | (data[colorOffset + 1] << 8);
			metadata.flacColors.push(color);
		}

		// Menu colors
		metadata.menuColors = [];
		for (let i = 0; i < 15; i++) {
			const colorOffset = offset + 19 + i * 2;
			const color = data[colorOffset] | (data[colorOffset + 1] << 8);
			metadata.menuColors.push(color);
		}

		// Verify checksum
		const storedChecksum = data[offset + 49] | (data[offset + 50] << 8);
		const calculatedChecksum = crc16(data.slice(offset, offset + 49));

		if (storedChecksum !== calculatedChecksum) {
			return null;
		}

		metadata.checksum = storedChecksum;
		return metadata;
	}
}

/**
 * CRC16 calculation
 */
export function crc16(data: Uint8Array): number {
	let crc = 0xffff;
	for (const byte of data) {
		crc ^= byte;
		for (let i = 0; i < 8; i++) {
			if (crc & 1) {
				crc = (crc >> 1) ^ 0xa001;
			} else {
				crc >>= 1;
			}
		}
	}
	return crc;
}

/**
 * Create patch metadata from color values
 */
export function createPatchMetadata(
	timestamp: number,
	flacColors: number[],
	menuColors: number[]
): PatchMetadata {
	const metadata = new PatchMetadataImpl();
	metadata.timestamp = timestamp;
	metadata.flacColors = [...flacColors];
	metadata.menuColors = [...menuColors];
	metadata.checksum = crc16(metadata.toBytes());
	return metadata;
}

/**
 * Read patch metadata from firmware data
 */
export function readPatchMetadata(data: Uint8Array, offset: number): PatchMetadata | null {
	return PatchMetadataImpl.fromBytes(data, offset);
}

/**
 * Write patch metadata to bytes
 */
export function writePatchMetadata(metadata: PatchMetadata): Uint8Array {
	return metadata.toBytes();
}

/**
 * Verify patch metadata checksum
 */
export function verifyPatchMetadata(metadata: PatchMetadata): boolean {
	const bytes = metadata.toBytes();
	const checksum = crc16(bytes.slice(0, bytes.length - 2));
	return checksum === metadata.checksum;
}

/**
 * Format timestamp as ISO string
 */
export function formatTimestamp(timestamp: number): string {
	const date = new Date(timestamp * 1000);
	return date.toISOString();
}
