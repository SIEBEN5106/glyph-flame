<script lang="ts">
  import type { BitmapFileInfo } from '../../rse/types';
  import { extractFrames } from '../../rse/utils/video-extractor';
  import LoadingWindow from '../98css/LoadingWindow.svelte';

  interface Props {
    imageList: BitmapFileInfo[];
    onApply: (mappings: { target: BitmapFileInfo; source: File }[]) => void;
    onClose: () => void;
  }

  let { imageList, onApply, onClose }: Props = $props();

  // Exact frame dimensions from firmware
  const BOOT_FRAMES = [
    { idx: 10,  w: 480, h: 222 },
    { idx: 11,  w: 312, h: 171 },
    { idx: 12,  w: 318, h: 174 },
    { idx: 13,  w: 328, h: 174 },
    { idx: 14,  w: 325, h: 181 },
    { idx: 15,  w: 319, h: 176 },
    { idx: 16,  w: 311, h: 176 },
    { idx: 17,  w: 311, h: 190 },
    { idx: 18,  w: 313, h: 178 },
    { idx: 19,  w: 305, h: 171 },
    { idx: 20,  w: 315, h: 174 },
    { idx: 21,  w: 318, h: 174 },
    { idx: 22,  w: 319, h: 168 },
    { idx: 23,  w: 319, h: 176 },
    { idx: 24,  w: 312, h: 165 },
    { idx: 25,  w: 408, h: 166 },
    { idx: 26,  w: 368, h: 161 },
    { idx: 27,  w: 343, h: 165 },
    { idx: 28,  w: 294, h: 156 },
    { idx: 29,  w: 309, h: 150 },
    { idx: 30,  w: 338, h: 150 },
    { idx: 31,  w: 353, h: 152 },
    { idx: 32,  w: 384, h: 155 },
    { idx: 33,  w: 417, h: 151 },
    { idx: 34,  w: 373, h: 149 },
    { idx: 35,  w: 399, h: 215 },
    { idx: 36,  w: 415, h: 215 },
    { idx: 37,  w: 408, h: 220 },
    { idx: 38,  w: 403, h: 220 },
    { idx: 39,  w: 394, h: 219 },
    { idx: 40,  w: 396, h: 217 },
    { idx: 41,  w: 393, h: 217 },
    { idx: 42,  w: 372, h: 219 },
    { idx: 43,  w: 387, h: 219 },
    { idx: 44,  w: 480, h: 222 },
  ];

  const ZONES = [
    { id: 'center76',  label: 'true center 76×76',       x: 202, y: 73, w: 76,  h: 76  },
    { id: 'tl149sq',   label: 'safe square 149×149', x: 0,   y: 0,  w: 149, h: 149 },
    { id: 'tl294rect', label: 'full safe 294×149',  x: 0,   y: 0,  w: 294, h: 149 },
    { id: 'centered108', label: 'mirrored safe 108×149', x: 186, y: 0,  w: 108, h: 149 },
  ];
  let selectedZoneId = $state('center76');
  const zone = $derived(ZONES.find(z => z.id === selectedZoneId) ?? ZONES[0]);

  // ── Placement within zone ──
  let contentOffsetX = $state(0);
  let contentOffsetY = $state(0);
  let contentW = $state(76);
  let contentH = $state(76);
  let srcAspect = $state(1);
  let stretchMode = $state(false);

  // Drag state — plain vars, no reactivity needed
  let dragActive = false;
  let dragStart = { mx: 0, my: 0, ox: 0, oy: 0 };
  let editorEl: HTMLDivElement | null = null;

  const EDITOR_MAX_W = 226;
  const EDITOR_PAD = 3; // padding inside placement-editor so borders never clip
  const EDITOR_INNER = EDITOR_MAX_W - EDITOR_PAD * 2;
  const editorScale = $derived(EDITOR_INNER / Math.max(zone.w, 1));
  const editorPxH = $derived(Math.floor(zone.h * editorScale) + EDITOR_PAD * 2);
  const editorInnerH = $derived(editorPxH - EDITOR_PAD * 2);
  const contentPxL = $derived(EDITOR_PAD + Math.floor(contentOffsetX * editorScale));
  const contentPxT = $derived(EDITOR_PAD + Math.floor(contentOffsetY * editorScale));
  const contentPxW = $derived(Math.min(EDITOR_INNER - 1, Math.round(contentW * editorScale)));
  const contentPxH = $derived(Math.min(editorInnerH - 1, Math.round(contentH * editorScale)));
  let sizeSlider = $state(100);

  function fitToZone() {
    // Use only local vars — never read $state contentW/contentH inside this function
    // because it is called from $effect and Svelte 5 tracks every $state read
    let w: number, h: number;
    if (stretchMode) {
      w = zone.w; h = zone.h;
    } else {
      const za = zone.w / zone.h;
      if (srcAspect >= za) { w = zone.w; h = Math.max(1, Math.round(zone.w / srcAspect)); }
      else { h = zone.h; w = Math.max(1, Math.round(zone.h * srcAspect)); }
    }
    contentW = w;
    contentH = h;
    contentOffsetX = Math.round((zone.w - w) / 2);
    contentOffsetY = Math.round((zone.h - h) / 2);
    sizeSlider = Math.round(w / Math.max(zone.w, 1) * 100);
  }

  function clampPlacement() {
    contentOffsetX = Math.max(0, Math.min(zone.w - contentW, contentOffsetX));
    contentOffsetY = Math.max(0, Math.min(zone.h - contentH, contentOffsetY));
  }

  function initFromBitmap(bitmap: ImageBitmap) {
    srcAspect = bitmap.width / bitmap.height;
    fitToZone();
  }

  $effect(() => { zone.w; zone.h; stretchMode; fitToZone(); });

  // ── Size slider ──
  function setSize(pct: number) {
    const nw = Math.max(8, Math.round(zone.w * pct / 100));
    contentW = Math.min(zone.w - contentOffsetX, nw);
    if (!stretchMode && srcAspect > 0) {
      contentH = Math.max(8, Math.min(zone.h - contentOffsetY, Math.round(contentW / srcAspect)));
    } else {
      contentH = Math.max(8, Math.min(zone.h - contentOffsetY, Math.round(zone.h * pct / 100)));
    }
    clampPlacement();
  }

  // ── Drag to move (pointer capture on editor element) ──
  function onEditorPointerDown(e: PointerEvent) {
    e.preventDefault();
    dragActive = true;
    dragStart = { mx: e.clientX, my: e.clientY, ox: contentOffsetX, oy: contentOffsetY };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function onEditorPointerMove(e: PointerEvent) {
    if (!dragActive) return;
    const dx = (e.clientX - dragStart.mx) / editorScale;
    const dy = (e.clientY - dragStart.my) / editorScale;
    contentOffsetX = Math.max(0, Math.min(zone.w - contentW, Math.round(dragStart.ox + dx)));
    contentOffsetY = Math.max(0, Math.min(zone.h - contentH, Math.round(dragStart.oy + dy)));
  }

  function onEditorPointerUp() { dragActive = false; }

    type Mode = 'gif' | 'video' | 'images';
  let mode = $state<Mode>('gif');
  let bgColor = $state('#000000');

  // Source bitmaps (one per slot, max 35)
  let sourceBitmaps = $state<ImageBitmap[]>([]);

  // 35-images mode: ordered list of {bitmap, filename}
  interface ImageSlot { bitmap: ImageBitmap; name: string; url: string; }
  let imageSlots = $state<ImageSlot[]>([]);
  let dragSrcIdx = $state<number | null>(null);

  // UI state
  let isDragOver = $state(false);
  let isProcessing = $state(false);
  let progress = $state(0);
  let statusMsg = $state('');
  let error = $state('');
  let showPreview = $state(false);
  let previewCanvases = $state<string[]>([]); // accumulated composited frames as data URLs
  let previewPlaying = $state(false);
  let previewFrameIdx = $state(0);
  let previewTimer: ReturnType<typeof setInterval> | null = null;

  let dropRef: HTMLDivElement;
  let fileInputRef: HTMLInputElement;

  function findTarget(frameIdx: number): BitmapFileInfo | null {
    const id = frameIdx.toString().padStart(4, '0');
    return imageList.find(img => img.name.startsWith(`IMG_${id}_`)) ?? null;
  }
  const targets = $derived(BOOT_FRAMES.map(f => ({ ...f, info: findTarget(f.idx) })));
  const allTargetsFound = $derived(targets.every(t => t.info !== null));

  // Effective bitmaps for processing
  const effectiveBitmaps = $derived(mode === 'images' ? imageSlots.map(s => s.bitmap) : sourceBitmaps);

  // Composite a single frame bitmap into a firmware-sized canvas
  async function compositeFrame(bitmap: ImageBitmap, frameW: number, frameH: number): Promise<File> {
    const canvas = document.createElement('canvas');
    canvas.width = frameW; canvas.height = frameH;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, frameW, frameH);
    ctx.drawImage(bitmap, zone.x + contentOffsetX, zone.y + contentOffsetY, contentW, contentH);
    return new Promise(resolve => {
      canvas.toBlob(blob => resolve(new File([blob!], 'frame.png', { type: 'image/png' })), 'image/png');
    });
  }

  // Build device-accurate accumulated preview (frame 0 is bg, rest are overlaid at 0,0)
  async function buildPreview(bitmaps: ImageBitmap[]) {
    const accCanvas = document.createElement('canvas');
    accCanvas.width = 480; accCanvas.height = 222;
    const ctx = accCanvas.getContext('2d')!;
    const urls: string[] = [];

    for (let i = 0; i < Math.min(bitmaps.length, BOOT_FRAMES.length); i++) {
      const frame = BOOT_FRAMES[i];
      // Composite this frame into a temp canvas at frame dims
      const tmp = document.createElement('canvas');
      tmp.width = frame.w; tmp.height = frame.h;
      const tc = tmp.getContext('2d')!;
      tc.fillStyle = bgColor;
      tc.fillRect(0, 0, frame.w, frame.h);
      tc.drawImage(bitmaps[i], zone.x + contentOffsetX, zone.y + contentOffsetY, contentW, contentH);
      // Overlay onto accumulated canvas at (0,0)
      ctx.drawImage(tmp, 0, 0);
      urls.push(accCanvas.toDataURL());
    }
    previewCanvases = urls;
  }

  // ── GIF ──
  async function processGif(file: File) {
    isProcessing = true; progress = 0; statusMsg = 'Decoding GIF…'; error = '';
    try {
      const { parseGIF, decompressFrames } = await import('https://esm.run/gifuct-js') as any;
      const buffer = await file.arrayBuffer();
      const gif = parseGIF(new Uint8Array(buffer));
      const frames = decompressFrames(gif, true);
      if (frames.length === 0) { error = 'No frames found in GIF.'; return; }
      statusMsg = `${frames.length} frames → mapping to 35 slots…`; progress = 20;
      const bitmaps: ImageBitmap[] = [];
      for (let i = 0; i < 35; i++) {
        const srcIdx = Math.floor(i * frames.length / 35);
        const f = frames[srcIdx];
        bitmaps.push(await createImageBitmap(new ImageData(new Uint8ClampedArray(f.patch), f.dims.width, f.dims.height)));
        progress = 20 + Math.round((i / 35) * 60);
      }
      sourceBitmaps = bitmaps;
      if (bitmaps.length > 0) initFromBitmap(bitmaps[0]);
      statusMsg = 'Generating preview…';
      await buildPreview(bitmaps);
      showPreview = true;
      previewFrameIdx = 0;
      statusMsg = 'Done'; progress = 100;
    } catch (e) { error = `GIF decode failed: ${e instanceof Error ? e.message : String(e)}`; }
    finally { isProcessing = false; }
  }

  // ── Video ──
  async function processVideo(file: File) {
    isProcessing = true; progress = 0; statusMsg = 'Extracting frames…'; error = '';
    try {
      const files = await extractFrames(file, 35, p => { progress = Math.round(p * 80); });
      const bitmaps: ImageBitmap[] = [];
      for (const f of files) { bitmaps.push(await createImageBitmap(f)); progress = 80 + Math.round((bitmaps.length/35)*20); }
      sourceBitmaps = bitmaps;
      if (bitmaps.length > 0) initFromBitmap(bitmaps[0]);
      statusMsg = 'Generating preview…';
      await buildPreview(bitmaps);
      showPreview = true;
      previewFrameIdx = 0;
      statusMsg = 'Done'; progress = 100;
    } catch (e) { error = `Video extract failed: ${e instanceof Error ? e.message : String(e)}`; }
    finally { isProcessing = false; }
  }

  // ── Images: add files (accumulative) ──
  async function addImageFiles(files: File[]) {
    const sorted = [...files].sort((a,b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    const newSlots: ImageSlot[] = [];
    for (const f of sorted) {
      try {
        const bitmap = await createImageBitmap(f);
        const url = URL.createObjectURL(f);
        newSlots.push({ bitmap, name: f.name, url });
      } catch {}
    }
    imageSlots = [...imageSlots, ...newSlots].slice(0, 35);
    if (newSlots.length > 0 && imageSlots.length === newSlots.length) initFromBitmap(newSlots[0].bitmap);
    const previewBitmaps = imageSlots.map(s => s.bitmap);
    await buildPreview(previewBitmaps);
    showPreview = true;
    previewFrameIdx = 0;
    if (imageSlots.length > 35) error = 'Max 35 images. Extra files were ignored.';
    else error = '';
  }

  function removeSlot(i: number) {
    URL.revokeObjectURL(imageSlots[i].url);
    imageSlots = imageSlots.filter((_, idx) => idx !== i);
  }

  function moveSlot(from: number, to: number) {
    const arr = [...imageSlots];
    const [item] = arr.splice(from, 1);
    arr.splice(to, 0, item);
    imageSlots = arr;
  }

  // Drag sort
  function onDragStart(i: number) { dragSrcIdx = i; }
  function onDragOver(e: DragEvent, i: number) {
    e.preventDefault();
    if (dragSrcIdx !== null && dragSrcIdx !== i) moveSlot(dragSrcIdx, i), dragSrcIdx = i;
  }
  function onDragEnd() { dragSrcIdx = null; }

  // Drop zone
  async function handleDrop(e: DragEvent) {
    e.preventDefault(); isDragOver = false;
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    const arr = Array.from(files);
    if (mode === 'gif') { const g = arr.find(f => f.name.toLowerCase().endsWith('.gif')); if (g) await processGif(g); }
    else if (mode === 'video') { const v = arr.find(f => f.type.startsWith('video/')); if (v) await processVideo(v); }
    else await addImageFiles(arr);
  }

  function handleFileInput(e: Event) {
    const input = e.target as HTMLInputElement;
    if (!input.files) return;
    const arr = Array.from(input.files);
    if (mode === 'gif') processGif(arr[0]);
    else if (mode === 'video') processVideo(arr[0]);
    else addImageFiles(arr);
    input.value = '';
  }

  function clearAll() {
    imageSlots.forEach(s => URL.revokeObjectURL(s.url));
    imageSlots = []; sourceBitmaps = []; previewCanvases = []; error = ''; statusMsg = '';
  }

  // Rebuild preview when bgColor or zone changes
  $effect(() => {
    bgColor; selectedZoneId;
    const bitmaps = mode === 'images' ? imageSlots.map(s => s.bitmap) : sourceBitmaps;
    if (bitmaps.length > 0 && showPreview) buildPreview(bitmaps);
  });

  // Preview playback
  async function togglePreview() {
    const bitmaps = mode === 'images' ? imageSlots.map(s => s.bitmap) : sourceBitmaps;
    if (bitmaps.length === 0) return;
    if (!showPreview) {
      showPreview = true;
      isProcessing = true; statusMsg = 'Building preview…'; progress = 0;
      await buildPreview(bitmaps);
      isProcessing = false; progress = 100;
      previewFrameIdx = 0;
    } else {
      showPreview = false;
      stopPlayback();
    }
  }

  function startPlayback() {
    if (previewTimer) clearInterval(previewTimer);
    previewPlaying = true;
    previewTimer = setInterval(() => {
      previewFrameIdx = (previewFrameIdx + 1) % previewCanvases.length;
    }, 80);
  }

  function stopPlayback() {
    if (previewTimer) { clearInterval(previewTimer); previewTimer = null; }
    previewPlaying = false;
  }

  $effect(() => () => { stopPlayback(); imageSlots.forEach(s => URL.revokeObjectURL(s.url)); });

  // ── Apply ──
  async function apply() {
    const bitmaps = mode === 'images' ? imageSlots.map(s => s.bitmap) : sourceBitmaps;
    if (bitmaps.length === 0 || !allTargetsFound) return;
    isProcessing = true; progress = 0; statusMsg = 'Compositing frames…';
    try {
      const mappings: { target: BitmapFileInfo; source: File }[] = [];
      for (let i = 0; i < BOOT_FRAMES.length; i++) {
        const frame = BOOT_FRAMES[i];
        const target = targets[i]?.info;
        if (!target) continue;
        const bitmapIdx = Math.floor(i * bitmaps.length / BOOT_FRAMES.length);
        mappings.push({ target, source: await compositeFrame(bitmaps[bitmapIdx], frame.w, frame.h) });
        progress = Math.round((i / BOOT_FRAMES.length) * 100);
      }
      onApply(mappings);
    } catch (e) { error = `Apply failed: ${e instanceof Error ? e.message : String(e)}`; isProcessing = false; }
  }

  const bitmapCount = $derived(mode === 'images' ? imageSlots.length : sourceBitmaps.length);
  const canApply = $derived(bitmapCount > 0 && allTargetsFound && !isProcessing);
  const canPreview = $derived(bitmapCount > 0 && !isProcessing);

  function acceptAttr(): string {
    if (mode === 'gif') return '.gif,image/gif';
    if (mode === 'video') return 'video/*';
    return 'image/*';
  }
</script>

<div class="baw-backdrop">
  <div class="baw">
    <div class="baw-head">
      <span class="baw-title">boot animation</span>
      <button class="baw-close" onclick={onClose}><i class="fa-solid fa-xmark"></i></button>
    </div>

    <div class="baw-body">
      <!-- Left: controls -->
      <div class="baw-left">

        <!-- Mode tabs -->
        <div class="cg">
          <div class="cl">source</div>
          <div class="mode-tabs">
            <button class="mode-tab" class:active={mode==='gif'} onclick={() => { mode='gif'; clearAll(); }}>gif</button>
            <button class="mode-tab" class:active={mode==='video'} onclick={() => { mode='video'; clearAll(); }}>video</button>
            <button class="mode-tab" class:active={mode==='images'} onclick={() => { mode='images'; clearAll(); }}>images</button>
          </div>
        </div>

        <!-- Hint per mode -->
        {#if mode === 'gif'}
          <div class="hint">
            <i class="fa-solid fa-circle-info hint-icon"></i>
            <div>
              For best results, split your GIF into exactly 35 frames using ezgif first, then upload them as 35 images instead.
              <a class="hint-link" href="https://ezgif.com/split" target="_blank" rel="noopener">ezgif.com/split <i class="fa-solid fa-arrow-up-right-from-square"></i></a>
            </div>
          </div>
        {:else if mode === 'video'}
          <div class="hint">
            <i class="fa-solid fa-triangle-exclamation hint-icon"></i>
            <div>Frame extraction may not be accurate. For best results, export your animation as a GIF, split to 35 frames on ezgif, then use the images mode.</div>
          </div>
        {:else}
          <div class="hint">
            <i class="fa-solid fa-circle-info hint-icon"></i>
            <div>Name files in order (1.png, 2.png… or frame_001.png…). Files are sorted by filename automatically. Add one at a time or all at once.</div>
          </div>
        {/if}

        <!-- BG color -->
        <div class="cg">
          <div class="cl">background color</div>
          <div class="bg-row">
            <input class="bg-swatch" type="color" bind:value={bgColor} />
            <input class="bg-hex" type="text" bind:value={bgColor} maxlength="7" spellcheck="false" placeholder="#000000" />
          </div>
          <div class="cn">fills areas outside the content zone in each frame</div>
        </div>

        <!-- Drop zone (for gif/video, or add more for images) -->
        <div class="cg">
          <div class="cl">
            {#if mode === 'images'}
              upload images <span class="cl-count">({imageSlots.length}/35)</span>
            {:else}
              upload
            {/if}
          </div>
          <div class="dropzone" class:over={isDragOver}
            ondragover={(e) => { e.preventDefault(); isDragOver = true; }}
            ondragleave={() => (isDragOver = false)}
            ondrop={handleDrop}
            onclick={() => fileInputRef?.click()}
            onkeydown={(e) => (e.key==='Enter'||e.key===' ') && fileInputRef?.click()}
            role="button" tabindex="0">
            <input bind:this={fileInputRef} type="file"
              accept={acceptAttr()} multiple={mode === 'images'} hidden onchange={handleFileInput} />
            <i class="fa-solid fa-folder-open dz-icon"></i>
            <span class="dz-text">
              {#if mode === 'gif'}drop .gif or click{:else if mode === 'video'}drop video or click{:else}drop image(s) or click to add{/if}
            </span>
          </div>
          {#if error}<div class="dz-error"><i class="fa-solid fa-triangle-exclamation"></i> {error}</div>{/if}
        </div>

        <!-- Images mode: sortable list -->
        {#if mode === 'images' && imageSlots.length > 0}
          <div class="cg">
            <div class="cl">frame order <span class="cn-inline">drag to reorder</span></div>
            <div class="img-list">
              {#each imageSlots as slot, i}
                <div class="img-row" class:dragging={dragSrcIdx === i}
                  draggable="true"
                  ondragstart={() => onDragStart(i)}
                  ondragover={(e) => onDragOver(e, i)}
                  ondragend={onDragEnd}>
                  <i class="fa-solid fa-grip-vertical drag-handle"></i>
                  <img class="img-thumb" src={slot.url} alt={slot.name} />
                  <div class="img-info">
                    <span class="img-frame">frame {(10 + i).toString().padStart(4,'0')}</span>
                    <span class="img-name">{slot.name}</span>
                  </div>
                  <button class="img-del" onclick={() => removeSlot(i)}><i class="fa-solid fa-xmark"></i></button>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        <!-- Spacer -->
        <div class="cg-spacer"></div>

        <!-- Actions -->
        <div class="cg">
          <div class="action-row">
            <button class="abtn abtn-preview" onclick={togglePreview} disabled={!canPreview}>
              <i class="fa-solid fa-eye"></i> {showPreview ? 'hide' : 'preview'}
            </button>
            <button class="abtn abtn-apply" onclick={apply} disabled={!canApply}>
              <i class="fa-solid fa-floppy-disk"></i> apply
            </button>
          </div>
          {#if !allTargetsFound}
            <div class="cn-warn"><i class="fa-solid fa-triangle-exclamation"></i> {targets.filter(t => t.info).length}/35 boot frames found in firmware.</div>
          {/if}
        </div>
      </div>

      <!-- Center: preview panel -->
      <div class="baw-center">
        <div class="preview-head">
          <span class="cl">device preview</span>
          {#if showPreview && previewCanvases.length > 0}
            <div class="playback-row">
              <button class="play-btn" onclick={() => previewPlaying ? stopPlayback() : startPlayback()}>
                <i class="fa-solid {previewPlaying ? 'fa-pause' : 'fa-play'}"></i>
              </button>
              <span class="frame-counter">{previewFrameIdx + 10} / 44</span>
              <input class="frame-scrub" type="range" min="0" max={previewCanvases.length - 1}
                bind:value={previewFrameIdx} oninput={stopPlayback} />
            </div>
          {/if}
        </div>

        <div class="preview-body">
          {#if showPreview && previewCanvases.length > 0}
            <div class="preview-device">
              <img class="preview-frame" src={previewCanvases[previewFrameIdx]} alt="frame preview" />

            </div>
            <div class="preview-note">accumulated render — frame 0010 as base, each subsequent frame overlaid at (0,0)</div>
          {:else if showPreview}
            <div class="preview-empty"><i class="fa-solid fa-spinner fa-spin"></i></div>
          {:else}
            <div class="preview-empty">
              <i class="fa-solid fa-eye"></i>
              <span>click preview to see device-accurate render</span>
            </div>
          {/if}
        </div>
      </div>

      <!-- Right: zone + placement -->
      <div class="baw-right">
        <div class="baw-right-head">
          <span class="cl">content zone</span>
        </div>
        <div class="baw-right-body">
          <div class="cg">
            <div class="cl-sub">zone preset</div>
            <div class="zone-tabs">
              {#each ZONES as z}
                <button class="zone-tab" class:active={selectedZoneId === z.id}
                  onclick={() => { selectedZoneId = z.id; }}>
                  {z.label}
                </button>
              {/each}
            </div>
          </div>

          <div class="cg">
            <div class="cl-sub">
              placement
              <label class="stretch-toggle">
                <input type="checkbox" bind:checked={stretchMode} />
                stretch
              </label>
            </div>
            <div class="placement-editor"
              style="width:226px;height:{editorPxH}px;">
              <div class="pe-content"
                style="left:{contentPxL}px;top:{contentPxT}px;width:{contentPxW}px;height:{contentPxH}px;"
                onpointerdown={onEditorPointerDown}
                onpointermove={onEditorPointerMove}
                onpointerup={onEditorPointerUp}
                onpointercancel={onEditorPointerUp}>
              </div>

            </div>
            <div class="resize-sliders">
              <div class="rs-group">
                <div class="rs-header">
                  <span class="rs-label">size</span>
                  <span class="rs-val">{sizeSlider}%</span>
                </div>
                <input class="rs-range" type="range" min="5" max="100"
                  value={sizeSlider}
                  oninput={(e) => { const v = +(e.target as HTMLInputElement).value; sizeSlider = v; setSize(v); }} />
              </div>
            </div>
            <div class="cn">
              offset ({contentOffsetX},{contentOffsetY}) · {contentW}×{contentH}px
              <button class="cn-reset" onclick={fitToZone}>reset</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

{#if isProcessing}
  <LoadingWindow title="boot animation" message={statusMsg} progress={progress} />
{/if}

<style>
  .baw-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.75);
    display: flex; align-items: center; justify-content: center;
    z-index: 9997; padding: 24px;
  }
  .baw {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 100%; max-width: 1100px; max-height: 88vh;
    display: flex; flex-direction: column; overflow: hidden;
  }

  .baw-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .baw-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); }
  .baw-close { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 12px; transition: color 0.15s; }
  .baw-close:hover { color: var(--text); }

  .baw-body { display: grid; grid-template-columns: 220px 1fr 260px; overflow: hidden; flex: 1; min-height: 0; }

  /* Left */
  .baw-left {
    border-right: 1px solid var(--border); overflow-y: auto;
    display: flex; flex-direction: column; gap: 14px; padding: 16px;
  }
  .cg { display: flex; flex-direction: column; gap: 6px; }
  .cg-spacer { flex: 1; }
  .cl { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); display: flex; align-items: center; gap: 6px; }
  .cl-count { color: var(--text-faint); font-size: 9px; text-transform: none; letter-spacing: 0; }
  .cn { font-size: 10px; color: var(--text-faint); line-height: 1.5; }
  .cn-inline { font-size: 9px; color: var(--text-faint); text-transform: none; letter-spacing: 0; font-weight: 400; }
  .cn-warn { font-size: 10px; color: #a07040; display: flex; align-items: flex-start; gap: 5px; }

  /* Placement editor */
  .placement-editor {
    position: relative; background: var(--surface); border: 1px solid var(--border2);
    border-radius: 3px; overflow: hidden; box-sizing: border-box;
  }
  .pe-content {
    position: absolute;
    box-shadow: inset 0 0 0 1px var(--accent);
    background: rgba(155,111,212,0.15); cursor: move;
    box-sizing: border-box;
  }

  .resize-sliders { display: flex; flex-direction: column; gap: 6px; width: 100%; }
  .rs-row { display: flex; align-items: center; gap: 6px; }
  .rs-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-faint); width: 10px; flex-shrink: 0; }
  .rs-range { width: 100%; display: block; -webkit-appearance: none; appearance: none; height: 2px; background: var(--border2); outline: none; cursor: pointer; border-radius: 1px; }
  .rs-range::-webkit-slider-thumb { -webkit-appearance: none; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); cursor: pointer; }
  .rs-val { font-size: 10px; color: var(--text-faint); font-family: "DM Mono", monospace; width: 24px; text-align: right; flex-shrink: 0; }

  .stretch-toggle {
    display: flex; align-items: center; gap: 5px;
    font-size: 10px; color: var(--text-faint); cursor: pointer;
    text-transform: none; letter-spacing: 0; font-weight: 400; margin-left: auto;
  }
  .stretch-toggle input { cursor: pointer; accent-color: var(--accent); }
  .cn-reset {
    background: none; border: none; font-family: 'DM Mono', monospace;
    font-size: 10px; color: var(--accent); cursor: pointer; padding: 0;
    margin-left: 6px; opacity: 0.8; transition: opacity 0.15s;
  }
  .cn-reset:hover { opacity: 1; }

  .zone-tabs { display: flex; flex-direction: column; gap: 2px; }
  .zone-tab {
    background: none; border: none; border-bottom: 1px solid var(--border);
    padding: 5px 0; font-family: 'DM Mono', monospace; font-size: 11px;
    color: var(--text-dim); cursor: pointer; text-align: left;
    transition: color 0.15s, border-color 0.15s;
  }
  .zone-tab:hover { color: var(--text); }
  .zone-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .mode-tab {
    flex: 1; background: none; border: none; border-bottom: 2px solid transparent;
    padding: 5px 0; font-family: 'DM Mono', monospace; font-size: 11px;
    color: var(--text-dim); cursor: pointer; transition: color 0.15s, border-color 0.15s;
    margin-bottom: -1px;
  }
  .mode-tab:hover { color: var(--text); }
  .mode-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  /* Hint */
  .hint {
    display: flex; gap: 8px; align-items: flex-start;
    border-left: 2px solid var(--border2); padding-left: 10px;
    font-size: 11px; color: var(--text-faint); line-height: 1.55;
  }
  .hint-icon { margin-top: 1px; flex-shrink: 0; color: var(--accent); font-size: 11px; }
  .hint-link { color: var(--accent); text-decoration: none; display: inline-flex; align-items: center; gap: 4px; margin-top: 4px; opacity: 0.8; transition: opacity 0.15s; }
  .hint-link:hover { opacity: 1; }
  .hint-link i { font-size: 9px; }

  /* BG color */
  .bg-row { display: flex; align-items: center; gap: 8px; }
  .bg-swatch { width: 26px; height: 26px; border: 1px solid var(--border2); border-radius: 3px; cursor: pointer; padding: 0; flex-shrink: 0; background: none; }
  .bg-hex { flex: 1; background: transparent; border: none; border-bottom: 1px solid var(--border); padding: 3px 0; font-family: 'DM Mono', monospace; font-size: 12px; color: var(--text-dim); outline: none; text-transform: uppercase; }
  .bg-hex:focus { border-bottom-color: var(--accent); color: var(--text); }

  /* Drop zone */
  .dropzone {
    border: 1px dashed var(--border2); border-radius: 3px; padding: 14px 12px;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    cursor: pointer; transition: border-color 0.15s; outline: none; text-align: center;
  }
  .dropzone:hover, .dropzone.over { border-color: var(--accent); }
  .dz-icon { font-size: 14px; color: var(--text-faint); transition: color 0.15s; }
  .dropzone:hover .dz-icon, .dropzone.over .dz-icon { color: var(--accent); }
  .dz-text { font-size: 12px; color: var(--text-dim); }
  .dz-error { font-size: 11px; color: #c06050; display: flex; align-items: flex-start; gap: 6px; line-height: 1.5; }

  /* Image list */
  .img-list { display: flex; flex-direction: column; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); max-height: 220px; overflow-y: auto; }
  .img-row {
    display: flex; align-items: center; gap: 8px; padding: 5px 0;
    border-bottom: 1px solid var(--border); cursor: grab;
    transition: background 0.1s;
  }
  .img-row:last-child { border-bottom: none; }
  .img-row:hover { background: var(--surface2); }
  .img-row.dragging { opacity: 0.5; }
  .drag-handle { color: var(--text-faint); font-size: 10px; flex-shrink: 0; cursor: grab; }
  .img-thumb { width: 32px; height: 20px; object-fit: cover; border-radius: 2px; border: 1px solid var(--border); flex-shrink: 0; image-rendering: pixelated; }
  .img-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .img-frame { font-size: 9px; color: var(--text-faint); font-family: 'DM Mono', monospace; }
  .img-name { font-size: 11px; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .img-del { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 10px; flex-shrink: 0; padding: 2px; transition: color 0.15s; }
  .img-del:hover { color: var(--danger); }

  /* Actions */
  .action-row { display: flex; gap: 8px; }
  .abtn {
    flex: 1; display: flex; align-items: center; justify-content: center; gap: 7px;
    background: none; border: none; border-bottom: 1px solid var(--border2);
    font-family: 'DM Mono', monospace; font-size: 12px; padding: 6px 0;
    cursor: pointer; transition: color 0.15s, border-color 0.15s; color: var(--text-dim);
  }
  .abtn:hover:not(:disabled) { color: var(--text); border-bottom-color: var(--text-dim); }
  .abtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .abtn-preview { color: var(--text-dim); }
  .abtn-apply { color: var(--accent); border-bottom-color: var(--accent); }
  .abtn-apply:hover:not(:disabled) { opacity: 0.7; }

  /* Center preview */
  .baw-center { display: flex; flex-direction: column; overflow: hidden; min-height: 0; }

  /* Right: zone + placement */
  .baw-right { border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
  .baw-right-head { padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
  .baw-right-body { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 14px; }
  .cl-sub { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
  .preview-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; gap: 12px;
  }
  .playback-row { display: flex; align-items: center; gap: 10px; }
  .play-btn { background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; transition: color 0.15s; padding: 2px; }
  .play-btn:hover { color: var(--accent); }
  .frame-counter { font-size: 10px; color: var(--text-faint); font-family: 'DM Mono', monospace; white-space: nowrap; }
  .frame-scrub { -webkit-appearance: none; appearance: none; width: 120px; height: 2px; background: var(--border2); outline: none; cursor: pointer; border-radius: 1px; }
  .frame-scrub::-webkit-slider-thumb { -webkit-appearance: none; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); cursor: pointer; }

  .preview-body { flex: 1; overflow: auto; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding: 12px; gap: 10px; min-height: 0; }
  .preview-device { position: relative; display: block; line-height: 0; width: 100%; }
  .preview-frame { width: 100%; height: auto; border: 1px solid var(--border); border-radius: 3px; image-rendering: pixelated; display: block; }

  .preview-note { font-size: 10px; color: var(--text-faint); text-align: center; }
  .preview-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--text-faint); font-size: 12px; }
  .preview-empty i { font-size: 22px; opacity: 0.3; }
</style>
