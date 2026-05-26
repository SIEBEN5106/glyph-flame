<script lang="ts">
  import { onMount } from "svelte";
  import DeviceMockup from "$lib/components/firmware/DeviceMockup.svelte";
  import FontGridRenderer from "$lib/components/firmware/FontGridRenderer.svelte";
  import SequenceReplacerWindow from "$lib/components/firmware/SequenceReplacerWindow.svelte";
  import ColorTable from "$lib/components/firmware/ColorTable.svelte";
  import ColorDetailWindow from "$lib/components/firmware/ColorDetailWindow.svelte";
  import { initDebugShortcut } from "$lib/stores";
  import {
    TreeView,
    LoadingWindow,
    WarningWindow,
    FontDebugWindow,
    TofuDebugWindow,
    FontSizeConfirmationWindow,
    ColorPicker,
  } from "$lib/components/98css";
  import { FirmwareState } from "$lib/rse/firmware-state.svelte";

  const fwState = new FirmwareState();

  let showSequenceReplacer = $state(false);
  let showDevice = $state(true);
  let fileInput = $state<HTMLInputElement | null>(null);
  let editFileInput = $state<HTMLInputElement | null>(null);
  let isDragOver = $state(false);
  let isImageDragOver = $state(false);
  let searchQuery = $state('');
  let showInstallModal = $state(false);
  let showAboutModal = $state(false);

  const THEMES = [
    { id: 'mocha',       label: 'Catppuccin Mocha' },
    { id: 'frappe',      label: 'Catppuccin Frappé' },
    { id: 'macchiato',   label: 'Catppuccin Macchiato' },
    { id: 'latte',       label: 'Catppuccin Latte' },
    { id: 'dark-orange', label: 'Dark Orange' },
    { id: 'parchment',   label: 'Parchment' },
  ];
  const THEME_STORAGE_KEY = 'of_theme';
  let currentThemeIdx = $state(0);
  const currentTheme = $derived(THEMES[currentThemeIdx]);

  function applyTheme(idx: number) {
    currentThemeIdx = idx;
    const theme = THEMES[idx];
    document.documentElement.className = `theme-${theme.id}`;
    try { localStorage.setItem(THEME_STORAGE_KEY, theme.id); } catch {}
  }

  function cycleTheme() {
    applyTheme((currentThemeIdx + 1) % THEMES.length);
  }

  const DEVICE_COLORS: Record<string, string[]> = {
    echo: ['black', 'blue', 'green', 'orange'],
    mini: ['black', 'blue', 'pink'],
    unknown: [],
  };

  onMount(() => {
    // Load saved theme
    try {
      const saved = localStorage.getItem(THEME_STORAGE_KEY);
      const idx = saved ? THEMES.findIndex(t => t.id === saved) : 0;
      applyTheme(idx >= 0 ? idx : 0);
    } catch { applyTheme(0); }

    initDebugShortcut();
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("paste", handlePaste);
    const cleanup = fwState.init();
    return () => { cleanup(); window.removeEventListener("keydown", handleKeyDown); window.removeEventListener("paste", handlePaste); };
  });

  $effect(() => {
    document.title = fwState.originalFirmwareData ? `${fwState.loadedFileName} — Ocean Flame` : "Ocean Flame";
  });

  function handleKeyDown(e: KeyboardEvent) {
    if (e.ctrlKey && e.key === "s") { e.preventDefault(); fwState.exportFirmware(); }
  }

  async function handlePaste(e: ClipboardEvent) {
    if (fwState.isProcessing) return;
    const files: File[] = [];
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) { const f = items[i].getAsFile(); if (f) files.push(f); }
    if (!files.length) return;
    const fonts = files.filter(f => fwState.isFontFile(f));
    if (fonts.length) { await fwState.replaceFont(fonts[0]); return; }
    const imgs = files.filter(f => !fwState.isFontFile(f));
    if (!imgs.length) return;
    if (imgs.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData)
      await fwState.replaceCurrentlySelectedImage(imgs[0]);
    else await fwState.handlePasteFiles(imgs);
  }

  function handleFileSelect(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) fwState.loadFirmware(f);
    (e.target as HTMLInputElement).value = "";
  }

  async function handleEditFileSelect(e: Event) {
    const files = Array.from((e.target as HTMLInputElement).files ?? []);
    if (!files.length) return;
    const fonts = files.filter(f => fwState.isFontFile(f));
    if (fonts.length) await fwState.replaceFont(fonts[0]);
    else if (files.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData)
      await fwState.replaceCurrentlySelectedImage(files[0]);
    else await fwState.handlePasteFiles(files);
    (e.target as HTMLInputElement).value = "";
  }

  function handleDragOver(e: DragEvent) { e.preventDefault(); isDragOver = true; }
  function handleDragLeave(e: DragEvent) { e.preventDefault(); isDragOver = false; }
  async function handleDrop(e: DragEvent) {
    e.preventDefault(); isDragOver = false;
    const f = e.dataTransfer?.files[0]; if (f) fwState.loadFirmware(f);
  }
  function handleImageDragOver(e: DragEvent) { e.preventDefault(); if (e.dataTransfer?.types.includes("Files")) isImageDragOver = true; }
  function handleImageDragLeave(e: DragEvent) { e.preventDefault(); isImageDragOver = false; }
  async function handleImageDrop(e: DragEvent) {
    e.preventDefault(); isImageDragOver = false;
    if (!fwState.originalFirmwareData) return;
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (!files.length) return;
    const fonts = files.filter(f => fwState.isFontFile(f));
    if (fonts.length) { await fwState.replaceFont(fonts[0]); return; }
    if (files.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData)
      await fwState.replaceCurrentlySelectedImage(files[0]);
    else await fwState.handlePasteFiles(files);
  }

  function exportCurrentImage() {
    const img = fwState.imageData; if (!img) return;
    const canvas = document.createElement("canvas");
    canvas.width = img.width; canvas.height = img.height;
    const ctx = canvas.getContext("2d")!;
    const id = ctx.createImageData(img.width, img.height);
    for (let i = 0; i < img.width * img.height; i++) {
      const o = i * 2; const px = (img.rgb565Data[o] << 8) | img.rgb565Data[o + 1];
      id.data[i*4]   = Math.round(((px>>11)&0x1f)*255/31);
      id.data[i*4+1] = Math.round(((px>>5) &0x3f)*255/63);
      id.data[i*4+2] = Math.round((px      &0x1f)*255/31);
      id.data[i*4+3] = 255;
    }
    ctx.putImageData(id, 0, 0);
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = img.name.replace(/\.BMP$/i, ".png");
    a.click();
  }

  // Dynamic import button label
  const importLabel = $derived(
    fwState.selectedNode?.type === "plane" ? "Import Font" : "Import Image"
  );
  const canExportImage = $derived(fwState.selectedNode?.type === "image" && !!fwState.imageData);
  const availableColors = $derived(DEVICE_COLORS[fwState.firmwareType] ?? []);

  // Search: flat filtered list of image nodes
  const searchResults = $derived.by(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return null;
    return fwState.imageList
      .filter(img => img.name.toLowerCase().includes(q))
      .map((img, i) => ({
        id: `search-${i}`,
        label: img.name,
        type: 'image' as const,
        data: img,
        children: [],
      }));
  });
</script>

<input type="file" bind:this={fileInput} hidden onchange={handleFileSelect} />
<input type="file" multiple hidden bind:this={editFileInput} onchange={handleEditFileSelect} />

{#if fwState.showLoadingWindow}
  <LoadingWindow title={fwState.loadingTitle} message={fwState.statusMessage} progress={fwState.progress} />
{/if}

{#if !fwState.originalFirmwareData && !fwState.isProcessing}
  <div class="drop-screen" class:active={isDragOver}
    ondragover={handleDragOver} ondragleave={handleDragLeave} ondrop={handleDrop}
    onclick={() => fileInput?.click()}
    onkeydown={(e) => (e.key === "Enter" || e.key === " ") && fileInput?.click()}
    role="button" tabindex="0">
    <div class="drop-card">
      <div class="drop-brand">
        <i class="fa-solid fa-fire drop-flame"></i>
        <div>
          <div class="drop-title">Ocean Flame</div>
          <div class="drop-sub">Snowsky Echo &amp; Echo Mini firmware editor</div>
        </div>
      </div>
      <div class="drop-divider"></div>
      <div class="drop-hint">Drop <code>.img</code> firmware here or click to browse</div>
    </div>
  </div>
{/if}

{#if fwState.originalFirmwareData && fwState.treeNodes.length > 0 && !showSequenceReplacer}
  <div class="app">

    <header class="header">
      <div class="hd-left">
        <button class="hd-brand-btn" onclick={cycleTheme} title="Cycle theme: {currentTheme.label}">
          <i class="fa-solid fa-fire hd-flame"></i>
          <span class="hd-name">Ocean Flame</span>
          <span class="hd-theme-dot" style="background:var(--accent);"></span>
        </button>
        <span class="hd-sep">|</span>
        <span class="hd-file">{fwState.loadedFileName}</span>
        {#if fwState.firmwareType !== 'unknown'}
          <span class="hd-badge" class:badge-echo={fwState.firmwareType==='echo'} class:badge-mini={fwState.firmwareType==='mini'}>
            {fwState.firmwareType.toUpperCase()}
          </span>
        {/if}
      </div>
      <div class="hd-status">{fwState.statusMessage}</div>
      <div class="hd-right">
        {#if fwState.replacedImages.length > 0}
          <span class="hd-changed">{fwState.replacedImages.length} changed</span>
        {/if}
      </div>
    </header>

    <div class="body">

      <!-- Col 1: File tree -->
      <aside class="col col-tree">
        <div class="col-head"><i class="fa-solid fa-circle col-dot-fa"></i>FILES</div>
        <div class="search-wrap">
          <input
            class="search-input"
            type="text"
            placeholder="Search images…"
            bind:value={searchQuery}
          />
          {#if searchQuery}
            <button class="search-clear" onclick={() => (searchQuery = '')} title="Clear"><i class="fa-solid fa-xmark"></i></button>
          {/if}
        </div>
        <div class="tree-scroll">
          {#if searchResults !== null}
            {#if searchResults.length === 0}
              <div class="search-empty">No images match "{searchQuery}"</div>
            {:else}
              <div class="search-count">{searchResults.length} result{searchResults.length !== 1 ? 's' : ''}</div>
              {#each searchResults as node}
                <div
                  class="leaf-node"
                  class:selected={fwState.selectedNode?.data?.name === node.data.name}
                  onclick={() => fwState.handleNodeClick(node)}
                  role="button" tabindex="0"
                  onkeydown={(e) => e.key === 'Enter' && fwState.handleNodeClick(node)}
                >
                  {node.label}
                </div>
              {/each}
            {/if}
          {:else}
            <TreeView
              nodes={fwState.treeNodes}
              expanded={fwState.expandedNodes}
              selected={fwState.selectedNode?.id ?? ""}
              onSelect={(id) => fwState.handleSelectNode(id)}
              replacedImages={fwState.replacedImages}
            />
          {/if}
        </div>
      </aside>

      <!-- Col 2: Main content -->
      <main class="col col-main" class:drag-over={isImageDragOver}
        ondragover={handleImageDragOver} ondragleave={handleImageDragLeave}
        ondrop={handleImageDrop} role="region">

        {#if fwState.selectedNode?.type === "image" && fwState.imageData}
          {#if fwState.firmwareType !== 'unknown'}
            <div class="view-bar">
              <button class="vb-btn" class:active={showDevice} onclick={() => (showDevice = !showDevice)}>
                {#if showDevice}<i class="fa-solid fa-mobile-screen"></i> Frame On{:else}<i class="fa-solid fa-image"></i> Frame Off{/if}
              </button>
              {#if showDevice && availableColors.length > 1}
                <div class="vb-sep"></div>
                {#each availableColors as color}
                  <button class="cswatch" class:active={fwState.deviceColor === color}
                    title={color} onclick={() => (fwState.deviceColor = color)}>
                    <span class="cswatch-dot" style="background:var(--swatch-{color});"></span>
                    {color}
                  </button>
                {/each}
              {/if}
            </div>
          {/if}
          <DeviceMockup deviceType={fwState.firmwareType} deviceColor={fwState.deviceColor}
            imageData={fwState.imageData} showDevice={showDevice} />

        {:else if fwState.selectedNode?.type === "plane" && fwState.planeData}
          <div class="panel-view">
            <div class="panel-head">
              <span class="panel-title">{fwState.planeData.name}</span>
              <span class="panel-meta">U+{fwState.planeData.start.toString(16).toUpperCase()}–U+{fwState.planeData.end.toString(16).toUpperCase()} · {fwState.planeData.fonts.length} glyphs</span>
            </div>
            <div class="panel-scroll">
              <FontGridRenderer fonts={fwState.planeData.fonts} zoom={10}
                replacedSmallChars={fwState.replacedSmallFontCharacters}
                replacedLargeChars={fwState.replacedLargeFontCharacters} />
            </div>
          </div>

        {:else if fwState.selectedNode?.type === "colors" && fwState.colorData}
          {@const nodeId = fwState.selectedNode.id}
          {@const nodeData = fwState.selectedNode.data as { themeId?: number; parentType?: string } | undefined}
          <div class="panel-view">
            <div class="panel-scroll no-pad">
              {#if nodeId === 'colors-menu'}
                <ColorTable entries={fwState.colorData.menuColors} height="100%" onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {:else if nodeId?.startsWith('colors-menu-theme-') && nodeData?.themeId !== undefined}
                <ColorTable entries={fwState.colorData.menuColors.filter(c => c.themeId === nodeData.themeId)} height="100%" onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {:else if nodeId === 'colors-flac'}
                <ColorTable entries={fwState.colorData.flacColors} height="100%" hideProperty={true} onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {:else if nodeId === 'colors-progress'}
                <ColorTable entries={fwState.colorData.progressColors} height="100%" hideProperty={true} hideSource={true} onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {:else if nodeId === 'colors-marquee'}
                <ColorTable entries={fwState.colorData.marqueeColors} height="100%" hideProperty={true} hideSource={true} onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {:else}
                <ColorTable entries={[...fwState.colorData.menuColors,...fwState.colorData.flacColors,...fwState.colorData.progressColors,...fwState.colorData.marqueeColors]} height="100%" onDoubleClick={(e) => fwState.openColorDetail(e)} />
              {/if}
            </div>
          </div>

        {:else}
          <div class="empty-view">
            <div class="empty-icon"><i class="fa-solid fa-fire"></i></div>
            <div class="empty-text">Select a resource from the sidebar</div>
          </div>
        {/if}
      </main>

      <!-- Col 3: Tools -->
      <aside class="col col-tools">
        <div class="col-head"><i class="fa-solid fa-circle col-dot-fa"></i>TOOLS</div>

        <div class="tg">
          <div class="tg-label">Selected</div>
          <div class="tg-filename">{fwState.imageData?.name ?? fwState.selectedNode?.label ?? '—'}</div>
        </div>

        <div class="tg">
          <div class="tg-label">Edit</div>
          <button class="tbtn" onclick={() => editFileInput?.click()} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-upload"></i> {importLabel}
          </button>
          <button class="tbtn" onclick={exportCurrentImage} disabled={!canExportImage}>
            <i class="fa-solid fa-download"></i> Export Image
          </button>
          <button class="tbtn" onclick={() => fwState.bundleImagesAsZip()} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-file-zipper"></i> Export ZIP
          </button>
        </div>

        <div class="tg">
          <div class="tg-label">Firmware</div>
          <button class="tbtn tbtn-accent" onclick={() => fwState.exportFirmware()} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-floppy-disk"></i> Download .img
          </button>
          <button class="tbtn" onclick={() => (showSequenceReplacer = true)} disabled={fwState.imageList.length === 0}>
            <i class="fa-solid fa-arrows-rotate"></i> Sequence Replacer
          </button>
        </div>

        <div class="tg tg-footer">
          <button class="tbtn tbtn-open" onclick={() => fileInput?.click()}>
            <i class="fa-solid fa-folder-open"></i> Open Firmware
          </button>
          <div class="tg-row2">
            <button class="tbtn tbtn-info" onclick={() => (showInstallModal = true)}>
              <i class="fa-solid fa-list-check"></i> Install Guide
            </button>
            <button class="tbtn tbtn-info" onclick={() => (showAboutModal = true)}>
              <i class="fa-solid fa-circle-info"></i> About
            </button>
          </div>
        </div>
      </aside>
    </div>
  </div>
{/if}

<!-- Install Guide Modal -->
{#if showInstallModal}
  <div class="modal-back" onclick={(e) => e.target === e.currentTarget && (showInstallModal = false)}>
    <div class="info-modal">
      <div class="info-modal-head"><i class="fa-solid fa-list-check"></i> Installation Guide</div>
      <div class="info-modal-body">

        <div class="im-section">
          <div class="im-device-label echo-label">Snowsky Echo</div>
          <div class="im-fw-name">Firmware filename: <code>ECHOVxxx.img</code></div>
        </div>

        <div class="im-section">
          <div class="im-device-label mini-label">Snowsky Echo Mini</div>
          <div class="im-fw-name">Firmware filename: <code>HIFIECxxx.img</code></div>
        </div>

        <div class="im-divider"></div>

        <div class="im-warn">⚠ Always copy the firmware to <strong>internal memory</strong>, not the SD card. Remove the SD card first.</div>

        <div class="im-steps">
          <div class="im-step"><span class="im-num">1</span>Remove the SD card from your device</div>
          <div class="im-step"><span class="im-num">2</span>Turn the device on</div>
          <div class="im-step"><span class="im-num">3</span>Connect to PC via USB</div>
          <div class="im-step"><span class="im-num">4</span>Enter USB Data mode on the device</div>
          <div class="im-step"><span class="im-num">5</span>Copy the <code>.img</code> file to the root of the internal memory</div>
          <div class="im-step"><span class="im-num">6</span>Safely eject from PC</div>
          <div class="im-step"><span class="im-num">7</span>Turn the device off, then back on — the firmware update screen will appear automatically</div>
          <div class="im-step"><span class="im-num">8</span>Once updated and restarted normally, reinsert your SD card</div>
        </div>

        <div class="im-note">⚠ The firmware upgrade may format the internal memory. Back up your songs before upgrading.</div>
      </div>
      <div class="info-modal-foot">
        <button class="pbtn" onclick={() => (showInstallModal = false)}>Done</button>
      </div>
    </div>
  </div>
{/if}

<!-- About Modal -->
{#if showAboutModal}
  <div class="modal-back" onclick={(e) => e.target === e.currentTarget && (showAboutModal = false)}>
    <div class="info-modal">
      <div class="info-modal-head"><i class="fa-solid fa-fire"></i> About Ocean Flame</div>
      <div class="info-modal-body">
        <div class="ab-name">Ocean Flame <span class="ab-ver">v1.0</span></div>
        <div class="ab-desc">A firmware image editor for Snowsky Echo and Echo Mini. Fork of FlameOcean with Echo (non-Mini) support and a redesigned UI.</div>
        <div class="ab-links">
          <a class="ab-link" href="https://github.com/unitreign/ocean-flame" target="_blank" rel="noopener">
            <span class="ab-link-icon"><i class="fa-brands fa-github"></i></span>
            <div>
              <div class="ab-link-title">Ocean Flame (this fork)</div>
              <div class="ab-link-sub">github.com/unitreign/ocean-flame</div>
            </div>
          </a>
          <a class="ab-link" href="https://github.com/Losses/flame-ocean-website" target="_blank" rel="noopener">
            <span class="ab-link-icon"><i class="fa-brands fa-github"></i></span>
            <div>
              <div class="ab-link-title">FlameOcean (original — Echo Mini)</div>
              <div class="ab-link-sub">github.com/Losses/flame-ocean-website</div>
            </div>
          </a>
          <a class="ab-link" href="https://www.youtube.com/watch?v=p8HDWJaDaP4" target="_blank" rel="noopener">
            <span class="ab-link-icon"><i class="fa-brands fa-youtube"></i></span>
            <div>
              <div class="ab-link-title">Basic Theming Guide (video)</div>
              <div class="ab-link-sub">youtube.com/watch?v=p8HDWJaDaP4</div>
            </div>
          </a>
        </div>
      </div>
      <div class="info-modal-foot">
        <button class="pbtn" onclick={() => (showAboutModal = false)}>Done</button>
      </div>
    </div>
  </div>
{/if}

{#if fwState.originalFirmwareData && showSequenceReplacer}
  <SequenceReplacerWindow targetImages={fwState.imageList} worker={fwState.worker!}
    onApply={(m) => fwState.handleSequenceReplace(m)} onClose={() => (showSequenceReplacer = false)} />
{/if}

{#if fwState.showWarning}
  <WarningWindow title={fwState.warningTitle} message={fwState.warningMessage}
    onconfirm={() => fwState.handleWarningConfirm()} oncancel={() => fwState.handleWarningCancel()}
    showCancel={fwState.pendingFlacUnlock} />
{/if}
{#if fwState.showFontDebug}
  <FontDebugWindow fileName={fwState.fontDebugFileName} message={fwState.fontDebugMessage}
    debugImages={fwState.fontDebugImages} onclose={() => (fwState.showFontDebug = false)} />
{/if}
{#if fwState.showTofuDebug}
  <TofuDebugWindow debugData={fwState.tofuDebugData} showConfirm={fwState.pendingReplacement !== null}
    onclose={() => fwState.pendingReplacement ? fwState.cancelFontReplacement() : (fwState.showTofuDebug = false)}
    onconfirm={() => fwState.confirmFontReplacement()} />
{/if}
{#if fwState.showFontSizeConfirmation && fwState.pendingFontConfirmation}
  <FontSizeConfirmationWindow fileName={fwState.pendingFontConfirmation.fileName}
    debugImages={fwState.pendingFontConfirmation.debugImages}
    oncancel={() => fwState.handleFontSizeCancel()} onconfirm={(t) => fwState.handleFontSizeConfirm(t)} />
{/if}
{#if fwState.showColorDetail && fwState.selectedColorDetail}
  <ColorDetailWindow detail={fwState.selectedColorDetail} onclose={() => (fwState.showColorDetail = false)}
    onedit={() => {
      const d = fwState.selectedColorDetail!;
      if (d.semantic.includes('Progress Bar')) fwState.openColorPicker('progress', d.themeId ?? 0);
      else if (d.semantic.includes('Marquee Overlay')) fwState.openColorPicker('marquee', d.themeId ?? 0);
      else if (d.semantic.includes('Codec Info') && fwState.flacPatched) fwState.openColorPicker('flac', d.themeId ?? 0);
    }}
    onunlock={() => fwState.showFlacUnlockWarning()} />
{/if}
{#if fwState.showColorPicker}
  <div class="modal-back">
    <ColorPicker onColorSelect={(rgb) => fwState.handleColorSelect(rgb)} onClose={() => fwState.closeColorPicker()} />
  </div>
{/if}

<style>
  .drop-screen {
    position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
    background: var(--bg); cursor: pointer; outline: none;
  }
  .drop-card {
    border: 1px solid var(--border); border-radius: 12px; padding: 40px 56px;
    background: var(--panel); max-width: 460px; width: 100%;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  .drop-screen:hover .drop-card, .drop-screen.active .drop-card {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent), 0 20px 60px rgba(0,0,0,0.5);
  }
  .drop-brand { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
  .drop-flame { font-size: 44px; }
  .drop-title { font-size: 26px; font-weight: 700; color: var(--text); letter-spacing: -0.5px; }
  .drop-sub { font-size: 12px; color: var(--text-dim); margin-top: 3px; }
  .drop-divider { height: 1px; background: var(--border); margin-bottom: 20px; }
  .drop-hint { font-size: 13px; color: var(--text-dim); text-align: center; }
  .drop-hint code { background: var(--surface); padding: 1px 6px; border-radius: 3px; color: var(--text); font-family: monospace; }

  .app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

  .header {
    display: flex; align-items: center; gap: 12px; padding: 0 20px; height: 42px;
    background: var(--panel); border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .hd-left { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
  .hd-flame { font-size: 16px; }
  .hd-name { font-weight: 700; color: var(--text); font-size: 14px; white-space: nowrap; }
  .hd-sep { color: var(--text-faint); }
  .hd-file { font-size: 12px; color: var(--text-dim); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hd-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; letter-spacing: 0.08em; flex-shrink: 0; }
  .badge-echo { background: var(--accent-bg); color: var(--accent2); border: 1px solid var(--accent); }
  .badge-mini { background: #0a1e32; color: #7ab0e0; border: 1px solid #1e4a7a; }
  .hd-status { font-size: 11px; color: var(--text-dim); white-space: nowrap; }
  .hd-right { display: flex; align-items: center; }
  .hd-changed { font-size: 11px; color: var(--accent2); background: var(--accent-bg); border: 1px solid var(--accent); border-radius: 4px; padding: 2px 8px; }

  .body { flex: 1; display: grid; grid-template-columns: 300px 1fr 300px; overflow: hidden; min-height: 0; }

  .col { display: flex; flex-direction: column; overflow: hidden; min-height: 0; background: var(--panel); }
  .col-tree { border-right: 1px solid var(--border); }
  .col-tools { border-left: 1px solid var(--border); overflow-y: auto; }

  .col-head {
    display: flex; align-items: center; gap: 8px; padding: 10px 16px 8px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.12em; color: var(--text-dim);
    text-transform: uppercase; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .col-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); opacity: 0.7; flex-shrink: 0; }

  /* Tree */
  .tree-scroll { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 6px 8px; min-height: 0; }
  .tree-scroll :global(.tree-view) { font-size: 13px; color: var(--text); }
  .tree-scroll :global(li) { list-style: none; }
  .tree-scroll :global(.leaf-node) {
    display: block; padding: 4px 12px; border-radius: 4px; cursor: pointer;
    color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background 0.1s, color 0.1s; font-size: 13px;
  }
  .tree-scroll :global(.leaf-node:hover) { background: var(--surface2); color: var(--text); }
  .tree-scroll :global(.leaf-node.selected) {
    background: var(--accent-bg) !important; color: var(--text) !important;
    border-left: 2px solid var(--accent); padding-left: 10px;
  }
  .tree-scroll :global(.leaf-node.replaced) { color: #7ab0e0; }
  .tree-scroll :global(summary) {
    padding: 5px 10px; cursor: pointer; font-size: 11px; font-weight: 600;
    color: var(--text-dim); letter-spacing: 0.06em; border-radius: 4px;
    list-style: none; display: flex; align-items: center; gap: 6px;
    user-select: none; transition: color 0.1s; text-transform: uppercase; margin-top: 4px;
  }
  .tree-scroll :global(summary:hover) { color: var(--text); }
  .tree-scroll :global(summary::marker), .tree-scroll :global(summary::-webkit-details-marker) { display: none; }
  .tree-scroll :global(summary::before) {
    content: '›'; font-size: 14px; transition: transform 0.15s;
    display: inline-block; width: 12px; color: var(--text-dim);
  }
  .tree-scroll :global(details[open] > summary::before) { transform: rotate(90deg); }
  .tree-scroll :global(details > ul) { padding-left: 12px; }

  /* Main col */
  .col-main {
    background: var(--bg); overflow: hidden; display: flex; flex-direction: column;
    position: relative; min-height: 0;
  }
  .col-main.drag-over { outline: 2px dashed var(--accent); outline-offset: -4px; }

  .view-bar {
    display: flex; align-items: center; gap: 6px; padding: 8px 14px;
    border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0;
  }
  .vb-btn {
    display: flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 5px;
    background: var(--surface); border: 1px solid var(--border2); color: var(--text-dim);
    font-size: 12px; cursor: pointer; transition: all 0.1s;
  }
  .vb-btn:hover { border-color: var(--accent); color: var(--text); }
  .vb-btn.active { background: var(--accent-bg); border-color: var(--accent); color: var(--text); }
  .vb-sep { width: 1px; height: 16px; background: var(--border); margin: 0 2px; }
  .cswatch {
    display: flex; align-items: center; gap: 5px; padding: 3px 8px; border-radius: 4px;
    border: 1px solid var(--border); background: transparent; color: var(--text-dim);
    font-size: 11px; cursor: pointer; transition: all 0.1s;
  }
  .cswatch:hover { border-color: var(--border2); color: var(--text); }
  .cswatch.active { border-color: var(--accent); background: var(--accent-bg); color: var(--text); }
  .cswatch-dot { width: 10px; height: 10px; border-radius: 50%; border: 1px solid var(--border2); flex-shrink: 0; }

  .panel-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .panel-head {
    display: flex; align-items: baseline; gap: 12px; padding: 14px 20px;
    border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0;
  }
  .panel-title { font-size: 14px; font-weight: 600; color: var(--text); }
  .panel-meta { font-size: 11px; color: var(--text-dim); }
  .panel-scroll { flex: 1; overflow: auto; padding: 16px; min-height: 0; }
  .panel-scroll.no-pad { padding: 0; }

  .empty-view { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
  .empty-icon { font-size: 32px; opacity: 0.15; }
  .empty-text { font-size: 13px; color: var(--text-faint); }

  /* Tools col */
  .tg { padding: 14px 16px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; }
  .tg-footer { border-bottom: none; margin-top: auto; }
  .tg-label { font-size: 10px; font-weight: 700; letter-spacing: 0.1em; color: var(--text-dim); text-transform: uppercase; margin-bottom: 2px; }
  .tg-filename {
    background: var(--surface); border: 1px solid var(--border); border-radius: 5px;
    padding: 7px 10px; font-size: 12px; color: var(--text); font-family: monospace;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-height: 32px;
    display: flex; align-items: center;
  }
  .tbtn {
    display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 5px;
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    font-size: 13px; cursor: pointer; transition: all 0.1s; width: 100%; text-align: left;
  }
  .tbtn:hover:not(:disabled) { background: var(--surface2); border-color: var(--border2); }
  .tbtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .tbtn-accent { background: var(--accent-bg); border-color: var(--accent); font-weight: 500; }
  .tbtn-accent:hover:not(:disabled) { border-color: var(--accent2); }
  .tbtn-open { }
  .tbtn-danger { color: #c07060; border-color: #3a1a12; }
  .tbtn-danger:hover:not(:disabled) { background: #2a100a; border-color: #803020; color: #e09080; }

  .modal-back { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 10001; }
  /* Search */
  .search-wrap {
    position: relative; padding: 8px 8px 4px; flex-shrink: 0;
    border-bottom: 1px solid var(--border);
  }
  .search-input {
    width: 100%; background: var(--surface); border: 1px solid var(--border);
    border-radius: 5px; padding: 6px 28px 6px 10px; font-size: 12px;
    color: var(--text); outline: none; transition: border-color 0.1s;
  }
  .search-input::placeholder { color: var(--text-faint); }
  .search-input:focus { border-color: var(--accent); }
  .search-clear {
    position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
    background: none; border: none; color: var(--text-dim); cursor: pointer;
    font-size: 11px; padding: 2px; line-height: 1;
  }
  .search-clear:hover { color: var(--text); }
  .search-empty { padding: 20px 12px; font-size: 12px; color: var(--text-faint); text-align: center; }
  .search-count { padding: 6px 12px 2px; font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; }
  .leaf-node {
    display: block; padding: 4px 12px; border-radius: 4px; cursor: pointer;
    color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-size: 13px; transition: background 0.1s, color 0.1s;
  }
  .leaf-node:hover { background: var(--surface2); color: var(--text); }
  .leaf-node.selected { background: var(--accent-bg); color: var(--text); border-left: 2px solid var(--accent); padding-left: 10px; }

  /* Two-column button row */
  .tg-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
  .tbtn-info { font-size: 11px; justify-content: center; color: var(--text-dim); }

  /* Info modals */
  .info-modal {
    background: var(--panel); border: 1px solid var(--border2); border-radius: 10px;
    width: 480px; max-height: 80vh; overflow: hidden; display: flex; flex-direction: column;
    box-shadow: 0 32px 80px rgba(0,0,0,0.7);
  }
  .info-modal-head {
    padding: 14px 20px; border-bottom: 1px solid var(--border);
    font-size: 14px; font-weight: 600; color: var(--text);
    background: var(--surface); flex-shrink: 0;
  }
  .info-modal-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .info-modal-foot {
    padding: 12px 20px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; flex-shrink: 0;
  }

  /* Install guide */
  .im-section { display: flex; align-items: baseline; gap: 10px; }
  .im-device-label { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 4px; flex-shrink: 0; }
  .echo-label { background: var(--accent-bg); color: var(--accent2); border: 1px solid var(--accent); }
  .mini-label { background: #0a1e32; color: #7ab0e0; border: 1px solid #1e4a7a; }
  .im-fw-name { font-size: 12px; color: var(--text-dim); }
  .im-fw-name code { background: var(--surface); padding: 1px 5px; border-radius: 3px; color: var(--text); font-family: monospace; font-size: 11px; }
  .im-divider { height: 1px; background: var(--border); }
  .im-warn { font-size: 12px; color: #d08840; background: #2a1a08; border: 1px solid #6a3810; border-radius: 5px; padding: 8px 12px; line-height: 1.5; }
  .im-warn strong { color: #e09040; }
  .im-steps { display: flex; flex-direction: column; gap: 6px; }
  .im-step { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; color: var(--text); line-height: 1.4; }
  .im-step code { background: var(--surface); padding: 0 4px; border-radius: 3px; font-size: 11px; font-family: monospace; color: var(--accent2); }
  .im-num {
    width: 20px; height: 20px; border-radius: 50%; background: var(--accent-bg);
    border: 1px solid var(--accent); color: var(--accent2); font-size: 10px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px;
  }
  .im-note { font-size: 11px; color: var(--text-dim); border-top: 1px solid var(--border); padding-top: 10px; line-height: 1.5; }

  /* About */
  .ab-name { font-size: 20px; font-weight: 700; color: var(--text); }
  .ab-ver { font-size: 13px; color: var(--text-dim); font-weight: 400; margin-left: 6px; }
  .ab-desc { font-size: 13px; color: var(--text-dim); line-height: 1.6; }
  .ab-links { display: flex; flex-direction: column; gap: 6px; }
  .ab-link {
    display: flex; align-items: center; gap: 12px; padding: 10px 14px;
    background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    text-decoration: none; transition: border-color 0.1s, background 0.1s;
  }
  .ab-link:hover { border-color: var(--accent); background: var(--surface2); }
  .ab-link-icon { font-size: 18px; flex-shrink: 0; width: 24px; text-align: center; }
  .ab-link-title { font-size: 13px; color: var(--text); font-weight: 500; }
  .ab-link-sub { font-size: 11px; color: var(--text-dim); font-family: monospace; margin-top: 2px; }
  .pbtn {
    padding: 8px 20px; border-radius: 5px; font-size: 13px; cursor: pointer;
    background: var(--accent-bg); border: 1px solid var(--accent); color: var(--text);
    font-weight: 500; transition: all 0.1s;
  }
  .pbtn:hover { border-color: var(--accent2); }
  /* Theme button in header */
  .hd-brand-btn {
    display: flex; align-items: center; gap: 8px;
    background: none; border: none; cursor: pointer; padding: 4px 8px;
    border-radius: 6px; transition: background 0.15s;
    color: inherit;
  }
  .hd-brand-btn:hover { background: var(--surface); }
  .hd-brand-btn:hover .hd-name { color: var(--accent2); }
  .hd-theme-dot {
    width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
    opacity: 0.8; transition: background 0.2s;
  }

  /* FA icon sizing fixes */
  .col-dot-fa { font-size: 6px; color: var(--accent); opacity: 0.7; }
  .drop-flame { font-size: 44px; color: var(--accent); }
  .hd-flame { font-size: 16px; color: var(--accent); }
  .empty-icon i { font-size: 32px; color: var(--text-faint); }
  .tbtn i, .vb-btn i { width: 14px; text-align: center; flex-shrink: 0; }
  .tbtn-info i { margin-right: 4px; }
  .im-steps .fa-solid, .im-note .fa-solid { margin-right: 2px; }
  .ab-link-icon i { font-size: 16px; }

</style>
