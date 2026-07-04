<script lang="ts">
  import { onMount } from "svelte";
  import DeviceMockup from "$lib/components/firmware/DeviceMockup.svelte";
  import FontGridRenderer from "$lib/components/firmware/FontGridRenderer.svelte";
  import SequenceReplacerWindow from "$lib/components/firmware/SequenceReplacerWindow.svelte";
  import BootAnimationWindow from "$lib/components/firmware/BootAnimationWindow.svelte";
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
  let showBootAnimModal = $state(false);
  let showAboutModal = $state(false);

  const THEMES = [
    { id: 'reign',       label: 'reign' },
    { id: 'mocha',       label: 'catppuccin mocha' },
    { id: 'frappe',      label: 'catppuccin frappé' },
    { id: 'macchiato',   label: 'catppuccin macchiato' },
    { id: 'latte',       label: 'catppuccin latte' },
    { id: 'dark-orange', label: 'dark orange' },
    { id: 'parchment',   label: 'parchment' },
  ];
  const THEME_KEY = 'of_theme';
  let currentThemeIdx = $state(0);
  const currentTheme = $derived(THEMES[currentThemeIdx]);

  function applyTheme(idx: number) {
    currentThemeIdx = idx;
    document.documentElement.className = `theme-${THEMES[idx].id}`;
    try { localStorage.setItem(THEME_KEY, THEMES[idx].id); } catch {}
  }
  function cycleTheme() { applyTheme((currentThemeIdx + 1) % THEMES.length); }

  const DEVICE_COLORS: Record<string, string[]> = {
    echo: ['black', 'blue', 'green', 'orange'],
    mini: ['black', 'blue', 'pink'],
    unknown: [],
  };

  onMount(() => {
    try {
      const saved = localStorage.getItem(THEME_KEY);
      const idx = saved ? THEMES.findIndex(t => t.id === saved) : 0;
      applyTheme(idx >= 0 ? idx : 0);
    } catch { applyTheme(0); }

    initDebugShortcut();
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("paste", handlePaste);
    const cleanup = fwState.init();
    return () => { 
      cleanup(); 
      window.removeEventListener("keydown", handleKeyDown); 
      window.removeEventListener("paste", handlePaste); 
    };
  });

  $effect(() => {
    document.title = fwState.originalFirmwareData ? `${fwState.loadedFileName} — GlyphFlame` : "GlyphFlame";
  });

  function handleKeyDown(e: KeyboardEvent) {
    if (e.ctrlKey && e.key === "s") { 
      e.preventDefault(); 
      fwState.exportFirmware(); 
    }
  }

  async function handlePaste(e: ClipboardEvent) {
    if (fwState.isProcessing) return;
    const files: File[] = [];
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) { 
      const f = items[i].getAsFile(); 
      if (f) files.push(f); 
    }
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

    // BDFファイルがあれば優先処理
    const bdfFiles = files.filter(f => f.name.toLowerCase().endsWith('.bdf'));
    if (bdfFiles.length > 0) {
        for (const bdfFile of bdfFiles) {
            const result = await fwState.importBDF(bdfFile);
            alert(`BDFインポート完了: ${result.imported}文字更新 / ${result.skipped}文字スキップ`);
        }
        return;
    }

    // 既存の処理（フォント・画像）
    const fonts = files.filter(f => fwState.isFontFile(f));
    if (fonts.length) await fwState.replaceFont(fonts[0]);
    else if (files.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData)
        await fwState.replaceCurrentlySelectedImage(files[0]);
    else await fwState.handlePasteFiles(files);

    (e.target as HTMLInputElement).value = "";
}

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    isDragOver = true;
}
  function handleDragLeave(e: DragEvent) { e.preventDefault(); isDragOver = false; }
  async function handleDrop(e: DragEvent) {
    e.preventDefault(); isDragOver = false;
    const f = e.dataTransfer?.files[0]; 
    if (f) fwState.loadFirmware(f);
  }
    function handleImageDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer?.types.includes("Files")) {
      isImageDragOver = true;
    }
  }

  function handleImageDragLeave(e: DragEvent) {
    e.preventDefault();
    isImageDragOver = false;
  }
    // ====================== 画像エリアへのドラッグ&ドロップ ======================
  async function handleImageDrop(e: DragEvent) {
    e.preventDefault();
    isImageDragOver = false;

    if (!fwState.originalFirmwareData) {
      console.warn("ファームウェアが読み込まれていません");
      return;
    }

    const droppedFiles = Array.from(e.dataTransfer?.files ?? []);
    if (droppedFiles.length === 0) return;

    console.log(`📥 ドロップされたファイル: ${droppedFiles.length}個`);

    // ---------------------- 1. BDFフォントファイル ----------------------
    const bdfFiles = droppedFiles.filter(file => 
      file.name.toLowerCase().endsWith('.bdf')
    );

    if (bdfFiles.length > 0) {
      let totalImported = 0;
      let totalSkipped = 0;
      let totalProcessed = 0;

      for (const bdfFile of bdfFiles) {
        try {
          console.log(`🔤 BDF処理開始: ${bdfFile.name}`);
          const result = await fwState.importBDF(bdfFile);
          
          totalImported += result.imported;
          totalSkipped += result.skipped;
          totalProcessed += result.total;

          console.log(`BDF ${bdfFile.name} → 更新:${result.imported} / スキップ:${result.skipped}`);
        } catch (err: any) {
          console.error(`BDF処理失敗 (${bdfFile.name}):`, err);
          alert(`BDFファイルの処理に失敗しました:\n${bdfFile.name}\n\n${err.message || err}`);
        }
      }

      if (totalProcessed > 0) {
        alert(`✅ BDF Import Completed\n\n` +
      `Files: ${bdfFiles.length}\n` +
      `Total Glyphs: ${totalProcessed}\n` +
      `Updated: ${totalImported}\n` +
      `Skipped: ${totalSkipped}`);
      }
      return; // BDFを処理した場合はここで終了
    }

    // ---------------------- 2. 通常のフォントファイル (.fonなど) ----------------------
    const fontFiles = droppedFiles.filter(f => fwState.isFontFile(f));
    if (fontFiles.length > 0) {
      console.log(`🔤 フォントファイル検出: ${fontFiles[0].name}`);
      await fwState.replaceFont(fontFiles[0]);
      return;
    }

    // ---------------------- 3. 画像ファイル ----------------------
    const imageFiles = droppedFiles.filter(f => !fwState.isFontFile(f) && !f.name.toLowerCase().endsWith('.bdf'));

    if (imageFiles.length === 1 && 
        fwState.selectedNode?.type === "image" && 
        fwState.imageData) {
      // 現在選択中の画像1枚を置き換え
      console.log(`🖼️ 画像置き換え: ${imageFiles[0].name}`);
      await fwState.replaceCurrentlySelectedImage(imageFiles[0]);
    } 
    else if (imageFiles.length > 0) {
      // 複数画像の一括処理
      console.log(`🖼️ 画像一括処理: ${imageFiles.length}個`);
      await fwState.handlePasteFiles(imageFiles);
    } 
    else {
      console.warn("対応していないファイル形式です");
    }
  }

  function exportCurrentImage() {
    const img = fwState.imageData; 
    if (!img) return;
    const canvas = document.createElement("canvas");
    canvas.width = img.width; 
    canvas.height = img.height;
    const ctx = canvas.getContext("2d")!;
    const id = ctx.createImageData(img.width, img.height);
    for (let i = 0; i < img.width * img.height; i++) {
      const o = i * 2; 
      const px = (img.rgb565Data[o] << 8) | img.rgb565Data[o + 1];
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


  // ==================== FontGridRenderer 用 追加 ====================
async function handleFontUpdate(e: CustomEvent<{
    unicode: number;
    pixels: boolean[][];
    fontType: 'SMALL' | 'LARGE';
}>) {
    const { unicode, pixels, fontType } = e.detail;
    const success = await fwState.updateSingleFont(unicode, fontType, pixels);
    
    if (success && fwState.planeData) {
        // 配列を完全に新しいものに置き換えてSvelteに通知
        fwState.planeData.fonts = [...fwState.planeData.fonts];
        
        console.log(`✅ フォント更新 & 配列再作成: U+${unicode.toString(16).padStart(4, '0')}`);
    }
}
  // ================================================================

  // ==================== 編集文字数（derived） ====================
  const totalEdited = $derived(
    fwState.replacedSmallFontCharacters.size + fwState.replacedLargeFontCharacters.size
  );


  // ==================== Smallのみ反映 ====================
  async function applyAllSmall() {
    const count = await fwState.applyAllSmallFonts();
    if (count > 0) {
      alert(`✅ Small fonts applied: ${count} glyphs`);
    }
  }

  // ==================== Largeのみ反映 ====================
  async function applyAllLarge() {
    const count = await fwState.applyAllLargeFonts();
    if (count > 0) {
      alert(`✅ Large fonts applied: ${count} glyphs`);
    }
  }

// ==================== .imgダウンロード（重要修正） ====================
    async function downloadFirmware() {
        if (fwState.isProcessing) return;

        try {
            // 編集内容を強制的にWorkerに同期
            if (fwState.replacedSmallFontCharacters.size > 0 || 
                fwState.replacedLargeFontCharacters.size > 0) {
                console.log("🔄 ダウンロード前に編集内容を同期中...");
                await fwState.forceSyncAllEditedFonts();
            }

            // 通常のダウンロード処理を実行
            await fwState.exportFirmware();
        } catch (err) {
            console.error("ダウンロード処理エラー:", err);
            alert("An error occurred while downloading the firmware.");
        }
    }
    // =============================================================

  const importLabel = $derived(fwState.selectedNode?.type === "plane" ? "import image" : "import image");
  const canExportImage = $derived(fwState.selectedNode?.type === "image" && !!fwState.imageData);
  const availableColors = $derived(DEVICE_COLORS[fwState.firmwareType] ?? []);

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
        children: [] 
      }));
  });
</script>

<input type="file" bind:this={fileInput} hidden onchange={handleFileSelect} />
<input type="file" multiple hidden bind:this={editFileInput} onchange={handleEditFileSelect} />

{#if fwState.showLoadingWindow}
  <LoadingWindow title={fwState.loadingTitle} message={fwState.statusMessage} progress={fwState.progress} />
{/if}

<!-- drop screen -->
{#if !fwState.originalFirmwareData && !fwState.isProcessing}
  <div class="drop-screen" class:active={isDragOver}
    ondragover={handleDragOver} ondragleave={handleDragLeave} ondrop={handleDrop}
    onclick={() => fileInput?.click()}
    onkeydown={(e) => (e.key === "Enter" || e.key === " ") && fileInput?.click()}
    role="button" tabindex="0">
    <div class="drop-card">
      <div class="drop-logo">GlyphFlame<span class="drop-dot"></span></div>
      <p class="drop-sub">Font Editor for Snowsky Echo(non-mini)</p>
      <div class="drop-divider"></div>
      <div class="drop-hint">drop <code>.img</code> firmware here or click to browse</div>
    </div>
  </div>
{/if}

<!-- main app -->
{#if fwState.originalFirmwareData && fwState.treeNodes.length > 0 && !showSequenceReplacer}
  <div class="app">

    <!-- header -->
    <header class="header">
      <div class="hd-left">
        <button class="hd-brand" onclick={cycleTheme} title="cycle theme → {currentTheme.label}">
          GlyphFlame<span class="hd-dot"></span>
        </button>
        <span class="hd-sep">/</span>
        <span class="hd-file">{fwState.loadedFileName}</span>
        {#if fwState.firmwareType !== 'unknown'}
          <span class="hd-badge" class:badge-echo={fwState.firmwareType==='echo'} class:badge-mini={fwState.firmwareType==='mini'}>
            {fwState.firmwareType}
          </span>
        {/if}
      </div>
      <div class="hd-center">{fwState.statusMessage}</div>
      <div class="hd-right">
        {#if fwState.replacedImages.length > 0}
          <span class="hd-changed">{fwState.replacedImages.length} changed</span>
        {/if}
      </div>
    </header>

    <!-- 3 columns -->
    <div class="body">

      <!-- col 1: tree -->
      <aside class="col col-tree">
        <div class="col-label">files</div>
        <div class="search-wrap">
          <i class="fa-solid fa-magnifying-glass search-icon"></i>
          <input class="search-input" type="text" placeholder="search images…" bind:value={searchQuery} />
          {#if searchQuery}
            <button class="search-clear" onclick={() => (searchQuery = '')}><i class="fa-solid fa-xmark"></i></button>
          {/if}
        </div>
        <div class="tree-scroll">
          {#if searchResults !== null}
            {#if searchResults.length === 0}
              <div class="tree-empty">no results for "{searchQuery}"</div>
            {:else}
              <div class="tree-count">{searchResults.length} result{searchResults.length !== 1 ? 's' : ''}</div>
              {#each searchResults as node}
                <div class="tree-row" class:selected={fwState.selectedNode?.data?.name === node.data.name}
                  onclick={() => fwState.handleNodeClick(node)} role="button" tabindex="0"
                  onkeydown={(e) => e.key === 'Enter' && fwState.handleNodeClick(node)}>
                  {node.label}
                </div>
              {/each}
            {/if}
          {:else}
            <TreeView nodes={fwState.treeNodes} expanded={fwState.expandedNodes}
              selected={fwState.selectedNode?.id ?? ""}
              onSelect={(id) => fwState.handleSelectNode(id)}
              replacedImages={fwState.replacedImages} />
          {/if}
        </div>
      </aside>

      <!-- col 2: main view -->
      <main class="col col-main" class:drag-over={isImageDragOver}
        ondragover={handleImageDragOver} ondragleave={handleImageDragLeave}
        ondrop={handleImageDrop} role="region">

        {#if fwState.selectedNode?.type === "image" && fwState.imageData}
          {#if fwState.firmwareType !== 'unknown'}
            <div class="view-bar">
              <button class="vb-btn" class:active={showDevice} onclick={() => (showDevice = !showDevice)}>
                {#if showDevice}<i class="fa-solid fa-mobile-screen"></i> frame on
                {:else}<i class="fa-solid fa-image"></i> frame off{/if}
              </button>
              {#if showDevice && availableColors.length > 1}
                <span class="vb-sep"></span>
                {#each availableColors as color}
                  <button class="cswatch" class:active={fwState.deviceColor === color}
                    title={color} onclick={() => (fwState.deviceColor = color)}>
                    <span class="cswatch-dot" style="background:var(--swatch-{color});"></span>{color}
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
              <FontGridRenderer 
                fonts={fwState.planeData.fonts} 
                zoom={10}
                replacedSmallChars={fwState.replacedSmallFontCharacters}
                replacedLargeChars={fwState.replacedLargeFontCharacters}
                on:update={handleFontUpdate}
              />
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
            <span class="empty-arrow">→</span>
            <span class="empty-text">select a resource from the sidebar</span>
          </div>
        {/if}

      </main>

      <!-- col 3: tools -->
      <aside class="col col-tools">
        <div class="col-label">tools</div>

        <div class="tg">
          <div class="tg-label">selected</div>
          <div class="tg-filename">{fwState.imageData?.name ?? fwState.selectedNode?.label ?? '—'}</div>
        </div>

        <div class="tg">
          <div class="tg-label">edit</div>
          <button class="tbtn" onclick={() => editFileInput?.click()} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-upload"></i> {importLabel}
          </button>
          <button class="tbtn" onclick={exportCurrentImage} disabled={!canExportImage}>
            <i class="fa-solid fa-download"></i> export image
          </button>
          <button class="tbtn" onclick={() => fwState.bundleImagesAsZip()} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-file-zipper"></i> export zip
          </button>
        </div>

        <div class="tg">
          <div class="tg-label">firmware</div>
          <button class="tbtn tbtn-accent" onclick={downloadFirmware} disabled={fwState.isProcessing}>
            <i class="fa-solid fa-floppy-disk"></i> 
            download .img
            {#if fwState.replacedSmallFontCharacters.size + fwState.replacedLargeFontCharacters.size > 0}
              <span style="margin-left: 8px; font-size: 10px; opacity: 0.85;">
                ({fwState.replacedSmallFontCharacters.size + fwState.replacedLargeFontCharacters.size})
              </span>
            {/if}
          </button>
          
          <!-- Small / Large 分別反映 -->
    <button class="tbtn" onclick={applyAllSmall} 
                  disabled={fwState.replacedSmallFontCharacters.size === 0}>
            <i class="fa-solid fa-check"></i> Apply Small ({fwState.replacedSmallFontCharacters.size})
          </button>

    <button class="tbtn" onclick={applyAllLarge} 
                  disabled={fwState.replacedLargeFontCharacters.size === 0}>
            <i class="fa-solid fa-check"></i> Apply Large ({fwState.replacedLargeFontCharacters.size})
          </button>

          
          <button class="tbtn" 
                  onclick={async () => await fwState.alignAllGlyphsLeft()}
                  disabled={fwState.isProcessing || !fwState.planeData}>
            <i class="fa-solid fa-align-left"></i> 
            Align All Left
          </button>

          
          <button class="tbtn" onclick={() => (showSequenceReplacer = true)} disabled={fwState.imageList.length === 0}>
            <i class="fa-solid fa-arrows-rotate"></i> sequence replacer
          </button>
          <button class="tbtn" onclick={() => (showBootAnimModal = true)} disabled={fwState.imageList.length === 0}>
            <i class="fa-solid fa-film"></i> boot animation
          </button>
        </div>

        <div class="tg tg-footer">
          <button class="tbtn" onclick={() => fileInput?.click()}>
            <i class="fa-solid fa-folder-open"></i> open firmware
          </button>
          <div class="tg-row2">
            <button class="tbtn tbtn-sm" onclick={() => (showInstallModal = true)}>
              <i class="fa-solid fa-list-check"></i> guide
            </button>
            <button class="tbtn tbtn-sm" onclick={() => (showAboutModal = true)}>
              <i class="fa-solid fa-circle-info"></i> about
            </button>
          </div>
        </div>
      </aside>
    </div>
  </div>
{/if}

          

<!-- install modal -->
{#if showInstallModal}
  <div class="modal-back" onclick={(e) => e.target === e.currentTarget && (showInstallModal = false)}>
    <div class="modal">
      <div class="modal-head">installation guide</div>
      <div class="modal-body">
        <div class="modal-devices">
          <span class="device-pill echo-pill">echo → <code>ECHOVxxx.img</code></span>
          <span class="device-pill mini-pill">mini → <code>HIFIECxxx.img</code></span>
        </div>
        <div class="modal-warn">copy to <strong>internal memory</strong> — not the sd card</div>
        <div class="modal-steps">
          {#each [
            'remove the sd card',
            'turn the device on',
            'connect to pc via usb',
            'enter usb data mode on the device',
            'copy the .img file to the root of internal memory',
            'safely eject from pc',
            'turn off, then back on — update screen appears automatically',
            'once restarted normally, reinsert sd card',
          ] as step, i}
            <div class="modal-step">
              <span class="step-num">{i + 1}</span>
              <span>{step}</span>
            </div>
          {/each}
        </div>
        <div class="modal-note">the upgrade may format internal memory. back up your songs first.</div>
      </div>
      <div class="modal-foot">
        <button class="mbtn" onclick={() => (showInstallModal = false)}>done</button>
      </div>
    </div>
  </div>
{/if}

<!-- about modal -->
{#if showAboutModal}
  <div class="modal-back" onclick={(e) => e.target === e.currentTarget && (showAboutModal = false)}>
    <div class="modal">
      <div class="modal-head">about GlyphFlame</div>
      <div class="modal-body">
        <div class="ab-title">GlyphFlame<span class="ab-ver">v0.1</span></div>
        <p class="ab-desc">A web-based font editor for Snowsky Echo / Echo Mini firmware. Specialized tool for editing bitmap fonts (SMALL / LARGE) in firmware images.</p>
        <div class="ab-links">
          <a class="ab-link" href="https://github.com/SIEBEN5106/glyph-flame" target="_blank" rel="noopener">
            <i class="fa-brands fa-github"></i>
            <div>
              <div class="ab-link-title">GlyphFlame (this fork)</div>
              <div class="ab-link-sub">github.com/SIEBEN5106/glyph-flame</div>
            </div>
          </a>
          <a class="ab-link" href="https://github.com/unitreign/ocean-flame" target="_blank" rel="noopener">
            <i class="fa-brands fa-github"></i>
            <div>
              <div class="ab-link-title">oflame (original)</div>
              <div class="ab-link-sub">github.com/unitreign/ocean-flame</div>
            </div>
          </a>
          
         
        </div>
      </div>
      <div class="modal-foot">
        <button class="mbtn" onclick={() => (showAboutModal = false)}>done</button>
      </div>
    </div>
  </div>
{/if}

{#if showBootAnimModal}
  <BootAnimationWindow
    imageList={fwState.imageList}
    onApply={(mappings) => { fwState.handleSequenceReplace(mappings); showBootAnimModal = false; }}
    onClose={() => (showBootAnimModal = false)}
  />
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
  /* ── drop screen ── */
  .drop-screen {
    position: fixed; inset: 0; display: flex; align-items: center; justify-content: center;
    background: var(--bg); cursor: pointer; outline: none;
  }
  .drop-card {
    border: 1px solid var(--border); border-radius: 5px; padding: 40px 56px;
    max-width: 420px; width: 100%; transition: border-color 0.2s;
  }
  .drop-screen:hover .drop-card, .drop-screen.active .drop-card { border-color: var(--accent); }
  .drop-logo { font-size: 22px; font-weight: 500; color: var(--text); margin-bottom: 8px; letter-spacing: -0.3px; }
  .drop-dot { color: var(--accent); }
  .drop-sub { font-size: 11px; color: var(--text-dim); margin-bottom: 20px; line-height: 1.6; }
  .drop-divider { height: 1px; background: var(--border); margin-bottom: 20px; }
  .drop-hint { font-size: 12px; color: var(--text-dim); }
  .drop-hint code { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--text); background: var(--surface2); padding: 1px 5px; border-radius: 3px; border: 1px solid var(--border); }

  /* ── app ── */
  .app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

  /* ── header ── */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 20px; height: 40px;
    border-bottom: 1px solid var(--border); flex-shrink: 0;
    background: var(--bg);
  }
  .hd-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
  .hd-brand {
    background: none; border: none; cursor: pointer; padding: 0;
    font-family: 'DM Mono', monospace; font-size: 14px; font-weight: 500;
    color: var(--text); letter-spacing: -0.3px; transition: color 0.2s;
  }
  .hd-brand:hover { color: var(--accent); }
  .hd-dot { color: var(--accent); }
  .hd-sep { color: var(--text-faint); font-size: 12px; }
  .hd-file { font-size: 11px; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hd-badge {
    font-size: 9px; padding: 1px 5px; border-radius: 10px; border: 1px solid;
    letter-spacing: 0.5px; flex-shrink: 0;
  }
  .badge-echo { border-color: var(--accent); color: var(--accent); opacity: 0.8; }
  .badge-mini { border-color: var(--blue); color: var(--blue); opacity: 0.8; }
  .hd-center { font-size: 11px; color: var(--text-faint); white-space: nowrap; }
  .hd-right { display: flex; align-items: center; }
  .hd-changed {
    font-size: 9px; color: var(--accent); border: 1px solid; border-color: var(--accent);
    border-radius: 10px; padding: 1px 7px; opacity: 0.8; letter-spacing: 0.3px;
  }

  /* ── body ── */
  .body { flex: 1; display: grid; grid-template-columns: 300px 1fr 300px; overflow: hidden; min-height: 0; }

  /* ── columns ── */
  .col { display: flex; flex-direction: column; overflow: hidden; min-height: 0; background: var(--bg); }
  .col-tree { border-right: 1px solid var(--border); }
  .col-tools { border-left: 1px solid var(--border); overflow-y: auto; }

  .col-label {
    padding: 12px 16px 6px;
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--text-dim); flex-shrink: 0;
  }

  /* search & tree styles (省略せず全文) */
  .search-wrap {
    position: relative; padding: 4px 12px 8px; flex-shrink: 0;
    border-bottom: 1px solid var(--border);
  }
  .search-icon {
    position: absolute; left: 20px; top: 50%; transform: translateY(-60%);
    font-size: 10px; color: var(--text-faint); pointer-events: none;
  }
  .search-input {
    width: 100%; background: transparent; border: none; border-bottom: 1px solid var(--border);
    padding: 4px 24px 4px 20px; font-size: 12px; color: var(--text);
    outline: none; transition: border-color 0.2s;
  }
  .search-input::placeholder { color: var(--text-faint); }
  .search-input:focus { border-bottom-color: var(--accent); }
  .search-clear {
    position: absolute; right: 14px; top: 50%; transform: translateY(-60%);
    background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 10px;
    transition: color 0.2s;
  }
  .search-clear:hover { color: var(--text); }
  .tree-empty { padding: 16px; font-size: 11px; color: var(--text-faint); }
  .tree-count { padding: 8px 16px 4px; font-size: 10px; color: var(--text-faint); letter-spacing: 0.5px; }
  .tree-row {
    border-top: 1px solid var(--border); padding: 7px 16px;
    cursor: pointer; font-size: 12px; color: var(--text-dim);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background 0.15s, color 0.15s;
  }
  .tree-row:hover { background: var(--surface2); color: var(--text); }
  .tree-row.selected { color: var(--accent); background: var(--accent-bg); }

  /* tree-view styles */
  .tree-scroll { flex: 1; overflow-y: auto; min-height: 0; padding: 4px 0; }
  .tree-scroll :global(.tree-view) { font-size: 12px; color: var(--text-dim); }
  .tree-scroll :global(li) { list-style: none; }
  .tree-scroll :global(.leaf-node) {
    display: block; border-top: 1px solid var(--border); padding: 7px 16px;
    cursor: pointer; color: var(--text-dim); font-size: 12px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    transition: background 0.15s, color 0.15s;
  }
  .tree-scroll :global(.leaf-node:first-child) { border-top: none; }
  .tree-scroll :global(.leaf-node:hover) { background: var(--surface2); color: var(--text); }
  .tree-scroll :global(.leaf-node.selected) { color: var(--accent); background: var(--accent-bg); }
  .tree-scroll :global(.leaf-node.replaced) { color: var(--blue); }
  .tree-scroll :global(summary) {
    padding: 8px 16px 4px; cursor: pointer;
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px;
    color: var(--text-dim); list-style: none; display: flex; align-items: center; gap: 6px;
    user-select: none; transition: color 0.15s;
  }
  .tree-scroll :global(summary:hover) { color: var(--text); }
  .tree-scroll :global(summary::marker), .tree-scroll :global(summary::-webkit-details-marker) { display: none; }
  .tree-scroll :global(summary::before) {
    content: '→'; font-size: 10px; transition: transform 0.15s;
    display: inline-block; width: 12px; color: var(--accent); flex-shrink: 0;
  }
  .tree-scroll :global(details[open] > summary::before) { transform: rotate(90deg); }
  .tree-scroll :global(details > ul) { padding-left: 10px; border-left: 1px solid var(--border); margin-left: 10px; }
  .tree-scroll :global(details > ul .leaf-node) { padding-left: 16px !important; }

  /* main view styles */
  .col-main {
    background: var(--bg); overflow: hidden; display: flex; flex-direction: column;
    position: relative; min-height: 0;
  }
  .col-main.drag-over { outline: 1px dashed var(--accent); outline-offset: -4px; }

  .view-bar {
    display: flex; align-items: center; gap: 8px; padding: 8px 16px;
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .vb-btn {
    display: flex; align-items: center; gap: 6px; padding: 3px 0;
    background: none; border: none; border-bottom: 1px solid transparent;
    color: var(--text-dim); font-size: 11px; cursor: pointer;
    font-family: 'DM Mono', monospace; transition: color 0.15s, border-color 0.15s;
  }
  .vb-btn:hover { color: var(--text); }
  .vb-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  .vb-sep { width: 1px; height: 12px; background: var(--border); margin: 0 2px; }
  .cswatch {
    display: flex; align-items: center; gap: 5px; padding: 3px 0;
    border: none; border-bottom: 1px solid transparent; background: transparent;
    color: var(--text-dim); font-size: 11px; cursor: pointer;
    font-family: 'DM Mono', monospace; transition: color 0.15s, border-color 0.15s;
  }
  .cswatch:hover { color: var(--text); }
  .cswatch.active { color: var(--accent); border-bottom-color: var(--accent); }
  .cswatch-dot { width: 8px; height: 8px; border-radius: 50%; border: 1px solid var(--border2); flex-shrink: 0; }

  .panel-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
  .panel-head {
    display: flex; align-items: baseline; gap: 12px; padding: 12px 20px;
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .panel-title { font-size: 13px; font-weight: 500; color: var(--text); }
  .panel-meta { font-size: 11px; color: var(--text-dim); }
  .panel-scroll { flex: 1; overflow: auto; padding: 16px; min-height: 0; }
  .panel-scroll.no-pad { padding: 0; }

  .empty-view { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px; }
  .empty-arrow { color: var(--accent); font-size: 12px; }
  .empty-text { font-size: 12px; color: var(--text-faint); }

  /* tools column */
  .tg { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 5px; }
  .tg-footer { border-bottom: none; }
  .tg-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); margin-bottom: 3px; }
  .tg-filename {
    font-size: 11px; color: var(--text-dim); padding: 5px 0;
    border-bottom: 1px solid var(--border); white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }
  .tg-row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }

  .tbtn {
    display: flex; align-items: center; gap: 8px; padding: 7px 0;
    background: none; border: none; border-bottom: 1px solid var(--border);
    color: var(--text-dim); font-size: 12px; cursor: pointer;
    font-family: 'DM Mono', monospace; text-align: left; width: 100%;
    transition: color 0.15s, border-color 0.15s;
  }
  .tbtn:hover:not(:disabled) { color: var(--text); border-bottom-color: var(--text-dim); }
  .tbtn:disabled { opacity: 0.3; cursor: not-allowed; }
  .tbtn i { width: 14px; text-align: center; flex-shrink: 0; color: var(--text-faint); transition: color 0.15s; }
  .tbtn:hover:not(:disabled) i { color: var(--accent); }
  .tbtn-accent { color: var(--accent); border-bottom-color: var(--accent); opacity: 0.9; }
  .tbtn-accent:hover:not(:disabled) { opacity: 1; }
  .tbtn-sm { font-size: 11px; justify-content: center; border: 1px solid var(--border); border-radius: 3px; padding: 5px 8px; }
  .tbtn-sm:hover:not(:disabled) { border-color: var(--text-dim); }

  /* modals */
  .modal-back {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 10000;
  }
  .modal {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 460px; max-height: 80vh;
    overflow: hidden; display: flex; flex-direction: column;
  }
  .modal-head {
    padding: 14px 20px; border-bottom: 1px solid var(--border);
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim);
    flex-shrink: 0;
  }
  .modal-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
  .modal-foot {
    padding: 12px 20px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; flex-shrink: 0;
  }
  .mbtn {
    background: none; border: none; border-bottom: 1px solid var(--accent);
    color: var(--accent); font-family: 'DM Mono', monospace; font-size: 12px;
    padding: 3px 0; cursor: pointer; transition: opacity 0.15s;
  }
  .mbtn:hover { opacity: 0.7; }

  /* install guide */
  .modal-devices { display: flex; gap: 10px; flex-wrap: wrap; }
  .device-pill { font-size: 11px; padding: 3px 8px; border-radius: 10px; border: 1px solid; }
  .echo-pill { border-color: var(--accent); color: var(--accent); opacity: 0.8; }
  .mini-pill { border-color: var(--blue); color: var(--blue); opacity: 0.8; }
  .device-pill code { font-family: 'DM Mono', monospace; font-size: 10px; }
  .modal-warn {
    font-size: 12px; color: var(--text-dim); padding: 8px 12px;
    border-left: 2px solid var(--accent);
  }
  .modal-warn strong { color: var(--text); }
  .modal-steps { display: flex; flex-direction: column; gap: 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .modal-step {
    display: flex; align-items: flex-start; gap: 12px; padding: 8px 0;
    border-bottom: 1px solid var(--border); font-size: 12px; color: var(--text-dim);
  }
  .modal-step:last-child { border-bottom: none; }
  .step-num {
    font-size: 10px; color: var(--text-faint); min-width: 16px;
    flex-shrink: 0; padding-top: 1px;
  }
  .modal-note { font-size: 11px; color: var(--text-faint); }

  /* about */
  .ab-title { font-size: 18px; font-weight: 500; color: var(--text); letter-spacing: -0.3px; }
  .ab-ver { font-size: 12px; color: var(--text-dim); font-weight: 400; margin-left: 8px; }
  .ab-desc { font-size: 12px; color: var(--text-dim); line-height: 1.65; }
  .ab-links { display: flex; flex-direction: column; gap: 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .ab-link {
    display: flex; align-items: center; gap: 12px; padding: 10px 0;
    border-bottom: 1px solid var(--border); text-decoration: none;
    color: var(--text-dim); transition: color 0.15s;
  }
  .ab-link:last-child { border-bottom: none; }
</style>
