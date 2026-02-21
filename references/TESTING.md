# Theme Patcher Testing Guide

This document explains how to verify strict equivalence between the Python and TypeScript implementations of the theme patcher.

## Overview

The theme patcher has two implementations:
- **Python** (`references/`): Original implementation, considered the source of truth
- **TypeScript** (`src/lib/rse/theme/`): Port for web application use

Strict equivalence means both implementations produce **byte-identical** output.

## Test Structure

### 1. Unit Tests (`theme-patcher.test.ts`)

Tests individual components:
- Instruction encoding (BL, MOVW, PUSH, etc.)
- Function discovery (FLAC, Menu)
- NOP slide finding
- Patch detection
- CRC16 calculation

Run with:
```bash
bun test src/lib/rse/__tests__/theme-patcher.test.ts
```

### 2. Python Integration Tests

Compare TypeScript output against Python reference outputs.

#### Generate Reference Outputs

First, generate reference outputs from the Python implementation:

```bash
cd references
python generate_test_results.py
```

This creates:
- `test-results/flac_discovery.json` - FLAC function discovery
- `test-results/menu_discovery.json` - Menu function discovery
- `test-results/nop_slide.json` - NOP slide selection
- `test-results/patch_output.json` - Full patching output
- `test-results/patched_firmware.bin` - Byte-identical patched firmware

#### Run Integration Tests

```bash
bun test src/lib/rse/__tests__/theme-patcher.test.ts
```

Tests marked with `skipIf` will only run if reference outputs exist.

## What Gets Verified

### 1. Function Discovery

✓ **FLAC Function**
- Function address matches Python
- Patch address matches Python
- Signature bytes correct

✓ **Menu Function**
- Function address matches Python
- Patch address matches Python
- Signature bytes correct

### 2. NOP Slide Selection

✓ **Same NOP Slide**
- Start address matches
- End address matches
- Size matches
- Within BL range of all functions

### 3. Patch Output

✓ **Patch Points**
- FLAC patch address correct
- Menu patch address correct
- Original bytes preserved
- New bytes (BL instructions) correct

✓ **NOP Slide**
- Same slide chosen as Python
- Correct address range

✓ **Metadata**
- Correct storage address
- CRC16 checksum matches

### 4. Byte-Level Firmware Comparison

✓ **Patched Firmware**
- Every byte identical to Python output
- File sizes match
- Zero differences allowed

### 5. Cross-Detection

✓ **Mutual Detection**
- TypeScript can detect Python patches
- Python can detect TypeScript patches
- Both see same patch status

## Verification Checklist

Before considering the TypeScript port complete:

- [ ] All unit tests pass
- [ ] FLAC discovery matches Python exactly
- [ ] Menu discovery matches Python exactly
- [ ] NOP slide selection matches Python exactly
- [ ] Patch output matches Python exactly
- [ ] Patched firmware is byte-identical
- [ ] Cross-detection works both ways
- [ ] All firmware versions supported (V2.9.0, V3.0.0, V3.1.0)

## Troubleshooting

### Tests Fail with "Cannot find module"

Make sure all imports are correct:
```bash
bun run check  # Verify TypeScript compilation
```

### Reference Outputs Don't Exist

Generate them:
```bash
cd references
python generate_test_results.py
```

### Byte-Level Comparison Fails

This means the patching logic differs. Check:
1. BL instruction encoding (offset calculation)
2. NOP slide selection algorithm
3. Patch code generation (MOVW/MOVT pairs)
4. Metadata writing (CRC16, address)

### Discovery Fails

Check that signature patterns are correct:
- FLAC: `0x04, 0x29, 0x0c, 0xbf` (CMP R1,#4 + ITE EQ)
- Menu: `0x4f, 0xf0, 0x00, 0x0c` (MOV.W R12, #0)

## Adding New Tests

When adding new functionality:

1. **Add Python implementation first** in `references/`
2. **Generate reference output** using the Python script
3. **Add TypeScript test** that compares against reference
4. **Verify byte-level equality** for any firmware modifications

## Continuous Integration

The test suite should run in CI/CD to prevent regressions:

```yaml
# .github/workflows/test.yml
- name: Generate test results
  run: |
    cd references
    python generate_test_results.py

- name: Run tests
  run: |
    bun test src/lib/rse/__tests__/theme-patcher.test.ts
```

## Updating Reference Outputs

If the Python implementation changes legitimately:

1. Regenerate reference outputs
2. Update `generate_test_results.py` if needed
3. Commit both the code and new reference outputs
4. Document why outputs changed

## Safety

- Never modify reference outputs to match TypeScript
- Always fix TypeScript to match Python
- Python is the source of truth
- Byte-identical output is required
