/**
 * Switch-Case Patcher Tests
 *
 * Tests Progress Bar and Marquee patching with round-trip verification.
 * 
 * Note: Full Unicorn CPU emulation tests require the Python 'unicorn' module.
 * To run Unicorn tests:
 * 1. Install: pip install unicorn
 * 2. Run: python3 references/test_switch_case_unicorn.py <firmware.img> <progress_addr> <marquee_addr>
 */

import { readFileSync, unlinkSync } from 'fs';
import { ThemePatcher } from '../theme/patcher.js';

// Test colors for Progress Bar and Marquee (5 themes each)
const TEST_COLORS = [0x1111, 0x2222, 0x3333, 0x4444, 0x5555];

// Firmware versions with switch_case function addresses
const SWITCH_CASE_FIRMWARES = [
	{ version: 'V1.8.0', progressAddr: 0x873A8, marqueeAddr: 0x3D088, subdir: 'ECHO MINI V1.8.0' },
	{ version: 'V2.4.0', progressAddr: 0x871E0, marqueeAddr: 0x3CDD0, subdir: 'ECHO MINI V2.4.0' },
	{ version: 'V2.5.0', progressAddr: 0x871E0, marqueeAddr: 0x3CDD0, subdir: 'ECHO MINI V2.5.0' },
	{ version: 'V2.6.0', progressAddr: 0x87228, marqueeAddr: 0x3CE18, subdir: 'ECHO MINI V2.6.0' },
	{ version: 'V2.7.0', progressAddr: 0x87250, marqueeAddr: 0x3CE40, subdir: 'ECHO MINI V2.7.0' },
	{ version: 'V2.8.0', progressAddr: 0x87250, marqueeAddr: 0x3CE40, subdir: 'ECHO MINI V2.8.0' },
	{ version: 'V3.0.0', progressAddr: 0x872E8, marqueeAddr: 0x3D068, subdir: 'ECHO MINI V3.0.0/ECHO MINI V3.0.0' },
	{ version: 'V3.1.0', progressAddr: 0x872B0, marqueeAddr: 0x3CFD0, subdir: 'ECHO MINI V3.1.0/ECHO MINI V3.1.0' },
	{ version: 'V3.2.0', progressAddr: 0x872b0, marqueeAddr: 0x3d010, subdir: 'ECHO MINI V3.2.0/ECHO MINI V3.2.0' },
];

function findFirmwareFile(subdir: string): string | null {
	const { execSync } = require('child_process');
	try {
		const result = execSync(`find "/tmp/echo-mini-firmwares/${subdir}" -maxdepth 2 -name "*.IMG" -type f`, { encoding: 'utf-8' });
		const files = result.trim().split('\n').filter((f: string) => f);
		return files.find((f: string) => !f.includes('_PATCHED')) || null;
	} catch {
		return null;
	}
}

function testFirmware(firmwarePath: string, version: string, progressAddr: number, marqueeAddr: number): boolean {
	try {
		// Read firmware
		const firmware = readFileSync(firmwarePath);
		const patcher = new ThemePatcher(firmware);
		
		// Extract original colors
		const original = patcher.extractSwitchCaseColors();
		
		// Patch with test colors
		const patchedPath = `/tmp/test-${version.replace(/\s+/g, '-')}-patched.img`;
		const result = patcher.patchSwitchCase(
			{
				progressColors: TEST_COLORS,
				marqueeColors: TEST_COLORS,
			},
			patchedPath,
			true
		);
		
		// Verify patches were applied
		if (!result.progressPatched || !result.marqueePatched) {
			console.log(`  ❌ Patching failed`);
			return false;
		}
		
		if (result.progressResults?.patchesApplied !== 5 || result.marqueeResults?.patchesApplied !== 5) {
			console.log(`  ❌ Wrong number of patches applied`);
			return false;
		}
		
		// Read patched firmware and verify round-trip
		const patchedFirmware = readFileSync(patchedPath);
		const verifyPatcher = new ThemePatcher(patchedFirmware);
		const patched = verifyPatcher.extractSwitchCaseColors();
		
		// Verify round-trip
		const progressMatch = patched.progressColors.every((c, i) => c === TEST_COLORS[i]);
		const marqueeMatch = patched.marqueeColors.every((c, i) => c === TEST_COLORS[i]);
		
		// Clean up
		unlinkSync(patchedPath);
		
		if (progressMatch && marqueeMatch) {
			console.log(`  ✅ PASS (Progress Bar: 5 patches, Marquee: 5 patches)`);
			return true;
		} else {
			console.log(`  ❌ FAIL - Round-trip verification failed`);
			if (!progressMatch) {
				console.log(`     Progress Bar: Expected [${TEST_COLORS.map(c => '0x' + c.toString(16))}], Got [${patched.progressColors.map(c => '0x' + c.toString(16))}]`);
			}
			if (!marqueeMatch) {
				console.log(`     Marquee: Expected [${TEST_COLORS.map(c => '0x' + c.toString(16))}], Got [${patched.marqueeColors.map(c => '0x' + c.toString(16))}]`);
			}
			return false;
		}
	} catch (error) {
		console.log(`  ❌ ERROR: ${error}`);
		return false;
	}
}

async function main() {
	console.log('=== Switch-Case Patcher Tests ===\n');
	console.log('Testing Progress Bar and Marquee patching with round-trip verification\n');
	
	let passed = 0;
	let failed = 0;
	let skipped = 0;
	
	for (const fw of SWITCH_CASE_FIRMWARES) {
		console.log(`Testing ${fw.version}...`);
		
		const firmwarePath = findFirmwareFile(fw.subdir);
		if (!firmwarePath) {
			console.log(`  ⊘ SKIP (firmware not found)\n`);
			skipped++;
			continue;
		}
		
		const success = testFirmware(firmwarePath, fw.version, fw.progressAddr, fw.marqueeAddr);
		
		if (success) {
			passed++;
		} else {
			failed++;
		}
		console.log('');
	}
	
	console.log('=== Summary ===');
	console.log(`Total: ${passed + failed + skipped}`);
	console.log(`Passed: ${passed} ✅`);
	console.log(`Failed: ${failed} ❌`);
	console.log(`Skipped: ${skipped} ⊘`);
	console.log(`Success Rate: ${((passed / (passed + failed + skipped)) * 100).toFixed(1)}%`);
	
	if (failed > 0) {
		process.exit(1);
	}
	
	console.log('\n🎉 All tests passed!');
}

main();
