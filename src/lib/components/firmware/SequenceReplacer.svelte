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
      .map(([prefix, imgs]) => ({ prefix, displayName: `${prefix} (${imgs[0].width}x${imgs[0].height})`, images: imgs.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })) }))
      .sort((a, b) => a.displayName.localeCompare(b.displayName));
  }

  function extractGroupKey(filename: string): { prefix: string; number: string } {
    const m1 = filename.match(/^(.+?)(\d+)_\((\d+),(\d+)\)\./);
    if (m1) return { prefix: m1[1], number: m1[2] };
    const m2 = filename.match(/^(.+?)[_-](\d+)[_-](\d+)[_.]/);
    if (m2) return { prefix: m2[1], number: m2[2] };
    const m3 = filename.match(/^(.+?)[_-](\d+)[_.]/);
    if (m3) { const p = m3[1]; return { prefix: p.endsWith('_')||p.endsWith('-') ? p : p+'_', number: m3[2] }; }
    return { prefix: '', number: '' };
  }

  async function handleGroupSelect(nodeId: string) {
    selectedGroupId = nodeId;
    const g = groups.find((g) => `group-${g.prefix}` === nodeId);
    if (g && g.images.length > 0) {
      selectedImageId = `file-${g.prefix}-0`; currentSourceIndex = 0;
      targetImageData = null; await loadTargetImage(g.images[0]); clearSources();
    }
    cleanupPreview(); updatePreview();
  }

  async function handleImageSelect(nodeId: string) {
    selectedImageId = nodeId;
    const match = nodeId.match(/file-(.+)-(\d+)/);
    if (match) { const g = groups.find((g) => g.prefix === match[1]); if (g) currentSourceIndex = parseInt(match[2], 10); }
    targetImageData = null;
    if (selectedImage) await loadTargetImage(selectedImage);
    updatePreview();
  }

  async function loadTargetImage(image: BitmapFileInfo) {
    isLoadingTarget = true;
    try { targetImageData = await onLoadImage(image); } catch (e) { targetImageData = null; } finally { isLoadingTarget = false; }
  }

  async function handleFilesDrop(files: File[]) {
    if (!files.length) return;
    const video = files.find((f) => f.type.startsWith('video/'));
    if (video) {
      isExtracting = true; extractProgress = 0; isFromVideo = true; sourceFileMap.clear();
      try { sourceFiles = await extractFrames(video, selectedGroup?.images.length || 30, (p) => { extractProgress = p; }); }
      catch (e) { alert('failed to extract frames: ' + (e instanceof Error ? e.message : String(e))); }
      finally { isExtracting = false; }
    } else {
      isFromVideo = false; sourceFiles = []; sourceFileMap.clear();
      if (selectedGroup) {
        const dropped = new Map<string, File>();
        for (const f of files) dropped.set(f.name.replace(/\.[^.]+$/, ''), f);
        for (const t of selectedGroup.images) { const base = t.name.replace(/\.[^.]+$/, ''); const match = dropped.get(base); if (match) sourceFileMap.set(t.name, match); }
      }
    }
    updatePreview();
  }

  function handleFileSelect(e: Event) { const input = e.target as HTMLInputElement; if (input.files) handleFilesDrop(Array.from(input.files)); input.value = ''; }
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
      for (let i = 0; i < selectedGroup.images.length && i < sourceFiles.length; i++) mappings.push({ target: selectedGroup.images[i], source: sourceFiles[i] });
    } else {
      if (!sourceFileMap.size) return;
      for (const t of selectedGroup.images) { const s = sourceFileMap.get(t.name); if (s) mappings.push({ target: t, source: s }); }
    }
    if (mappings.length > 0) { onApply(mappings); cleanupPreview(); }
  }

  const canApply = $derived(!!selectedGroup && (isFromVideo ? sourceFiles.length > 0 : sourceFileMap.size > 0));
  const applyCount = $derived(isFromVideo ? Math.min(sourceFiles.length, selectedGroup?.images.length || 0) : sourceFileMap.size);

  $effect(() => () => cleanupPreview());
</script>

<div class="sr">
  <div class="sr-desc">select a group, then drop replacement files (matching filenames) or a video to extract frames from.</div>
  <div class="sr-content">

    <div class="sr-col">
      <div class="sr-col-head">groups</div>
      <div class="sr-col-body">
        <TreeView nodes={groupNodes} selected={selectedGroupId} onSelect={handleGroupSelect} />
      </div>
    </div>

    <div class="sr-col">
      <div class="sr-col-head">{selectedGroup ? `${selectedGroup.displayName}` : 'files'}</div>
      <div class="sr-col-body">
        {#if selectedGroup}
          <TreeView nodes={fileNodes} selected={selectedImageId} onSelect={handleImageSelect} />
        {:else}
          <div class="sr-empty">select a group</div>
        {/if}
      </div>
    </div>

    <div class="sr-col sr-col-right">
      <div class="sr-col-head">{selectedImage?.name ?? 'preview'}</div>
      <div class="preview-area">
        {#if selectedImage}
          <div class="preview-pair">
            <div class="preview-half">
              <div class="ph-label">before</div>
              {#if isLoadingTarget}
                <div class="ph-empty">loading…</div>
              {:else if targetImageData}
                <ImageRenderer name={targetImageData.name} width={targetImageData.width} height={targetImageData.height} rgb565Data={targetImageData.rgb565Data} zoom={2} />
              {:else}
                <div class="ph-empty">no data</div>
              {/if}
            </div>
            <div class="preview-half">
              <div class="ph-label">after</div>
              {#if previewUrl}
                <img class="ph-img" src={previewUrl} alt="preview" />
              {:else}
                <div class="ph-empty">drop files below</div>
              {/if}
            </div>
          </div>
        {:else}
          <div class="sr-empty">select an image</div>
        {/if}
      </div>
      <div class="dropzone-wrap">
        <div class="dropzone" class:over={isDragOver}
          ondragover={(e)=>{e.preventDefault();isDragOver=true;}}
          ondragleave={()=>(isDragOver=false)}
          ondrop={(e)=>{e.preventDefault();isDragOver=false;if(e.dataTransfer?.files)handleFilesDrop(Array.from(e.dataTransfer.files));}}
          onclick={()=>fileInputRef?.click()}
          onkeydown={(e)=>(e.key==='Enter'||e.key===' ')&&fileInputRef?.click()}
          role="button" tabindex="0">
          <input type="file" use:fileInputAction accept="image/*,video/*" multiple hidden onchange={handleFileSelect} />
          <i class="fa-solid fa-folder-open dz-icon"></i>
          <span class="dz-text">drop images or video here</span>
        </div>
      </div>
    </div>
  </div>

  <div class="sr-footer">
    <button class="dbtn dbtn-accent" onclick={apply} disabled={!canApply}>
      → apply ({applyCount} image{applyCount !== 1 ? 's' : ''})
    </button>
  </div>
</div>

{#if isExtracting}
  <LoadingWindow message="extracting frames from video…" progress={extractProgress} showProgress={true} />
{/if}

<style>
  .sr { display: flex; flex-direction: column; height: 100%; padding: 14px; gap: 12px; }
  .sr-desc { font-size: 11px; color: var(--text-faint); flex-shrink: 0; }
  .sr-content { flex: 1; display: grid; grid-template-columns: 190px 190px 1fr; gap: 10px; min-height: 0; overflow: hidden; }
  .sr-col { display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; min-height: 0; }
  .sr-col-right { border: none; background: transparent; gap: 8px; }
  .sr-col-head { padding: 7px 12px; border-bottom: 1px solid var(--border); font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-faint); flex-shrink: 0; }
  .sr-col-body { flex: 1; overflow-y: auto; min-height: 0; padding: 2px 0; }
  .sr-col-body :global(.tree-view) { font-size: 11px; }
  .sr-col-body :global(li) { list-style: none; }
  .sr-col-body :global(.leaf-node) { display: block; border-top: 1px solid var(--border); padding: 6px 12px; cursor: pointer; color: var(--text-dim); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: background 0.1s, color 0.1s; }
  .sr-col-body :global(.leaf-node:first-child) { border-top: none; }
  .sr-col-body :global(.leaf-node:hover) { background: var(--surface2); color: var(--text); }
  .sr-col-body :global(.leaf-node.selected) { color: var(--accent); background: var(--accent-bg); }
  .sr-empty { padding: 20px 12px; font-size: 11px; color: var(--text-faint); text-align: center; }

  .preview-area { flex: 1; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; min-height: 0; display: flex; flex-direction: column; }
  .preview-pair { display: flex; flex: 1; min-height: 0; }
  .preview-half { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 10px; gap: 8px; border-right: 1px solid var(--border); overflow: auto; }
  .preview-half:last-child { border-right: none; }
  .ph-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-faint); flex-shrink: 0; }
  .ph-empty { font-size: 11px; color: var(--text-faint); margin-top: 16px; }
  .ph-img { max-width: 100%; max-height: 200px; image-rendering: pixelated; object-fit: contain; border-radius: 2px; border: 1px solid var(--border); }
  .preview-half :global(.image-container) { background: transparent; border: none; padding: 0; }
  .preview-half :global(canvas) { max-width: 100%; height: auto; }

  .dropzone-wrap { flex-shrink: 0; }
  .dropzone {
    border: 1px dashed var(--border2); border-radius: 3px; padding: 14px;
    display: flex; align-items: center; justify-content: center; gap: 8px;
    cursor: pointer; transition: border-color 0.15s, color 0.15s; outline: none;
  }
  .dropzone:hover, .dropzone.over { border-color: var(--accent); }
  .dz-icon { font-size: 14px; color: var(--text-faint); transition: color 0.15s; }
  .dropzone:hover .dz-icon, .dropzone.over .dz-icon { color: var(--accent); }
  .dz-text { font-size: 11px; color: var(--text-faint); }

  .sr-footer { display: flex; justify-content: flex-end; flex-shrink: 0; }
  .dbtn { background: none; border: none; border-bottom: 1px solid var(--border2); color: var(--text-dim); font-family: 'DM Mono', monospace; font-size: 12px; padding: 3px 0; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .dbtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .dbtn:hover:not(:disabled) { color: var(--text); border-bottom-color: var(--text-dim); }
  .dbtn-accent { color: var(--accent); border-bottom-color: var(--accent); }
  .dbtn-accent:hover:not(:disabled) { opacity: 0.7; }
</style>
