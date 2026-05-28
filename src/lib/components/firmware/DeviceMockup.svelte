<script lang="ts">
  interface Props {
    deviceType: 'echo' | 'mini' | 'unknown';
    deviceColor: string;
    imageData: { name: string; width: number; height: number; rgb565Data: Uint8Array } | null;
    showDevice: boolean;
  }

  let { deviceType, deviceColor, imageData, showDevice }: Props = $props();

  const FULL_SCREEN = { echo: { w: 480, h: 222 }, mini: { w: 320, h: 170 } };
  const OVERLAY = {
    echo:    { left: 140/796*100, top: 71/529*100, width: 514/796*100, height: 238/529*100 },
    mini:    { left: 126/555*100, top: 61/371*100, width: 287/555*100, height: 152/371*100 },
    unknown: { left: 0, top: 0, width: 100, height: 100 },
  };

  let canvasEl = $state<HTMLCanvasElement | null>(null);

  const isFullScreen = $derived(() => {
    if (!imageData || deviceType === 'unknown') return false;
    const fs = FULL_SCREEN[deviceType as 'echo' | 'mini'];
    return imageData.width === fs?.w && imageData.height === fs?.h;
  });
  const shouldShowDevice = $derived(showDevice && isFullScreen() && deviceType !== 'unknown');
  const cfg = $derived(OVERLAY[deviceType]);

  $effect(() => {
    imageData;
    if (!canvasEl || !imageData) return;
    const { width, height, rgb565Data } = imageData;
    canvasEl.width = width; canvasEl.height = height;
    const ctx = canvasEl.getContext('2d')!;
    const id = ctx.createImageData(width, height);
    for (let i = 0; i < width * height; i++) {
      const o = i * 2; const px = (rgb565Data[o] << 8) | rgb565Data[o + 1];
      id.data[i*4]   = Math.round(((px>>11)&0x1f)*255/31);
      id.data[i*4+1] = Math.round(((px>>5) &0x3f)*255/63);
      id.data[i*4+2] = Math.round((px      &0x1f)*255/31);
      id.data[i*4+3] = 255;
    }
    ctx.putImageData(id, 0, 0);
  });
</script>

<div class="mockup">
  {#if shouldShowDevice}
    <div class="device-wrap">
      <img class="device-img" src="/images/{deviceColor}{deviceType}.png" alt="{deviceType}" draggable="false" />
      {#if imageData}
        <canvas bind:this={canvasEl} class="screen-canvas"
          style="left:{cfg.left}%;top:{cfg.top}%;width:{cfg.width}%;height:{cfg.height}%;"></canvas>
      {/if}
    </div>
  {:else}
    <div class="raw-wrap">
      {#if imageData}
        <canvas bind:this={canvasEl} class="raw-canvas"></canvas>
        <div class="img-meta">{imageData.name} — {imageData.width}×{imageData.height}</div>
      {:else}
        <div class="empty">→ select an image from the sidebar</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .mockup { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 16px; gap: 10px; min-height: 0; }
  .device-wrap { position: relative; display: inline-block; line-height: 0; max-width: 100%; max-height: calc(100vh - 200px); }
  .device-img { max-width: 100%; max-height: calc(100vh - 200px); width: auto; height: auto; display: block; user-select: none; pointer-events: none; }
  .screen-canvas { position: absolute; image-rendering: pixelated; }
  .raw-wrap { display: flex; flex-direction: column; align-items: center; gap: 10px; max-width: 100%; width: 100%; }
  .raw-canvas { max-width: 100%; max-height: calc(100vh - 180px); width: auto; height: auto; image-rendering: pixelated; border: 1px solid var(--border); border-radius: 3px; display: block; }
  .img-meta { font-size: 10px; color: var(--text-faint); font-family: 'DM Mono', monospace; }
  .empty { font-size: 12px; color: var(--text-faint); }
</style>
