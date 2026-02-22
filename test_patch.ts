#!/usr/bin/env bun
/**
 * Patch firmware for testing
 *
 * This script patches an ECHO MINI firmware with test theme colors
 * to generate actual patched firmware files for Unicorn emulation testing.
 */

import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { ThemePatcher } from './src/lib/rse/theme/patcher.js';

// Test colors (using original firmware colors for verification)
const FLAC_COLORS = [0x44DE, 0x44DE, 0x44DE, 0x44DE, 0xE162];

// Menu: 15 colors (3 per theme: R1, R2, R3 attributes)
// T0: cyan, dark gray, black | T1: white, dark gray, white
// T2: cyan, black, dark gray | T3: white, black, black | T4: white, black, black
const MENU_COLORS = [
	0x77DE, 0x2945, 0x0000,  // T0
	0xFFFF, 0x2945, 0xFFFF,  // T1
	0x77DE, 0x0000, 0x2945,  // T2
	0xFFFF, 0x0000, 0x0000,  // T3
	0xFFFF, 0x0000, 0x0000,  // T4
];

// Firmware file to patch
const FIRMWARE_PATH = '/tmp/echo-mini-firmwares/ECHO MINI V3.1.0/ECHO MINI V3.1.0/HIFIEC10.IMG';
const OUTPUT_PATH = '/tmp/echo-mini-firmwares/ECHO MINI V3.1.0/ECHO MINI V3.1.0/HIFIEC10_PATCHED.IMG';

console.log('='.repeat(60));
console.log('Firmware Patching Test Script');
console.log('='.repeat(60));
console.log(`Input:  ${FIRMWARE_PATH}`);
console.log(`Output: ${OUTPUT_PATH}`);
console.log();

try {
	// Read firmware
	console.log('Reading firmware...');
	const firmwareData = readFileSync(FIRMWARE_PATH);
	console.log(`  Size: ${firmwareData.length.toLocaleString()} bytes`);

	// Create patcher
	console.log('Creating patcher...');
	const patcher = new ThemePatcher(firmwareData, 'V3.1.0');

	// Analyze firmware
	console.log('Analyzing firmware...');
	const analysis = patcher.analyze();
	console.log(`  Theme functions found: ${analysis.themeFunctions.length}`);
	console.log(`  NOP slides found: ${analysis.nopSlides.length}`);
	console.log(`  Can patch: ${analysis.canPatch}`);
	console.log(`  Patch status: ${analysis.patchStatus.isPatched ? 'PATCHED' : 'UNPATCHED'}`);

	if (!analysis.canPatch) {
		console.error('ERROR: Firmware cannot be patched');
		process.exit(1);
	}

	if (analysis.patchStatus.isPatched) {
		console.error('ERROR: Firmware is already patched');
		process.exit(1);
	}

	// Patch firmware
	console.log();
	console.log('Patching firmware...');
	console.log(`  FLAC colors: ${FLAC_COLORS.map(c => '0x' + c.toString(16)).join(', ')}`);
	console.log(`  MENU colors: ${MENU_COLORS.slice(0, 5).map(c => '0x' + c.toString(16)).join(', ')} ...`);

	const result = patcher.patch(FLAC_COLORS, MENU_COLORS, OUTPUT_PATH, true);

	console.log();
	console.log('Patching completed successfully!');
	console.log(`  NOP slide: 0x${result.nopSlide.start.toString(16)} - 0x${result.nopSlide.end.toString(16)} (${result.nopSlide.size} bytes)`);
	console.log(`  Metadata: 0x${result.metadataAddr.toString(16)}`);

	if (result.patchPoints['flac']) {
		console.log(`  FLAC patch: 0x${result.patchPoints['flac'].patchAddr.toString(16)}`);
	}
	if (result.patchPoints['menu']) {
		console.log(`  Menu patch: 0x${result.patchPoints['menu'].patchAddr.toString(16)}`);
	}

	console.log();
	console.log(`Output written to: ${OUTPUT_PATH}`);

} catch (error) {
	console.error('ERROR:', error);
	process.exit(1);
}
