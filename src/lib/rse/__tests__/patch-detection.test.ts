/**
 * FLAC/Menu Patch Detection Unit Tests
 *
 * Tests that patch status detection works correctly for all scenarios:
 * - First patch: FLAC-only, Menu-only, Both (3 options)
 * - Second patch: FLAC-only, Menu-only, Both (3 options)
 * - Total: 9 scenarios
 *
 * For each scenario, we verify:
 * 1. First patch is applied correctly
 * 2. detectPatchStatus() correctly identifies the patch state
 * 3. Second patch (re-patch) is applied correctly
 * 4. detectPatchStatus() correctly identifies the final state
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { ThemePatcher } from '../theme/patcher.js';

const FIRMWARE_BASE = '/tmp/echo-mini-firmwares';

// Test colors
const TEST_COLORS = {
	flac: {
		first: [0x1111, 0x2222, 0x3333, 0x4444, 0x5555],
		second: [0xF800, 0x07E0, 0x001F, 0xFFE0, 0x8410]
	},
	menu: {
		first: [0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666, 0x7777, 0x8888, 0x9999, 0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD, 0xEEEE, 0xFFFF],
		second: [0xF800, 0x07E0, 0x001F, 0xFFE0, 0x8410, 0xFFFF, 0x0000, 0x7777, 0x8888, 0x9999, 0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD, 0xEEEE]
	}
};

// Firmware info
const FIRMWARE_INFO = [
	{ version: 'V2.4.0', file: 'HIFIEC40.IMG', subdir: 'ECHO MINI V2.4.0/ECHO MINI V2.4.0' },
	{ version: 'V2.5.0', file: 'HIFIEC50.IMG', subdir: 'ECHO MINI V2.5.0/ECHO MINI V2.5.0' },
];

interface Scenario {
	id: string;
	name: string;
	firstOp: 'flac-only' | 'menu-only' | 'both';
	secondOp: 'flac-only' | 'menu-only' | 'both';
	firstColors: { flacColors?: number[]; menuColors?: number[] };
	secondColors: { flacColors?: number[]; menuColors?: number[] };
	// Expected patch status after first patch
	expectedAfterFirst: {
		isPatched: boolean;
		flacPatched: boolean;
		menuPatched: boolean;
	};
	// Expected patch status after second patch
	expectedAfterSecond: {
		isPatched: boolean;
		flacPatched: boolean;
		menuPatched: boolean;
	};
}

// All 9 test scenarios
const SCENARIOS: Scenario[] = [
	{
		id: 'flac_flac',
		name: 'FLAC-only → FLAC-only',
		firstOp: 'flac-only',
		secondOp: 'flac-only',
		firstColors: { flacColors: TEST_COLORS.flac.first },
		secondColors: { flacColors: TEST_COLORS.flac.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: false },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: false },
	},
	{
		id: 'flac_menu',
		name: 'FLAC-only → Menu-only',
		firstOp: 'flac-only',
		secondOp: 'menu-only',
		firstColors: { flacColors: TEST_COLORS.flac.first },
		secondColors: { menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: false },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'flac_both',
		name: 'FLAC-only → Both',
		firstOp: 'flac-only',
		secondOp: 'both',
		firstColors: { flacColors: TEST_COLORS.flac.first },
		secondColors: { flacColors: TEST_COLORS.flac.second, menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: false },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'menu_flac',
		name: 'Menu-only → FLAC-only',
		firstOp: 'menu-only',
		secondOp: 'flac-only',
		firstColors: { menuColors: TEST_COLORS.menu.first },
		secondColors: { flacColors: TEST_COLORS.flac.second },
		expectedAfterFirst: { isPatched: true, flacPatched: false, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'menu_menu',
		name: 'Menu-only → Menu-only',
		firstOp: 'menu-only',
		secondOp: 'menu-only',
		firstColors: { menuColors: TEST_COLORS.menu.first },
		secondColors: { menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: false, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: false, menuPatched: true },
	},
	{
		id: 'menu_both',
		name: 'Menu-only → Both',
		firstOp: 'menu-only',
		secondOp: 'both',
		firstColors: { menuColors: TEST_COLORS.menu.first },
		secondColors: { flacColors: TEST_COLORS.flac.second, menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: false, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'both_flac',
		name: 'Both → FLAC-only',
		firstOp: 'both',
		secondOp: 'flac-only',
		firstColors: { flacColors: TEST_COLORS.flac.first, menuColors: TEST_COLORS.menu.first },
		secondColors: { flacColors: TEST_COLORS.flac.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'both_menu',
		name: 'Both → Menu-only',
		firstOp: 'both',
		secondOp: 'menu-only',
		firstColors: { flacColors: TEST_COLORS.flac.first, menuColors: TEST_COLORS.menu.first },
		secondColors: { menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	},
	{
		id: 'both_both',
		name: 'Both → Both',
		firstOp: 'both',
		secondOp: 'both',
		firstColors: { flacColors: TEST_COLORS.flac.first, menuColors: TEST_COLORS.menu.first },
		secondColors: { flacColors: TEST_COLORS.flac.second, menuColors: TEST_COLORS.menu.second },
		expectedAfterFirst: { isPatched: true, flacPatched: true, menuPatched: true },
		expectedAfterSecond: { isPatched: true, flacPatched: true, menuPatched: true },
	}
];

/**
 * Apply patch and return result
 */
function applyPatch(
	firmwarePath: string,
	colors: { flacColors?: number[]; menuColors?: number[] },
	outputPath: string
): { success: boolean; error?: string } {
	try {
		const firmwareData = readFileSync(firmwarePath);
		const patcher = new ThemePatcher(firmwareData);
		const result = patcher.patch(colors, outputPath, true);

		if (!result.success) {
			return { success: false, error: 'Patch failed' };
		}

		return { success: true };
	} catch (error: any) {
		return { success: false, error: String(error.message || error) };
	}
}

/**
 * Check patch status detection
 */
function checkPatchStatus(
	firmwarePath: string
): { success: boolean; status?: { isPatched: boolean; flacPatched: boolean; menuPatched: boolean }; error?: string } {
	try {
		const firmwareData = readFileSync(firmwarePath);
		const patcher = new ThemePatcher(firmwareData);
		const analysis = patcher.analyze();

		return {
			success: true,
			status: {
				isPatched: analysis.patchStatus.isPatched,
				flacPatched: analysis.patchStatus.flacPatched,
				menuPatched: analysis.patchStatus.menuPatched
			}
		};
	} catch (error: any) {
		return { success: false, error: String(error.message || error) };
	}
}

/**
 * Check if detection matches expected
 */
function detectionMatches(
	actual: { isPatched: boolean; flacPatched: boolean; menuPatched: boolean },
	expected: { isPatched: boolean; flacPatched: boolean; menuPatched: boolean }
): boolean {
	return actual.isPatched === expected.isPatched &&
		actual.flacPatched === expected.flacPatched &&
		actual.menuPatched === expected.menuPatched;
}

describe('FLAC/Menu Patch Detection Tests', () => {
	for (const firmware of FIRMWARE_INFO) {
		const firmwarePath = join(FIRMWARE_BASE, firmware.subdir, firmware.file);

		// Skip tests if firmware not found
		if (!existsSync(firmwarePath)) {
			describe.skip(`Firmware ${firmware.version}`, () => {
				it.skip('all scenarios', () => {
					// Skipped because firmware file not found
				});
			});
			continue;
		}

		describe(`Firmware ${firmware.version}`, () => {
			for (const scenario of SCENARIOS) {
				describe(scenario.name, () => {
					it('first patch should apply correctly', () => {
						const firstOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-1.IMG`;
						const firstPatch = applyPatch(firmwarePath, scenario.firstColors, firstOutput);

						expect(firstPatch.success).toBe(true);
						if (!firstPatch.success) {
							throw new Error(firstPatch.error);
						}
					});

					it('first patch detection should match expected', () => {
						const firstOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-1.IMG`;
						const firstDetection = checkPatchStatus(firstOutput);

						expect(firstDetection.success).toBe(true);
						expect(firstDetection.status).toBeDefined();
						expect(detectionMatches(
							firstDetection.status!,
							scenario.expectedAfterFirst
						)).toBe(true);
					});

					it('second patch should apply correctly', () => {
						const firstOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-1.IMG`;
						const secondOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-2.IMG`;

						const secondPatch = applyPatch(firstOutput, scenario.secondColors, secondOutput);

						expect(secondPatch.success).toBe(true);
						if (!secondPatch.success) {
							throw new Error(secondPatch.error);
						}
					});

					it('second patch detection should match expected', () => {
						const firstOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-1.IMG`;
						const secondOutput = `/tmp/test-patch-detection-${firmware.version}-${scenario.id}-2.IMG`;

						// Apply first patch if not already done
						if (!existsSync(secondOutput)) {
							applyPatch(firmwarePath, scenario.firstColors, firstOutput);
							applyPatch(firstOutput, scenario.secondColors, secondOutput);
						}

						const secondDetection = checkPatchStatus(secondOutput);

						expect(secondDetection.success).toBe(true);
						expect(secondDetection.status).toBeDefined();
						expect(detectionMatches(
							secondDetection.status!,
							scenario.expectedAfterSecond
						)).toBe(true);
					});
				});
			}
		});
	}
});
