<script lang="ts">
  import type { BitmapFileInfo } from "../../rse/types";
  import { extractFrames } from "../../rse/utils/video-extractor";
  import { TreeView, LoadingWindow } from "../98css";
  import ImageRenderer from "./ImageRenderer.svelte";

  interface Props {
    targetImages: BitmapFileInfo[];
    onLoadImage: (image: BitmapFileInfo) => Promise<{ name: string; width: number; height: number; rgb565Data: Uint8Array } | null>;
    onApply: (mappings: { target: BitmapFileInfo; source: File }[]) => void;
    onCancel: () => void;
  }

  let { targetImages, onLoadImage, onApply, onCancel }: Props = $props();

  interface ImageGroup { prefix: string; displayName: string; images: BitmapFileInfo[]; }

  let selectedGroupId = $state("");
  let selectedImageId = $state("");
  let sourceFiles = $state<File[]>([]);
  let sourceFileMap = $state<Map<string, File>>(new Map());
  let isFromVideo = $state(false);
  let isDragOver = $state(false);
  let isExtracting = $state(false);
  let extractProgress = $state(0);
  let previewUrl = $state<string | null>(null);
  let currentSourceIndex = $state(0);
  let targetImageData = $state<{ name: string; width: number; height: number; rgb565Data: Uint8Array } | null>(null);
  let isLoadingTarget = $state(false);
  let fileInputRef: HTMLInputElement;

  function fileInputAction(node: HTMLInputElement) { fileInputRef = node; return {}; }

  let groups = $derived(parseImageGroups(targetImages));
  let groupNodes = $derived(groups.map((g) => ({ id: `group-${g.prefix}`, label: `${g.prefix} (${g.images.length})`, children: [] })));
  let fileNodes = $derived.by(() => {
    const g = groups.find((g) => `group-${g.prefix}` === selectedGroupId);
    if (!g) return [];
    return g.images.map((img, idx) => ({ id: `file-${g.prefix}-${idx}`, label: `${img.name} (${img.width}x${img.height})` }));
  });
  let selectedGroup = $derived(groups.find((g) => `group-${g.prefix}` === selectedGroupId));
  let selectedImage = $derived(selectedGroup?.images.find((_, idx) => `file-${selectedGroup.prefix}-${idx}` === selectedImageId) ?? null);

  $effect(() => {
    if (groups.length > 0 && !selectedGroupId) {
      selectedGroupId = `group-${groups[0].prefix}`;
      selectedImageId = `file-${groups[0].prefix}-0`;
    }
  });

  function parseImageGroups(images: BitmapFileInfo[]): ImageGroup[] {
    const map = new Map<string, BitmapFileInfo[]>();
    for (const img of images) {
      const key = extractGroupKey(img.name);
      if (!key.prefix) continue;
      if (!map.has(key.prefix)) map.set(key.prefix, []);
      map.get(key.prefix)!.push(img);
    }
    return Array.from(map.entries())
      .filter(([_, imgs]) => {
        if (imgs.length <= 1) return false;
        const d = `${imgs[0].width}x${imgs[0].height}`;
        return imgs.every((i) => `${i.width}x${i.height}` === d);
      })
      .map(([prefix, imgs]) => ({
        prefix,
        displayName: `${prefix} (${imgs[0].width}x${imgs[0].height})`,
        images: imgs.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })),
      }))
      .sort((a, b) => a.displayName.localeCompare(b.displayName));
  }

  function extractGroupKey(filename: string): { prefix: string; number: string } {
    const m1 = filename.match(/^(.+?)(\d+)_\((\d+),(\d+)\)\./);
    if (m1) return { prefix: m1[1], number: m1[2] };
    const m2 = filename.match(/^(.+?)[_-](\d+)[_-](\d+)[_.]/);
    if (m2) return { prefix: m2[1], number: m2[2] };
    const m3 = filename.match(/^(.+?)[_-](\d+)[_.]/);
    if (m3) { const p = m3[1]; return { prefix: p.endsWith('_') || p.endsWith('-') ? p : p + '_', number: m3[2] }; }
    return { prefix: '', number: '' };
  }

  async function handleGroupSelect(nodeId: string) {
    selectedGroupId = nodeId;
    const g = groups.find((g) => `group-${g.prefix}` === nodeId);
    if (g && g.images.length > 0) {
      selectedImageId = `file-${g.prefix}-0`;
      currentSourceIndex = 0;
      targetImageData = null;
      await loadTargetImage(g.images[0]);
      clearSources();
    }
    cleanupPreview(); updatePreview();
  }

  async function handleImageSelect(nodeId: string) {
    selectedImageId = nodeId;
    const match = nodeId.match(/file-(.+)-(\d+)/);
    if (match) {
      const g = groups.find((g) => g.prefix === match[1]);
      if (g) currentSourceIndex = parseInt(match[2], 10);
    }
    targetImageData = null;
    if (selectedImage) await loadTargetImage(selectedImage);
    updatePreview();
  }

  async function loadTargetImage(image: BitmapFileInfo) {
    isLoadingTarget = true;
    try { targetImageData = await onLoadImage(image); }
    catch (e) { console.error(e); targetImageData = null; }
    finally { isLoadingTarget = false; }
  }

  async function handleFilesDrop(files: File[]) {
    if (!files.length) return;
    const video = files.find((f) => f.type.startsWith('video/'));
    if (video) {
      isExtracting = true; extractProgress = 0; isFromVideo = true; sourceFileMap.clear();
      try {
        sourceFiles = await extractFrames(video, selectedGroup?.images.length || 30, (p) => { extractProgress = p; });
      } catch (e) { alert('Failed to extract frames: ' + (e instanceof Error ? e.message : String(e))); }
      finally { isExtracting = false; }
    } else {
      isFromVideo = false; sourceFiles = []; sourceFileMap.clear();
      if (selectedGroup) {
        const dropped = new Map<string, File>();
        for (const f of files) dropped.set(f.name.replace(/\.[^.]+$/, ''), f);
        for (const t of selectedGroup.images) {
          const base = t.name.replace(/\.[^.]+$/, '');
          const match = dropped.get(base);
          if (match) sourceFileMap.set(t.name, match);
        }
      }
    }
    updatePreview();
  }

  function handleFileSelect(e: Event) {
    const input = e.target as HTMLInputElement;
    if (input.files) handleFilesDrop(Array.from(input.files));
    input.value = '';
  }

  function updatePreview() {
    cleanupPreview();
    const f = isFromVideo ? sourceFiles[currentSourceIndex] : (selectedImage ? sourceFileMap.get(selectedImage.name) : undefined);
    if (f) previewUrl = URL.createObjectURL(f);
  }
  function cleanupPreview() { if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; } }
  function clearSources() { sourceFiles = []; sourceFileMap.clear(); isFromVideo = false; }

  function apply() {
    if (!selectedGroup) return;
    const mappings: { target: BitmapFileInfo; source: File }[] = [];
    if (isFromVideo) {
      if (!sourceFiles.length) return;
      for (let i = 0; i < selectedGroup.images.length && i < sourceFiles.length; i++)
        mappings.push({ target: selectedGroup.images[i], source: sourceFiles[i] });
    } else {
      if (!sourceFileMap.size) return;
      for (const t of selectedGroup.images) {
        const s = sourceFileMap.get(t.name);
        if (s) mappings.push({ target: t, source: s });
      }
    }
    if (mappings.length > 0) { onApply(mappings); cleanupPreview(); }
  }

  const canApply = $derived(
    !!selectedGroup && (isFromVideo ? sourceFiles.length > 0 : sourceFileMap.size > 0)
  );
  const applyCount = $derived(
    isFromVideo
      ? Math.min(sourceFiles.length, selectedGroup?.images.length || 0)
      : sourceFileMap.size
  );

  $effect(() => () => cleanupPreview());
</script>

<div class="sr">
  <div class="sr-desc">Select an image group, then drop replacement files (matching names) or a video to extract frames from.</div>

  <div class="sr-content">
    <!-- Groups -->
    <div class="sr-col">
      <div class="sr-col-head">Groups <span class="cnt">({groups.length})</span></div>
      <div class="sr-col-body">
        <TreeView nodes={groupNodes} selected={selectedGroupId} onSelect={handleGroupSelect} />
      </div>
    </div>

    <!-- Files in group -->
    <div class="sr-col">
      <div class="sr-col-head">
        {selectedGroup?.displayName || 'Files'}
        <span class="cnt">({selectedGroup?.images.length || 0})</span>
      </div>
      <div class="sr-col-body">
        {#if selectedGroup}
          <TreeView nodes={fileNodes} selected={selectedImageId} onSelect={handleImageSelect} />
        {:else}
          <div class="empty">Select a group</div>
        {/if}
      </div>
    </div>

    <!-- Preview + drop -->
    <div class="sr-col sr-col-right">
      <!-- Before/After -->
      <div class="sr-col-head">
        {selectedImage?.name ?? 'Preview'}
        {#if selectedImage}<span class="cnt">{selectedImage.width}×{selectedImage.height}</span>{/if}
      </div>
      <div class="preview-area">
        {#if selectedImage}
          <div class="preview-pair">
            <div class="preview-half">
              <div class="preview-label">Before</div>
              {#if isLoadingTarget}
                <div class="preview-loading">Loading…</div>
              {:else if targetImageData}
                <ImageRenderer name={targetImageData.name} width={targetImageData.width}
                  height={targetImageData.height} rgb565Data={targetImageData.rgb565Data} zoom={2} />
              {:else}
                <div class="preview-empty">No data</div>
              {/if}
            </div>
            <div class="preview-half">
              <div class="preview-label">After</div>
              {#if previewUrl}
                <img class="preview-img" src={previewUrl} alt="Preview" />
              {:else}
                <div class="preview-empty">Drop files below</div>
              {/if}
            </div>
          </div>
        {:else}
          <div class="empty">Select an image</div>
        {/if}
      </div>

      <!-- Drop zone -->
      <div class="dropzone-wrap">
        <div
          class="dropzone"
          class:over={isDragOver}
          ondragover={(e) => { e.preventDefault(); isDragOver = true; }}
          ondragleave={() => (isDragOver = false)}
          ondrop={(e) => { e.preventDefault(); isDragOver = false; if (e.dataTransfer?.files) handleFilesDrop(Array.from(e.dataTransfer.files)); }}
          onclick={() => fileInputRef?.click()}
          onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputRef?.click()}
          role="button" tabindex="0"
        >
          <input type="file" use:fileInputAction accept="image/*,video/*" multiple hidden onchange={handleFileSelect} />
          <span class="dz-icon">📁</span>
          <span class="dz-text">Drop images (matching names) or video</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="sr-footer">
    <button class="fbtn fbtn-accent" onclick={apply} disabled={!canApply}>
      Apply ({applyCount} image{applyCount !== 1 ? 's' : ''})
    </button>
  </div>
</div>

{#if isExtracting}
  <LoadingWindow message="Extracting frames from video..." progress={extractProgress} showProgress={true} />
{/if}

<style>
  .sr {
    display: flex; flex-direction: column; height: 100%;
    background: var(--panel); padding: 16px; gap: 12px;
  }
  .sr-desc { font-size: 12px; color: var(--text-dim); flex-shrink: 0; }

  .sr-content {
    flex: 1; display: grid; grid-template-columns: 200px 200px 1fr;
    gap: 12px; min-height: 0; overflow: hidden;
  }

  .sr-col {
    display: flex; flex-direction: column;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; overflow: hidden; min-height: 0;
  }
  .sr-col-right { border: none; background: transparent; gap: 8px; }

  .sr-col-head {
    padding: 8px 12px; background: var(--surface2);
    border-bottom: 1px solid var(--border);
    font-size: 11px; font-weight: 600; color: var(--text-dim);
    text-transform: uppercase; letter-spacing: 0.06em;
    flex-shrink: 0; display: flex; align-items: center; gap: 6px;
  }
  .cnt { color: var(--text-faint); font-weight: 400; }

  .sr-col-body { flex: 1; overflow-y: auto; min-height: 0; padding: 4px; }
  .sr-col-body :global(.tree-view) { font-size: 12px; }
  .sr-col-body :global(li) { list-style: none; }
  .sr-col-body :global(.leaf-node) {
    display: block; padding: 3px 8px; border-radius: 3px;
    cursor: pointer; color: var(--text-dim); font-size: 12px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background 0.1s;
  }
  .sr-col-body :global(.leaf-node:hover) { background: var(--panel); color: var(--text); }
  .sr-col-body :global(.leaf-node.selected) { background: var(--accent-bg); color: var(--text); border-left: 2px solid var(--accent); padding-left: 6px; }

  .empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-faint); font-size: 12px; }

  /* Preview */
  .preview-area {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; overflow: hidden; min-height: 0; display: flex; flex-direction: column;
  }
  .preview-pair { display: flex; flex: 1; min-height: 0; }
  .preview-half {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: flex-start; padding: 10px; gap: 8px;
    border-right: 1px solid var(--border);
    overflow: auto;
  }
  .preview-half:last-child { border-right: none; }
  .preview-label { font-size: 10px; font-weight: 700; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.06em; flex-shrink: 0; }
  .preview-loading, .preview-empty { font-size: 11px; color: var(--text-faint); margin-top: 20px; }
  .preview-img { max-width: 100%; max-height: 200px; image-rendering: pixelated; object-fit: contain; border-radius: 3px; border: 1px solid var(--border2); }
  .preview-half :global(.image-container) { background: transparent; border: none; padding: 0; }
  .preview-half :global(canvas) { max-width: 100%; height: auto; }

  /* Drop zone */
  .dropzone-wrap { flex-shrink: 0; }
  .dropzone {
    background: var(--surface); border: 1px dashed var(--border2); border-radius: 6px;
    padding: 16px; display: flex; align-items: center; justify-content: center;
    gap: 10px; cursor: pointer; transition: all 0.1s; outline: none;
  }
  .dropzone:hover, .dropzone.over { border-color: var(--accent); background: var(--accent-bg); }
  .dz-icon { font-size: 20px; }
  .dz-text { font-size: 12px; color: var(--text-dim); }

  /* Footer */
  .sr-footer { display: flex; justify-content: flex-end; flex-shrink: 0; }
  .fbtn {
    padding: 9px 20px; border-radius: 5px; font-size: 13px; cursor: pointer;
    border: 1px solid var(--border2); background: var(--surface); color: var(--text);
    transition: all 0.1s;
  }
  .fbtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .fbtn-accent { background: var(--accent-bg); border-color: var(--accent); font-weight: 600; }
  .fbtn-accent:hover:not(:disabled) { border-color: var(--accent2); }
</style>
