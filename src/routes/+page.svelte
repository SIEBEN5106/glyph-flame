<script lang="ts">
  import { onMount } from "svelte";
  import ImageRenderer from "$lib/components/firmware/ImageRenderer.svelte";
  import FontGridRenderer from "$lib/components/firmware/FontGridRenderer.svelte";
  import SequenceReplacerWindow from "$lib/components/firmware/SequenceReplacerWindow.svelte";
  import ColorTable from "$lib/components/firmware/ColorTable.svelte";
  import ColorDetailWindow from "$lib/components/firmware/ColorDetailWindow.svelte";
  import { initDebugShortcut } from "$lib/stores";
  import {
    Window,
    TreeView,
    StatusBar,
    WindowBody,
    LoadingWindow,
    WarningWindow,
    FontDebugWindow,
    TofuDebugWindow,
    FontSizeConfirmationWindow,
  } from "$lib/components/98css";
  import { FirmwareState } from "$lib/rse/firmware-state.svelte";

  // State
  const fwState = new FirmwareState();

  // Show sequence replacer mode (UI only state)
  let showSequenceReplacer = $state(false);

  // File input refs
  let fileInput = $state<HTMLInputElement | null>(null);
  let editFileInput = $state<HTMLInputElement | null>(null);
  let dropZone = $state<HTMLDivElement | null>(null);
  let isDragOver = $state(false);
  let isImageDragOver = $state(false);

  // Initialize
  onMount(() => {
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

  // Update document title dynamically
  $effect(() => {
    if (!fwState.firmwareData && !fwState.isProcessing) {
      document.title = "FlameOcean";
    } else if (fwState.showLoadingWindow) {
      document.title = "Loading - FlameOcean";
    } else if (fwState.selectedNode?.type === "image" && fwState.imageData) {
      document.title = `${fwState.imageData.name} - FlameOcean`;
    } else if (fwState.selectedNode?.type === "plane" && fwState.planeData) {
      const fontType = (fwState.selectedNode.data as any)?.fontType;
      document.title = `${fwState.planeData.name} (${fontType}) - FlameOcean`;
    } else {
      document.title = "Resource Browser - FlameOcean";
    }
  });

  // Keyboard handlers
  function handleKeyDown(e: KeyboardEvent) {
    if (e.ctrlKey && e.key === "s") {
      e.preventDefault();
      fwState.exportFirmware();
    }
  }

  // Paste handler
  async function handlePaste(e: ClipboardEvent) {
    if (fwState.isProcessing) {
      fwState.showWarningDialog("Busy", "A replacement is already in progress.");
      return;
    }

    const items = e.clipboardData?.items;
    if (!items) return;

    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const file = item.getAsFile();
      if (file) files.push(file);
    }

    if (files.length === 0) return;

    const fontFiles = files.filter(f => fwState.isFontFile(f));
    if (fontFiles.length > 0) {
      await fwState.replaceFont(fontFiles[0]);
      return;
    }

    const imageFiles = files.filter((f) => !fwState.isFontFile(f));
    if (imageFiles.length === 0) return;

    if (imageFiles.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData) {
      await fwState.replaceCurrentlySelectedImage(imageFiles[0]);
    } else {
      await fwState.handlePasteFiles(imageFiles);
    }
  }

  // File selection
  function handleFileSelect(e: Event) {
    const target = e.target as HTMLInputElement;
    const file = target.files?.[0];
    if (file) fwState.loadFirmware(file);
    target.value = "";
  }

  async function handleEditFileSelect(e: Event) {
    const target = e.target as HTMLInputElement;
    const files = target.files;
    if (files && files.length > 0) {
      const fileArray = Array.from(files);
      const fontFiles = fileArray.filter(f => fwState.isFontFile(f));
      if (fontFiles.length > 0) {
        await fwState.replaceFont(fontFiles[0]);
      } else if (fileArray.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData) {
        await fwState.replaceCurrentlySelectedImage(fileArray[0]);
      } else {
        await fwState.handlePasteFiles(fileArray);
      }
    }
    target.value = "";
  }

  // Drag and Drop
  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    isDragOver = true;
    if (dropZone) dropZone.classList.add("drag-over");
  }

  function handleDragLeave(e: DragEvent) {
    e.preventDefault();
    isDragOver = false;
    if (dropZone) dropZone.classList.remove("drag-over");
  }

  async function handleDrop(e: DragEvent) {
    e.preventDefault();
    isDragOver = false;
    if (dropZone) dropZone.classList.remove("drag-over");
    const file = e.dataTransfer?.files[0];
    if (file) fwState.loadFirmware(file);
  }

  function handleImageDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer?.types.includes("Files")) isImageDragOver = true;
  }

  function handleImageDragLeave(e: DragEvent) {
    e.preventDefault();
    isImageDragOver = false;
  }

  async function handleImageDrop(e: DragEvent) {
    e.preventDefault();
    isImageDragOver = false;
    if (!fwState.firmwareData || fwState.imageList.length === 0) return;

    const files = Array.from(e.dataTransfer?.files ?? []);
    if (files.length === 0) return;

    const fontFiles = files.filter(f => fwState.isFontFile(f));
    if (fontFiles.length > 0) {
      await fwState.replaceFont(fontFiles[0]);
      return;
    }

    if (files.length === 1 && fwState.selectedNode?.type === "image" && fwState.imageData) {
      await fwState.replaceCurrentlySelectedImage(files[0]);
    } else {
      await fwState.handlePasteFiles(files);
    }
  }

  function triggerFileInput() { fileInput?.click(); }
  function triggerEditFileInput() { editFileInput?.click(); }
</script>

<div class="page-wrapper">
  <input type="file" bind:this={fileInput} hidden onchange={handleFileSelect} />

  <div class="page-container">
    {#if !fwState.firmwareData && !fwState.isProcessing}
      <Window title="FlameOcean" width="500px" showClose={false}>
        <WindowBody>
          <div
            bind:this={dropZone}
            class="drop-zone"
            ondragover={handleDragOver}
            ondragleave={handleDragLeave}
            ondrop={handleDrop}
            onclick={triggerFileInput}
            onkeydown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), triggerFileInput())}
            role="button"
            tabindex="0"
          >
            <div class="drop-zone-content">
              <img
                src={isDragOver ? "/folder-drag-accept.png" : "/folder.png"}
                alt="Folder"
                class="folder-icon"
              />
              <div class="drop-text">Drop firmware file here or click to browse</div>
            </div>
          </div>
        </WindowBody>
      </Window>
    {/if}

    {#if fwState.showLoadingWindow}
      <LoadingWindow title={fwState.loadingTitle} message={fwState.statusMessage} progress={fwState.progress} />
    {/if}

    {#if fwState.firmwareData && fwState.treeNodes.length > 0 && !showSequenceReplacer}
      <Window
        title="Resource Browser"
        class="browser-window"
        onclose={() => fwState.handleCloseResourceViewer()}
      >
        <WindowBody>
          <div class="toolbar">
            <button class="toolbar-button" title="Open Firmware" onclick={triggerFileInput}>
              <img src="/document-open.png" alt="" class="toolbar-icon" />
            </button>
            <button class="toolbar-button" title="Save Firmware" onclick={() => fwState.exportFirmware()} disabled={fwState.isProcessing}>
              <img src="/document-save.png" alt="" class="toolbar-icon" />
            </button>
            <button class="toolbar-button" title="Download ZIP" onclick={() => fwState.bundleImagesAsZip()} disabled={fwState.isProcessing}>
              <img src="/document-export.png" alt="" class="toolbar-icon" />
            </button>
            <button class="toolbar-button" title="Import Files" onclick={triggerEditFileInput} disabled={fwState.isProcessing}>
              <img src="/document-edit.png" alt="" class="toolbar-icon" />
            </button>
            <button class="toolbar-button" title="Sequence Replacer" onclick={() => (showSequenceReplacer = true)} disabled={fwState.imageList.length === 0}>
              <img src="/video.png" alt="" class="toolbar-icon-small" />
            </button>
            <input type="file" multiple hidden bind:this={editFileInput} onchange={handleEditFileSelect} />
          </div>

          <div class="browser-layout">
            <div class="tree-panel">
              <TreeView
                nodes={fwState.treeNodes}
                expanded={fwState.expandedNodes}
                selected={fwState.selectedNode?.id ?? ""}
                onSelect={(id) => fwState.handleSelectNode(id)}
                replacedImages={fwState.replacedImages}
              />
            </div>

            <div
              class="content-panel"
              class:drag-over-images={isImageDragOver}
              ondragover={handleImageDragOver}
              ondragleave={handleImageDragLeave}
              ondrop={handleImageDrop}
              role="region"
            >
              {#if fwState.selectedNode}
                {#if fwState.isProcessing}
                  <div class="empty-state"><p>Loading {fwState.selectedNode.type}...</p></div>
                {:else if fwState.selectedNode.type === "plane" && fwState.planeData}
                  <div class="plane-header">
                    <h2>{fwState.planeData.name}</h2>
                    <p>U+{fwState.planeData.start.toString(16).toUpperCase()} - U+{fwState.planeData.end.toString(16).toUpperCase()}</p>
                    <p>{fwState.planeData.fonts.length} glyphs found</p>
                  </div>
                  <div class="flex-grow">
                    <FontGridRenderer
                      fonts={fwState.planeData.fonts}
                      zoom={10}
                      replacedSmallChars={fwState.replacedSmallFontCharacters}
                      replacedLargeChars={fwState.replacedLargeFontCharacters}
                    />
                  </div>
                {:else if fwState.selectedNode.type === "image" && fwState.imageData}
                  <ImageRenderer
                    name={fwState.imageData.name}
                    width={fwState.imageData.width}
                    height={fwState.imageData.height}
                    rgb565Data={fwState.imageData.rgb565Data}
                    zoom={2}
                  />
                {:else if fwState.selectedNode.type === "colors" && fwState.colorData}
                  <div class="colors-container">
                    {#if fwState.selectedNode.label.includes('General Text') || fwState.selectedNode.id === 'colors-menu'}
                      {#if fwState.colorData.menuColors.length > 0}
                        <ColorTable
                          entries={fwState.colorData.menuColors}
                          title="General Text Colors (Menu Text)"
                          height="100%"
                          onDoubleClick={(entry) => fwState.openColorDetail(entry)}
                        />
                      {:else}
                        <div class="empty-state"><p>No menu colors found (0 entries)</p></div>
                      {/if}
                    {:else if fwState.selectedNode.label.includes('Codec') || fwState.selectedNode.id === 'colors-flac'}
                      <ColorTable
                        entries={fwState.colorData.flacColors}
                        title="Codec Information Color (FLAC String)"
                        height="100%"
                        hideProperty={true}
                        onDoubleClick={(entry) => fwState.openColorDetail(entry)}
                      />
                    {:else if fwState.selectedNode.label.startsWith('Theme')}
                      {@const selectedTheme = (fwState.selectedNode.data && 'themeId' in fwState.selectedNode.data) ? fwState.selectedNode.data.themeId : undefined}
                      {@const themeColors = fwState.colorData.menuColors.filter(c => c.themeId === selectedTheme)}
                      {#if themeColors.length > 0}
                        <ColorTable
                          entries={themeColors}
                          title="Theme Colors"
                          height="100%"
                          onDoubleClick={(entry) => fwState.openColorDetail(entry)}
                        />
                      {:else}
                        <div class="empty-state"><p>No colors found for this theme</p></div>
                      {/if}
                    {:else}
                      <ColorTable
                        entries={[...fwState.colorData.menuColors, ...fwState.colorData.flacColors]}
                        title="All Colors"
                        height="100%"
                        onDoubleClick={(entry) => fwState.openColorDetail(entry)}
                      />
                    {/if}
                  </div>
                {:else}
                  <div class="empty-state"><p>No data available</p></div>
                {/if}
              {:else}
                <div class="empty-state"><p>Select a resource to view contents</p></div>
              {/if}
            </div>
          </div>
        </WindowBody>
      </Window>
    {/if}

    {#if fwState.firmwareData && fwState.treeNodes.length > 0 && showSequenceReplacer}
      <SequenceReplacerWindow
        targetImages={fwState.imageList}
        worker={fwState.worker!}
        onApply={(mappings) => fwState.handleSequenceReplace(mappings)}
        onClose={() => (showSequenceReplacer = false)}
      />
    {/if}
  </div>

  <footer class="status-footer">
    <div class="status-bar-window">
      <StatusBar statusFields={[{ text: fwState.statusMessage }]} />
    </div>
  </footer>

  {#if fwState.showWarning}
    <WarningWindow
      title={fwState.warningTitle}
      message={fwState.warningMessage}
      onconfirm={() => (fwState.showWarning = false)}
      showCancel={false}
    />
  {/if}

  {#if fwState.showFontDebug}
    <FontDebugWindow
      fileName={fwState.fontDebugFileName}
      message={fwState.fontDebugMessage}
      debugImages={fwState.fontDebugImages}
      onclose={() => (fwState.showFontDebug = false)}
    />
  {/if}

  {#if fwState.showTofuDebug}
    <TofuDebugWindow
      debugData={fwState.tofuDebugData}
      showConfirm={fwState.pendingReplacement !== null}
      onclose={() => fwState.pendingReplacement ? fwState.cancelFontReplacement() : (fwState.showTofuDebug = false)}
      onconfirm={() => fwState.confirmFontReplacement()}
    />
  {/if}

  {#if fwState.showFontSizeConfirmation && fwState.pendingFontConfirmation}
    <FontSizeConfirmationWindow
      fileName={fwState.pendingFontConfirmation.fileName}
      debugImages={fwState.pendingFontConfirmation.debugImages}
      oncancel={() => fwState.handleFontSizeCancel()}
      onconfirm={(type) => fwState.handleFontSizeConfirm(type)}
    />
  {/if}

  {#if fwState.showColorDetail && fwState.selectedColorDetail}
    <ColorDetailWindow
      detail={fwState.selectedColorDetail}
      onclose={() => (fwState.showColorDetail = false)}
    />
  {/if}
</div>

<style>
  :global(*) {
    box-sizing: border-box;
  }

  :global(body) {
    margin: 0;
    padding: 0;
    overflow: hidden;
  }

  .page-wrapper {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: url("/background.png") no-repeat center center;
    background-size: cover;
  }

  .page-container {
    max-width: 100vw;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    padding: 20px;
    overflow-y: auto;
  }

  .status-footer {
    flex-shrink: 0;
    background-color: #c0c0c0;
    border-top: 2px solid #ffffff;
  }

  .status-footer :global(.window) {
    border: none;
    box-shadow: none;
    margin: 0;
  }

  .status-footer :global(.status-bar) {
    border: none;
    margin: 0;
    font-family: "Pixelated MS Sans Serif", Arial;
  }

  :global(.window) {
    margin: 0 auto;
  }

  .drop-zone {
    padding: 40px;
    border: 2px inset #808080;
    background-color: #ffffff;
    text-align: center;
    cursor: pointer;
  }

  .drop-zone:hover {
    background-color: #eeeeee;
  }

  .drop-zone :global(.drag-over) {
    border: 2px inset #000080;
    background-color: #e0e0ff;
  }

  .drop-zone-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }

  .folder-icon {
    width: 64px;
    height: 64px;
    image-rendering: pixelated;
  }

  .drop-text {
    font-size: 14px;
    color: #000000;
  }

  :global(.browser-window) {
    max-width: 1024px;
    max-height: 768px;
    width: 100%;
    height: auto;
    margin: 64px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
  }

  :global(.browser-window .window-body) {
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* Toolbar styling */
  .toolbar {
    display: flex;
    gap: 2px;
    margin-bottom: 6px;
  }

  .toolbar-button {
    display: inline-flex;
    padding: 2px;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    min-height: 22px;
    cursor: pointer;
    box-shadow: none;
  }

  .toolbar-button:hover:not(.toolbar-button:active) {
    box-shadow: inset -1px -1px #0a0a0a,inset 1px 1px #fff,inset -2px -2px grey,inset 2px 2px #dfdfdf;
  }

  .toolbar-button:focus {
    outline: 1px dotted #000000;
    outline-offset: -4px;
  }

  .toolbar-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .toolbar-icon {
    width: 24px;
    height: 24px;
    image-rendering: pixelated;
    pointer-events: none;
  }

  .toolbar-icon-small {
    width: 16px;
    height: 16px;
    margin: 4px;
    image-rendering: pixelated;
    pointer-events: none;
  }

  .browser-layout {
    display: grid;
    grid-template-columns: 220px 1fr;
    grid-template-rows: 1fr;
    gap: 0;
    width: 100%;
    height: 600px;
    overflow: hidden;
  }

  .tree-panel {
    overflow: hidden;
    height: 100%;
  }

  .tree-panel :global(.tree-view) {
    height: 100%;
  }

  .content-panel {
    padding-left: 8px;
    padding-top: 8px;
    overflow: hidden;
    height: 100%;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
  }

  .content-panel.drag-over-images {
    background-color: #e0ffe0;
    border: 2px inset #008000;
  }

  .plane-header {
    padding-bottom: 8px;
  }

  .plane-header h2 {
    font-size: 16px;
    margin: 0 0 8px 0;
  }

  .plane-header p {
    font-size: 12px;
    margin: 4px 0;
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 300px;
    color: #808080;
  }

  .flex-grow {
    flex: 1 1 0;
    min-height: 0;
    box-sizing: border-box;
  }

  .colors-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
  }
</style>
