<script lang="ts">
  import { buildBitmapListFromMetadata } from '$lib/rse/utils/metadata';
  import { readU32LE } from '$lib/rse/utils/struct';

  interface Props {
    onComplete: (patchedFirmware: Uint8Array, filename: string) => void;
    onClose: () => void;
  }

  const { onComplete, onClose }: Props = $props();

  type Step = 'select' | 'processing' | 'results';

  let step = $state<Step>('select');

  let firmwareA = $state<Uint8Array | null>(null);
  let firmwareAName = $state('');
  let firmwareB = $state<Uint8Array | null>(null);
  let firmwareBName = $state('');

  let isDragOverA = $state(false);
  let isDragOverB = $state(false);

  let fileInputA = $state<HTMLInputElement | null>(null);
  let fileInputB = $state<HTMLInputElement | null>(null);

  let progressMsg = $state('');
  let progressPct = $state(0);

  interface MoveResult {
    moved: number;
    skipped: string[];
    failed: string[];
  }

  let result = $state<MoveResult | null>(null);
  let patchedFirmware = $state<Uint8Array | null>(null);
  let patchedName = $state('');

  const canMove = $derived(firmwareA !== null && firmwareB !== null);

  function loadFile(file: File, which: 'a' | 'b') {
    const reader = new FileReader();
    reader.onload = (e) => {
      const data = new Uint8Array(e.target!.result as ArrayBuffer);
      if (which === 'a') { firmwareA = data; firmwareAName = file.name; }
      else { firmwareB = data; firmwareBName = file.name; }
    };
    reader.readAsArrayBuffer(file);
  }

  function handleFileInputA(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) loadFile(f, 'a');
    (e.target as HTMLInputElement).value = '';
  }

  function handleFileInputB(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) loadFile(f, 'b');
    (e.target as HTMLInputElement).value = '';
  }

  function handleDropA(e: DragEvent) {
    e.preventDefault(); isDragOverA = false;
    const f = e.dataTransfer?.files[0]; if (f) loadFile(f, 'a');
  }

  function handleDropB(e: DragEvent) {
    e.preventDefault(); isDragOverB = false;
    const f = e.dataTransfer?.files[0]; if (f) loadFile(f, 'b');
  }

  function extractPixels(firmware: Uint8Array, offset: number, width: number, height: number): Uint8Array {
    const part5Offset = readU32LE(firmware, 0x14c);
    const actualOffset = part5Offset + offset;
    const size = width * height * 2;
    return firmware.slice(actualOffset, actualOffset + size);
  }

  async function moveTheme() {
    if (!firmwareA || !firmwareB) return;
    step = 'processing';
    progressPct = 5;
    progressMsg = 'Parsing source firmware...';

    await tick();

    const imagesA = buildBitmapListFromMetadata(firmwareA, true);
    progressPct = 20;
    progressMsg = 'Parsing target firmware...';
    await tick();

    const imagesB = buildBitmapListFromMetadata(firmwareB, true);
    progressPct = 35;
    progressMsg = 'Building lookup...';
    await tick();

    const mapB = new Map(imagesB.map(img => [img.name, img]));

    const moved: string[] = [];
    const skipped: string[] = [];
    const failed: string[] = [];

    const patched = new Uint8Array(firmwareB);
    const part5OffsetB = readU32LE(patched, 0x14c);
    const part5SizeB = readU32LE(patched, 0x150);

    const total = imagesA.length;
    for (let i = 0; i < total; i++) {
      const imgA = imagesA[i];
      progressPct = 35 + Math.round((i / total) * 60);
      progressMsg = `Processing ${i + 1}/${total}: ${imgA.name}`;
      if (i % 10 === 0) await tick();

      const imgB = mapB.get(imgA.name);
      if (!imgB) { skipped.push(`${imgA.name}: not in target`); continue; }
      if (imgB.offset === undefined) { skipped.push(`${imgA.name}: target has no offset`); continue; }
      if (imgA.offset === undefined) { skipped.push(`${imgA.name}: source has no offset`); continue; }

      let pixels: Uint8Array;

      if (imgA.width === imgB.width && imgA.height === imgB.height) {
        try {
          pixels = extractPixels(firmwareA, imgA.offset, imgA.width, imgA.height);
        } catch {
          failed.push(`${imgA.name}: failed to extract`);
          continue;
        }
      } else {
        skipped.push(`${imgA.name}: dimension mismatch (${imgA.width}x${imgA.height} vs ${imgB.width}x${imgB.height})`);
        continue;
      }

      const actualOffsetB = part5OffsetB + imgB.offset;
      const size = imgB.width * imgB.height * 2;

      if (imgB.offset + size > part5SizeB || actualOffsetB + size > patched.length) {
        failed.push(`${imgA.name}: target out of bounds`);
        continue;
      }

      if (pixels.length < size) {
        failed.push(`${imgA.name}: source data too short`);
        continue;
      }

      patched.set(pixels.subarray(0, size), actualOffsetB);
      moved.push(imgA.name);
    }

    progressPct = 100;
    progressMsg = 'Done!';
    await tick();

    patchedFirmware = patched;
    patchedName = firmwareBName.replace(/\.(img|bin)$/i, '') + '_themed.img';
    result = { moved: moved.length, skipped, failed };
    step = 'results';
  }

  function continueToEditor() {
    if (patchedFirmware) onComplete(patchedFirmware, patchedName);
  }

  function startOver() {
    firmwareA = null; firmwareAName = '';
    firmwareB = null; firmwareBName = '';
    result = null; patchedFirmware = null; patchedName = '';
    progressMsg = ''; progressPct = 0;
    step = 'select';
  }

  function tick() {
    return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  }
</script>

<input type="file" accept=".img,.bin" bind:this={fileInputA} hidden onchange={handleFileInputA} />
<input type="file" accept=".img,.bin" bind:this={fileInputB} hidden onchange={handleFileInputB} />

<div class="backdrop" role="dialog" aria-modal="true" tabindex="-1"
  onclick={(e) => e.target === e.currentTarget && onClose()}
  onkeydown={(e) => e.key === "Escape" && onClose()}>
  <div class="modal">
    <div class="modal-head">
      <span>theme mover</span>
      <button class="close-btn" onclick={onClose}>✕</button>
    </div>

    {#if step === 'select'}
      <div class="modal-body">
        <p class="intro">copy all images from a themed firmware into a clean target firmware.</p>
        <div class="fw-slots">
          <!-- Firmware A -->
          <div class="fw-slot" class:loaded={!!firmwareA} class:drag-over={isDragOverA}
            onclick={() => fileInputA?.click()}
            ondragover={(e) => { e.preventDefault(); isDragOverA = true; }}
            ondragleave={() => (isDragOverA = false)}
            ondrop={handleDropA}
            role="button" tabindex="0"
            onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputA?.click()}>
            <div class="slot-label">source <span class="slot-tag">themed</span></div>
            {#if firmwareA}
              <div class="slot-file"><i class="fa-solid fa-file-code"></i> {firmwareAName}</div>
            {:else}
              <div class="slot-hint">drop or click to load</div>
            {/if}
          </div>

          <div class="arrow-sep"><i class="fa-solid fa-arrow-right"></i></div>

          <!-- Firmware B -->
          <div class="fw-slot" class:loaded={!!firmwareB} class:drag-over={isDragOverB}
            onclick={() => fileInputB?.click()}
            ondragover={(e) => { e.preventDefault(); isDragOverB = true; }}
            ondragleave={() => (isDragOverB = false)}
            ondrop={handleDropB}
            role="button" tabindex="0"
            onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputB?.click()}>
            <div class="slot-label">target <span class="slot-tag slot-tag-b">clean</span></div>
            {#if firmwareB}
              <div class="slot-file"><i class="fa-solid fa-file-code"></i> {firmwareBName}</div>
            {:else}
              <div class="slot-hint">drop or click to load</div>
            {/if}
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button class="mbtn" onclick={onClose}>cancel</button>
        <button class="mbtn mbtn-accent" onclick={moveTheme} disabled={!canMove}>move theme →</button>
      </div>

    {:else if step === 'processing'}
      <div class="modal-body processing-body">
        <div class="prog-label">{progressMsg}</div>
        <div class="prog-track"><div class="prog-bar" style="width:{progressPct}%"></div></div>
        <div class="prog-pct">{progressPct}%</div>
      </div>

    {:else if step === 'results' && result}
      <div class="modal-body">
        <div class="result-counts">
          <div class="result-stat stat-ok">
            <span class="stat-num">{result.moved}</span>
            <span class="stat-lbl">moved</span>
          </div>
          <div class="result-stat stat-skip">
            <span class="stat-num">{result.skipped.length}</span>
            <span class="stat-lbl">skipped</span>
          </div>
          <div class="result-stat stat-fail">
            <span class="stat-num">{result.failed.length}</span>
            <span class="stat-lbl">failed</span>
          </div>
        </div>
        {#if result.skipped.length > 0 || result.failed.length > 0}
          <div class="result-list">
            {#each result.failed as msg, i (i)}
              <div class="result-row result-row-fail"><i class="fa-solid fa-xmark"></i> {msg}</div>
            {/each}
            {#each result.skipped as msg, i (i)}
              <div class="result-row result-row-skip"><i class="fa-solid fa-minus"></i> {msg}</div>
            {/each}
          </div>
        {/if}
      </div>
      <div class="modal-foot">
        <button class="mbtn" onclick={startOver}>start over</button>
        <button class="mbtn mbtn-accent" onclick={continueToEditor}>open in editor →</button>
      </div>
    {/if}
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.65);
    display: flex; align-items: center; justify-content: center; z-index: 10000;
  }
  .modal {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 520px; max-height: 82vh;
    display: flex; flex-direction: column; overflow: hidden;
  }
  .modal-head {
    padding: 14px 20px; border-bottom: 1px solid var(--border);
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim);
    display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
  }
  .close-btn {
    background: none; border: none; color: var(--text-faint); cursor: pointer;
    font-size: 11px; padding: 0; transition: color 0.15s;
  }
  .close-btn:hover { color: var(--text); }
  .modal-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .modal-foot {
    padding: 12px 20px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 12px; flex-shrink: 0;
  }
  .mbtn {
    background: none; border: none; border-bottom: 1px solid var(--border2);
    color: var(--text-dim); font-family: 'DM Mono', monospace; font-size: 12px;
    padding: 3px 0; cursor: pointer; transition: color 0.15s, border-color 0.15s;
  }
  .mbtn:hover:not(:disabled) { color: var(--text); border-bottom-color: var(--text-dim); }
  .mbtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .mbtn-accent { color: var(--accent); border-bottom-color: var(--accent); }
  .mbtn-accent:hover:not(:disabled) { color: var(--accent2); border-bottom-color: var(--accent2); }

  .intro { font-size: 12px; color: var(--text-dim); line-height: 1.6; }

  .fw-slots { display: flex; align-items: center; gap: 10px; }
  .fw-slot {
    flex: 1; border: 1px solid var(--border); border-radius: 4px;
    padding: 16px 14px; cursor: pointer; transition: border-color 0.2s;
    min-height: 80px; display: flex; flex-direction: column; gap: 6px;
  }
  .fw-slot:hover, .fw-slot.drag-over { border-color: var(--accent); }
  .fw-slot.loaded { border-color: var(--border2); }
  .slot-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; color: var(--text-dim); display: flex; align-items: center; gap: 6px; }
  .slot-tag { font-size: 9px; padding: 1px 5px; border-radius: 10px; border: 1px solid var(--accent); color: var(--accent); opacity: 0.7; }
  .slot-tag-b { border-color: var(--blue); color: var(--blue); }
  .slot-file { font-size: 11px; color: var(--text); display: flex; align-items: center; gap: 6px; word-break: break-all; }
  .slot-file i { color: var(--accent); flex-shrink: 0; }
  .slot-hint { font-size: 11px; color: var(--text-faint); }
  .arrow-sep { color: var(--text-faint); font-size: 14px; flex-shrink: 0; }

  .processing-body { align-items: center; justify-content: center; gap: 12px; min-height: 120px; }
  .prog-label { font-size: 11px; color: var(--text-dim); text-align: center; max-width: 380px; }
  .prog-track { width: 100%; height: 2px; background: var(--border); border-radius: 1px; overflow: hidden; }
  .prog-bar { height: 100%; background: var(--accent); transition: width 0.2s; }
  .prog-pct { font-size: 10px; color: var(--text-faint); }

  .result-counts { display: flex; gap: 0; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
  .result-stat { flex: 1; padding: 14px; display: flex; flex-direction: column; align-items: center; gap: 4px; border-right: 1px solid var(--border); }
  .result-stat:last-child { border-right: none; }
  .stat-num { font-size: 22px; font-weight: 500; }
  .stat-lbl { font-size: 10px; text-transform: uppercase; letter-spacing: 1.2px; color: var(--text-dim); }
  .stat-ok .stat-num { color: var(--accent); }
  .stat-skip .stat-num { color: var(--text-dim); }
  .stat-fail .stat-num { color: var(--danger); }

  .result-list { display: flex; flex-direction: column; max-height: 220px; overflow-y: auto; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .result-row { font-size: 11px; padding: 6px 0; border-bottom: 1px solid var(--border); display: flex; align-items: flex-start; gap: 8px; color: var(--text-dim); }
  .result-row:last-child { border-bottom: none; }
  .result-row i { flex-shrink: 0; margin-top: 1px; }
  .result-row-fail { color: var(--danger); }
  .result-row-skip i { color: var(--text-faint); }
</style>
