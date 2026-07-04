<script lang="ts">
    import { Grid } from 'svelte-virtual';
    import { onMount } from 'svelte';
    import { createEventDispatcher } from 'svelte';

    interface FontData {
        unicode: number;
        fontType: 'SMALL' | 'LARGE';
        pixels: boolean[][];
    }

    interface Props {
        fonts: FontData[];
        zoom?: number;
        replacedSmallChars?: Set<number>;
        replacedLargeChars?: Set<number>;
        onCharSelect?: (unicode: number) => void;
    }

    let { 
        fonts = [], 
        zoom = 10, 
        replacedSmallChars = new Set<number>(), 
        replacedLargeChars = new Set<number>(),
        onCharSelect 
    }: Props = $props();

    const dispatch = createEventDispatcher<{
        update: { unicode: number; pixels: boolean[][]; fontType: 'SMALL' | 'LARGE' };
    }>();

    let selectedUnicode = $state<number | null>(null);
    let currentEditingPixels: boolean[][] = [];
    let showGrid = $state(true);        // ← 追加

    // 範囲選択
    let selection = $state<{ startX: number; startY: number; endX: number; endY: number } | null>(null);
    let isSelecting = $state(false);
    let wasRangeSelected = $state(false);   // ← 重要：範囲選択だったかを記録
    
    const LARGE_FONT_SIZE = 16;
    const fontWidth = $derived(fonts[0]?.pixels[0]?.length ?? LARGE_FONT_SIZE);
    const fontHeight = $derived(fonts[0]?.pixels.length ?? LARGE_FONT_SIZE);

    const itemWidth = $derived(fontWidth * zoom + 20);
    const itemHeight = $derived(fontHeight * zoom + 30);
    const itemCount = $derived(fonts.length);

    let containerHeight = $state(600);
    let containerElement: HTMLDivElement;

    let gridKey = $state(0);   // 強制再描画用

    $effect(() => {
        if (selectedUnicode !== null) loadCurrentGlyph();
    });

    function observeContainer() {
        const ro = new ResizeObserver((entries) => {
            containerHeight = entries[0]?.contentRect.height ?? 600;
        });
        if (containerElement) ro.observe(containerElement);
        return ro;
    }

        onMount(() => {
        const ro = observeContainer();

        // 枠外でも選択を続けるためのグローバルリスナー
        const handleGlobalMouseMove = (e: MouseEvent) => updateSelection(e);
        const handleGlobalMouseUp = () => endSelection();
        
        // グローバルキーイベント（より確実）
        const handleKeyDownGlobal = (e: KeyboardEvent) => {
            if (selectedUnicode !== null) {
                handleKeyDown(e);
            }
        };

        document.addEventListener('mousemove', handleGlobalMouseMove);
        document.addEventListener('mouseup', handleGlobalMouseUp);
        document.addEventListener('keydown', handleKeyDownGlobal);


        return () => {
            ro.disconnect();
            document.removeEventListener('mousemove', handleGlobalMouseMove);
            document.removeEventListener('mouseup', handleGlobalMouseUp);
            document.removeEventListener('keydown', handleKeyDownGlobal);
        };
    });

    function getHexString(unicode: number): string {
        return 'U+' + unicode.toString(16).padStart(4, '0').toUpperCase();
    }

    function handleSelect(unicode: number) {
        selectedUnicode = unicode;
        onCharSelect?.(unicode);
    }

    function loadCurrentGlyph() {
        const fontItem = fonts.find(f => f.unicode === selectedUnicode);
        if (!fontItem) return;
        currentEditingPixels = fontItem.pixels.map(row => [...row]);
        setTimeout(drawBigPreview, 30);
    }

        function drawBigPreview() {
        const canvas = document.getElementById('big-preview') as HTMLCanvasElement | null;
        if (!canvas) return;
        const ctx = canvas.getContext('2d', { alpha: false });
        if (!ctx) return;

        const zoomLevel = 20;
        canvas.width = fontWidth * zoomLevel;
        canvas.height = fontHeight * zoomLevel;

        // 背景
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // ピクセル描画
        for (let y = 0; y < currentEditingPixels.length; y++) {
            for (let x = 0; x < currentEditingPixels[y].length; x++) {
                ctx.fillStyle = currentEditingPixels[y][x] ? '#000000' : '#ffffff';
                ctx.fillRect(x * zoomLevel, y * zoomLevel, zoomLevel, zoomLevel);
            }
        }

        // ================ グリッドガイド ================
        if (showGrid) {
            ctx.strokeStyle = '#aaaaaa';
            ctx.lineWidth = 1;

            // 縦線
            for (let x = 0; x <= fontWidth; x++) {
                const pos = x * zoomLevel + 0.5;
                ctx.beginPath();
                ctx.moveTo(pos, 0);
                ctx.lineTo(pos, canvas.height);
                ctx.stroke();
            }

            // 横線
            for (let y = 0; y <= fontHeight; y++) {
                const pos = y * zoomLevel + 0.5;
                ctx.beginPath();
                ctx.moveTo(0, pos);
                ctx.lineTo(canvas.width, pos);
                ctx.stroke();
            }

            // 中央ガイドライン
            ctx.strokeStyle = '#ff8800';
            ctx.lineWidth = 2.5;
            const centerX = Math.floor(fontWidth / 2) * zoomLevel + 0.5;
            const centerY = Math.floor(fontHeight / 2) * zoomLevel + 0.5;

            ctx.beginPath();
            ctx.moveTo(centerX, 0);
            ctx.lineTo(centerX, canvas.height);
            ctx.stroke();

            ctx.beginPath();
            ctx.moveTo(0, centerY);
            ctx.lineTo(canvas.width, centerY);
            ctx.stroke();
        }
            // ================ 選択範囲のハイライト ================
        if (selection) {
            const left   = Math.min(selection.startX, selection.endX) * zoomLevel;
            const top    = Math.min(selection.startY, selection.endY) * zoomLevel;
            const width  = (Math.abs(selection.endX - selection.startX) + 1) * zoomLevel;
            const height = (Math.abs(selection.endY - selection.startY) + 1) * zoomLevel;

            // 半透明の青で塗る
            ctx.fillStyle = 'rgba(0, 120, 255, 0.3)';
            ctx.fillRect(left, top, width, height);

            // 青い枠線
            ctx.strokeStyle = '#0066ff';
            ctx.lineWidth = 3;
            ctx.strokeRect(left + 1.5, top + 1.5, width - 3, height - 3);
        }
        }

    // グリッド表示状態が変わったら再描画
    $effect(() => {
        if (selectedUnicode !== null) {
            drawBigPreview();
        }
    });

                        // ==================== 範囲選択機能（枠外追従版） ====================
            function startSelection(e: MouseEvent) {
        e.stopImmediatePropagation();
        isSelecting = true;
        wasRangeSelected = false;

        const canvas = e.currentTarget as HTMLCanvasElement;
        const rect = canvas.getBoundingClientRect();
        const x = Math.floor((e.clientX - rect.left) / 20);
        const y = Math.floor((e.clientY - rect.top) / 20);

        selection = { startX: x, startY: y, endX: x, endY: y };
    }

    function updateSelection(e: MouseEvent) {
        if (!isSelecting || !selection) return;

        const canvas = document.getElementById('big-preview') as HTMLCanvasElement;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();

        let x = Math.floor((e.clientX - rect.left) / 20);
        let y = Math.floor((e.clientY - rect.top) / 20);

        x = Math.max(0, Math.min(fontWidth - 1, x));
        y = Math.max(0, Math.min(fontHeight - 1, y));

        // 少しでも動いたら範囲選択とみなす
        if (Math.abs(x - selection.startX) > 0 || Math.abs(y - selection.startY) > 0) {
            wasRangeSelected = true;
        }

        selection.endX = x;
        selection.endY = y;
        drawBigPreview();
    }

    function endSelection() {
        isSelecting = false;
    }

    // 枠外クリックで選択解除
    function handleCanvasClick(e: MouseEvent) {
        if (ignoreNextClick) {
            ignoreNextClick = false;
            return;
        }

        // クリック位置が範囲選択中でなければ通常のドット編集
        if (!selection) {
            const canvas = e.currentTarget as HTMLCanvasElement;
            const rect = canvas.getBoundingClientRect();
            const x = Math.floor((e.clientX - rect.left) / 20);
            const y = Math.floor((e.clientY - rect.top) / 20);

            if (currentEditingPixels[y]?.[x] !== undefined) {
                currentEditingPixels[y][x] = !currentEditingPixels[y][x];
                drawBigPreview();
            }
        } else {
            // 枠外クリックで選択解除
            selection = null;
            drawBigPreview();
        }
    }

    // キーボードで選択範囲を移動
        function handleKeyDown(e: KeyboardEvent) {
        if (e.key === 'Escape' && selection) {
            e.preventDefault();
            clearSelection();
            return;
        }

        if (!selection) return;

        let dx = 0, dy = 0;
        const speed = e.shiftKey ? 3 : 1;

        switch (e.key) {
            case 'ArrowLeft':  dx = -speed; break;
            case 'ArrowRight': dx = speed; break;
            case 'ArrowUp':    dy = -speed; break;
            case 'ArrowDown':  dy = speed; break;
            default: return;
        }

        e.preventDefault();
        moveSelection(dx, dy);
    }

                                function handlePixelClick(e: MouseEvent) {
        // 範囲選択を行った直後はクリックを無視
        if (wasRangeSelected) {
            wasRangeSelected = false;   // 1回だけブロック
            return;
        }

        const canvas = e.currentTarget as HTMLCanvasElement;
        const rect = canvas.getBoundingClientRect();
        const x = Math.floor((e.clientX - rect.left) / 20);
        const y = Math.floor((e.clientY - rect.top) / 20);

        if (currentEditingPixels[y]?.[x] !== undefined) {
            currentEditingPixels[y][x] = !currentEditingPixels[y][x];
            drawBigPreview();
        }
    }

    // 選択範囲を解除
    function clearSelection() {
        selection = null;
        drawBigPreview();
    }

            // 選択範囲を移動（全方向対応版）
    function moveSelection(dx: number, dy: number) {
        if (!selection || !currentEditingPixels.length) return;

        const width = fontWidth;
        const height = fontHeight;

        // 選択範囲の実際の左上座標とサイズを計算
        const left   = Math.min(selection.startX, selection.endX);
        const top    = Math.min(selection.startY, selection.endY);
        const selWidth  = Math.abs(selection.endX - selection.startX) + 1;
        const selHeight = Math.abs(selection.endY - selection.startY) + 1;

        // バックアップ
        const backup: boolean[][] = [];
        for (let y = 0; y < selHeight; y++) {
            backup[y] = [];
            for (let x = 0; x < selWidth; x++) {
                backup[y][x] = currentEditingPixels[top + y][left + x];
            }
        }

        // 元の範囲をクリア
        for (let y = top; y < top + selHeight; y++) {
            for (let x = left; x < left + selWidth; x++) {
                currentEditingPixels[y][x] = false;
            }
        }

        // 新しい位置を計算（境界チェック）
        let newLeft = Math.max(0, Math.min(width - selWidth, left + dx));
        let newTop  = Math.max(0, Math.min(height - selHeight, top + dy));

        // 新しい位置に貼り付け
        for (let y = 0; y < selHeight; y++) {
            for (let x = 0; x < selWidth; x++) {
                const targetY = newTop + y;
                const targetX = newLeft + x;
                if (targetY < height && targetX < width) {
                    currentEditingPixels[targetY][targetX] = backup[y][x];
                }
            }
        }

        // 選択範囲の座標を更新（start/endの大小関係を保持）
        selection.startX = newLeft;
        selection.startY = newTop;
        selection.endX   = newLeft + selWidth - 1;
        selection.endY   = newTop + selHeight - 1;

        drawBigPreview();
        
        console.log(`移動 (${dx}, ${dy}) | サイズ: ${selWidth}×${selHeight}`);
    }

    function clearCurrentGlyph() {
        currentEditingPixels = currentEditingPixels.map(row => row.map(() => false));
        drawBigPreview();
    }

    function invertCurrentGlyph() {
        currentEditingPixels = currentEditingPixels.map(row => row.map(p => !p));
        drawBigPreview();
    }

        function alignLeftCurrentGlyph() {
        if (!currentEditingPixels.length) return;

        const height = currentEditingPixels.length;
        const width = currentEditingPixels[0].length;

        // 各行の左端と右端の黒ピクセル位置を調べる
        let minX = width;
        let maxX = 0;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                if (currentEditingPixels[y][x]) {
                    minX = Math.min(minX, x);
                    maxX = Math.max(maxX, x);
                }
            }
        }

        if (minX === width) return; // 空のグリフ

        const shift = minX; // 左に詰める量

        const newPixels: boolean[][] = Array(height).fill(0).map(() => Array(width).fill(false));

        for (let y = 0; y < height; y++) {
            for (let x = shift; x < width; x++) {
                newPixels[y][x - shift] = currentEditingPixels[y][x];
            }
        }

        currentEditingPixels = newPixels;
        drawBigPreview();

        console.log(`左詰め実行: ${shift}ピクセル左に移動`);
    }

function saveToFont() {
    if (selectedUnicode === null) return;

    const fontItem = fonts.find(f => f.unicode === selectedUnicode);
    if (!fontItem) return;

    const newPixels = currentEditingPixels.map(row => [...row]);
    fontItem.pixels = newPixels;

    dispatch('update', {
        unicode: selectedUnicode,
        pixels: newPixels,
        fontType: fontItem.fontType
    });

    if (fontItem.fontType === 'SMALL') {
        replacedSmallChars.add(selectedUnicode);
    } else {
        replacedLargeChars.add(selectedUnicode);
    }

    // === 強制再描画（これを強化）===
    gridKey = Date.now() + Math.random();   // より強力にキー変更
    console.log(`🔄 グリッド強制再描画: ${getHexString(selectedUnicode)}`);

    alert(`✅ Update completed: ${getHexString(selectedUnicode)}`);
}

    function renderFont(canvas: HTMLCanvasElement, font: FontData) {
        const draw = () => {
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const fw = font.pixels[0]?.length ?? LARGE_FONT_SIZE;
            const fh = font.pixels.length;
            canvas.width = fw * zoom;
            canvas.height = fh * zoom;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (let py = 0; py < fh; py++) {
                for (let px = 0; px < fw; px++) {
                    if (font.pixels[py][px]) {
                        ctx.fillStyle = '#000000';
                        ctx.fillRect(px * zoom, py * zoom, zoom, zoom);
                    }
                }
            }
        };
        draw();
    }
</script>

<div bind:this={containerElement} class="font-grid-container">
    <Grid
    itemCount={itemCount}
    itemWidth={itemWidth}
    itemHeight={itemHeight}
    height={containerHeight}
    key={gridKey}
    {fonts}   <!-- 念のため props を直接渡す -->
>
        <div 
            slot="item" 
            let:index 
            let:style 
            class="font-item" 
            {style}
            on:click={() => handleSelect(fonts[index].unicode)}
        >
            <div class="canvas-wrapper">
                <canvas
                    use:renderFont={fonts[index]}
                    class="font-canvas"
                    class:selected={fonts[index].unicode === selectedUnicode}
                ></canvas>
            </div>
            <div class="unicode-label">
                {getHexString(fonts[index].unicode)}
            </div>
        </div>
    </Grid>
</div>

<!-- 1文字編集エリア -->
{#if selectedUnicode !== null}
  <div class="single-char-editor">
    <h3>選択中: {String.fromCodePoint(selectedUnicode)} ({getHexString(selectedUnicode)})</h3>
    <div class="preview-area">
                                  <canvas 
        id="big-preview" 
        class="big-canvas" 
        tabindex="0"                    
        on:focus={() => {}}             
        on:mousedown={startSelection}
        on:mousemove={updateSelection}
        on:mouseup={endSelection}
        on:click={handlePixelClick}
    ></canvas>
    </div>
    <div class="editor-controls">
      <button on:click={invertCurrentGlyph}>Invert</button>
      
      <button 
        on:click={clearSelection}
        disabled={!selection}>
        Clear Selection
      </button>
      
       <!-- 新規追加 -->
      <button on:click={alignLeftCurrentGlyph}>Align Left</button>

      
      <!-- グリッドガイド オン/オフ -->
      <button 
        on:click={() => showGrid = !showGrid}
        style="background: {showGrid ? '#d0d0d0' : '#f0f0f0'}; font-weight: {showGrid ? 'bold' : 'normal'};">
        {showGrid ? 'Hide Grid' : 'Show Grid'}
      </button>

      <button on:click={saveToFont} style="background:#0066ff;color:white;font-weight:bold;">Apply This Glyph</button>
      <button on:click={() => selectedUnicode = null}>Close</button>
    </div>
  </div>
{/if}

<style>
    .font-grid-container {
        display: block;
        background-color: #c0c0c0;
        border: 2px solid;
        border-color: #dfdfdf #808080 #808080 #dfdfdf;
        padding: 4px;
        height: 100%;
        min-height: 0;
        overflow: hidden;
        box-sizing: border-box;
    }

    .font-item {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 4px;
        cursor: pointer;
    }

    .font-item:hover {
        background-color: #e0e0e0;
    }

    .canvas-wrapper {
        border: 2px solid;
        border-color: #808080 #dfdfdf #dfdfdf #808080;
        padding: 2px;
        background-color: #ffffff;
        display: inline-block;
    }

    .font-canvas {
        display: block;
        image-rendering: pixelated;
    }

    .font-canvas.selected {
        outline: 3px solid #ff8800;
        outline-offset: -3px;
    }

    .unicode-label {
        color: #000000;
        margin-top: 4px;
        text-align: center;
        font-size: 0.85em;
    }

    .single-char-editor {
        margin-top: 20px;
        padding: 20px;
        background: #f8f8f8;
        border: 3px solid #ff8800;
        border-radius: 6px;
    }

    .preview-area {
        background: white;
        padding: 10px;
        display: inline-block;
        border: 3px solid #808080;
    }

    .big-canvas {
        image-rendering: pixelated;
        cursor: crosshair;
    }

    .editor-controls {
        margin-top: 12px;
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
    }
</style>
