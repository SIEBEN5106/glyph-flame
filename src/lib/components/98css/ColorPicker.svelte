<script lang="ts">
  import { onMount } from 'svelte';

  interface Props {
    storageKey?: string;
    onColorSelect?: (rgb: { r: number; g: number; b: number }) => void;
    onClose?: () => void;
  }

  let { storageKey = 'of_custom_colors', onColorSelect, onClose }: Props = $props();

  const MAX_CHROMA = 0.37;

  let oklch = $state({ l: 0.7, c: 0.15, h: 200 });
  let customColors = $state<string[]>(Array(16).fill(''));
  let spectrumCanvas = $state<HTMLCanvasElement | undefined>();
  let lumCanvas = $state<HTMLCanvasElement | undefined>();
  let isDraggingSpectrum = $state(false);
  let isDraggingLum = $state(false);
  let hexInput = $state('');

  onMount(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          customColors = [...parsed.slice(0, 16), ...Array(16).fill('')].slice(0, 16);
        }
      }
    } catch {}
  });

  $effect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(customColors)); } catch {}
  });

  const rgb = $derived.by(() => {
    const [r, g, b] = oklchToRgb(oklch.l, oklch.c, oklch.h);
    return { r, g, b };
  });

  $effect(() => {
    hexInput = '#' +
      rgb.r.toString(16).padStart(2,'0') +
      rgb.g.toString(16).padStart(2,'0') +
      rgb.b.toString(16).padStart(2,'0');
  });

  // Draw spectrum
  $effect(() => {
    if (!spectrumCanvas) return;
    oklch.l; // redraw on lightness change
    const ctx = spectrumCanvas.getContext('2d')!;
    const w = spectrumCanvas.width, h = spectrumCanvas.height;
    const d = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
      const c = MAX_CHROMA * (1 - y / h);
      for (let x = 0; x < w; x++) {
        const hh = (x / w) * 360;
        const [r, g, b] = oklchToRgb(oklch.l, c, hh);
        const i = (y * w + x) * 4;
        d.data[i] = r; d.data[i+1] = g; d.data[i+2] = b; d.data[i+3] = 255;
      }
    }
    ctx.putImageData(d, 0, 0);
  });

  // Draw luminance bar
  $effect(() => {
    if (!lumCanvas) return;
    oklch.h; oklch.c; // redraw on hue/chroma change
    const ctx = lumCanvas.getContext('2d')!;
    const w = lumCanvas.width, h = lumCanvas.height;
    const d = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
      const l = 1 - y / h;
      const [r, g, b] = oklchToRgb(l, oklch.c, oklch.h);
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 4;
        d.data[i] = r; d.data[i+1] = g; d.data[i+2] = b; d.data[i+3] = 255;
      }
    }
    ctx.putImageData(d, 0, 0);
  });

  $effect(() => {
    const up = () => { isDraggingSpectrum = false; isDraggingLum = false; };
    const move = (e: MouseEvent) => {
      if (isDraggingSpectrum) onSpectrumMove(e);
      if (isDraggingLum) onLumMove(e);
    };
    window.addEventListener('mouseup', up);
    window.addEventListener('mousemove', move);
    return () => { window.removeEventListener('mouseup', up); window.removeEventListener('mousemove', move); };
  });

  // Math
  function clamp(x: number, lo: number, hi: number) { return Math.min(Math.max(x, lo), hi); }
  function linearToSrgb(c: number) { return c >= 0.0031308 ? 1.055*Math.pow(c,1/2.4)-0.055 : 12.92*c; }
  function srgbToLinear(c: number) { return c >= 0.04045 ? Math.pow((c+0.055)/1.055,2.4) : c/12.92; }

  function oklchToRgb(l: number, c: number, h: number): [number,number,number] {
    const hr = h * Math.PI/180, a = c*Math.cos(hr), b = c*Math.sin(hr);
    const l_ = l+0.3963377774*a+0.2158037573*b;
    const m_ = l-0.1055613458*a-0.0638541728*b;
    const s_ = l-0.0894841775*a-1.291485548*b;
    const l3=l_**3, m3=m_**3, s3=s_**3;
    let r = 4.0767416621*l3-3.3077115913*m3+0.2309699292*s3;
    let g = -1.2684380046*l3+2.6097574011*m3-0.3413193965*s3;
    let bl = -0.0041960863*l3-0.7034186147*m3+1.707614701*s3;
    return [Math.round(clamp(linearToSrgb(r),0,1)*255), Math.round(clamp(linearToSrgb(g),0,1)*255), Math.round(clamp(linearToSrgb(bl),0,1)*255)];
  }

  function rgbToOklch(r: number, g: number, b: number) {
    r=srgbToLinear(r/255); g=srgbToLinear(g/255); b=srgbToLinear(b/255);
    const l_=Math.cbrt(0.4122214708*r+0.5363325363*g+0.0514459929*b);
    const m_=Math.cbrt(0.2119034982*r+0.6806995451*g+0.1073969566*b);
    const s_=Math.cbrt(0.0883024619*r+0.2817188376*g+0.6299787005*b);
    const L=0.2104542553*l_+0.793617785*m_-0.004072*s_;
    const a=1.9779984951*l_-2.428592205*m_+0.4505937099*s_;
    const B=0.0259040371*l_+0.7827717662*m_-0.808675766*s_;
    let H=Math.atan2(B,a)*180/Math.PI; if(H<0)H+=360;
    return { l:L, c:Math.sqrt(a*a+B*B), h:H };
  }

  function onSpectrumMove(e: MouseEvent) {
    if (!spectrumCanvas) return;
    const r = spectrumCanvas.getBoundingClientRect();
    const x = clamp(e.clientX-r.left, 0, 220);
    const y = clamp(e.clientY-r.top, 0, 220);
    oklch = { ...oklch, h: (x/220)*360, c: MAX_CHROMA*(1-y/220) };
  }

  function onLumMove(e: MouseEvent) {
    if (!lumCanvas) return;
    const r = lumCanvas.getBoundingClientRect();
    const y = clamp(e.clientY-r.top, 0, 220);
    oklch = { ...oklch, l: 1-y/220 };
  }

  function onHexInput(e: Event) {
    const val = (e.target as HTMLInputElement).value.trim();
    const hex = val.startsWith('#') ? val.slice(1) : val;
    if (hex.length === 6 && /^[0-9a-fA-F]+$/.test(hex)) {
      const r=parseInt(hex.slice(0,2),16), g=parseInt(hex.slice(2,4),16), b=parseInt(hex.slice(4,6),16);
      oklch = rgbToOklch(r, g, b);
    }
  }

  function onRgbInput(field: 'r'|'g'|'b', val: string) {
    const v = clamp(parseInt(val)||0, 0, 255);
    const cur = rgb;
    oklch = rgbToOklch(field==='r'?v:cur.r, field==='g'?v:cur.g, field==='b'?v:cur.b);
  }

  function addCustom() {
    const s = `rgb(${rgb.r},${rgb.g},${rgb.b})`;
    customColors = [s, ...customColors.slice(0, 15)];
  }

  function pickSwatch(s: string) {
    if (!s) return;
    if (s.startsWith('#')) {
      const h=s.slice(1);
      oklch = rgbToOklch(parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16));
      onColorSelect?.({ r: parseInt(h.slice(0,2),16), g: parseInt(h.slice(2,4),16), b: parseInt(h.slice(4,6),16) });
    } else {
      const m = s.match(/\d+/g);
      if (m) {
        const [r,g,b]=[+m[0],+m[1],+m[2]];
        oklch = rgbToOklch(r,g,b);
        onColorSelect?.({r,g,b});
      }
    }
  }

  function confirm() { onColorSelect?.(rgb); onClose?.(); }

  // Basic palette — more muted/practical
  const PALETTE = [
    '#ffffff','#d4d4d4','#a0a0a0','#707070','#404040','#202020','#000000','#ff4444',
    '#ff8844','#ffcc00','#88cc00','#00cc88','#0088ff','#8844ff','#ff44cc','#884444',
    '#cc3300','#ff6600','#ffaa00','#99cc33','#33cc99','#3399ff','#6633cc','#cc3399',
    '#550000','#884400','#886600','#446600','#004433','#003366','#220044','#440022',
  ];
</script>

<div class="backdrop" onclick={(e) => e.target === e.currentTarget && onClose?.()}>
  <div class="picker">

    <div class="picker-header">
      <span>Edit Color</span>
    </div>

    <div class="picker-body">
      <!-- Left: spectrum + lum -->
      <div class="canvas-area">
        <div class="spectrum-wrap"
          onmousedown={(e) => { isDraggingSpectrum = true; onSpectrumMove(e); }}
          role="slider" tabindex="0" aria-label="Color hue/chroma"
          aria-valuenow={Math.round(oklch.h)}>
          <canvas bind:this={spectrumCanvas} width={220} height={220} class="spectrum-canvas"></canvas>
          <div class="cursor" style="left:{(oklch.h/360)*220}px;top:{(1-oklch.c/MAX_CHROMA)*220}px;"></div>
        </div>
        <div class="lum-wrap"
          onmousedown={(e) => { isDraggingLum = true; onLumMove(e); }}
          role="slider" tabindex="0" aria-label="Lightness"
          aria-valuenow={Math.round(oklch.l*100)}>
          <canvas bind:this={lumCanvas} width={20} height={220} class="lum-canvas"></canvas>
          <div class="lum-cursor" style="top:{(1-oklch.l)*220}px;"></div>
        </div>
      </div>

      <!-- Right: preview + inputs -->
      <div class="inputs-area">
        <!-- Preview -->
        <div class="preview" style="background:rgb({rgb.r},{rgb.g},{rgb.b});"></div>

        <!-- Hex -->
        <div class="field-row">
          <label class="field-label">HEX</label>
          <input class="field-input field-input-hex" value={hexInput}
            oninput={onHexInput} spellcheck="false" maxlength="7" />
        </div>

        <!-- RGB -->
        <div class="field-row">
          <label class="field-label">R</label>
          <input class="field-input" type="number" min="0" max="255" value={rgb.r}
            oninput={(e) => onRgbInput('r', (e.target as HTMLInputElement).value)} />
        </div>
        <div class="field-row">
          <label class="field-label">G</label>
          <input class="field-input" type="number" min="0" max="255" value={rgb.g}
            oninput={(e) => onRgbInput('g', (e.target as HTMLInputElement).value)} />
        </div>
        <div class="field-row">
          <label class="field-label">B</label>
          <input class="field-input" type="number" min="0" max="255" value={rgb.b}
            oninput={(e) => onRgbInput('b', (e.target as HTMLInputElement).value)} />
        </div>

        <!-- OKLCH compact -->
        <div class="field-row">
          <label class="field-label">H</label>
          <input class="field-input" type="number" min="0" max="360" value={Math.round(oklch.h)}
            oninput={(e) => oklch = {...oklch, h: clamp(+(e.target as HTMLInputElement).value,0,360)}} />
        </div>
        <div class="field-row">
          <label class="field-label">L</label>
          <input class="field-input" type="number" min="0" max="100" value={Math.round(oklch.l*100)}
            oninput={(e) => oklch = {...oklch, l: clamp(+(e.target as HTMLInputElement).value,0,100)/100}} />
        </div>
      </div>
    </div>

    <!-- Palette swatches -->
    <div class="swatch-section">
      <div class="swatch-label">Palette</div>
      <div class="swatches">
        {#each PALETTE as s}
          <button class="sw" style="background:{s};" onclick={() => pickSwatch(s)} title={s}></button>
        {/each}
      </div>
    </div>

    <!-- Custom colors -->
    <div class="swatch-section">
      <div class="swatch-label">Saved</div>
      <div class="swatches">
        {#each customColors as s, i}
          <button class="sw" class:empty={!s} style={s ? `background:${s};` : ''}
            onclick={() => s && pickSwatch(s)} title={s || 'empty'}></button>
        {/each}
        <button class="sw-add" onclick={addCustom} title="Save current color">+</button>
      </div>
    </div>

    <!-- Footer -->
    <div class="picker-footer">
      <button class="pbtn pbtn-accent" onclick={confirm}>Select</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 10002;
  }
  .picker {
    background: var(--panel); border: 1px solid var(--border2);
    border-radius: 10px; overflow: hidden; width: 420px;
    box-shadow: 0 32px 80px rgba(0,0,0,0.7);
    display: flex; flex-direction: column;
  }
  .picker-header {
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    font-size: 13px; font-weight: 600; color: var(--text);
    background: var(--surface);
  }
  .picker-body {
    display: flex; gap: 16px; padding: 16px;
  }

  /* Canvases */
  .canvas-area { display: flex; gap: 8px; flex-shrink: 0; }
  .spectrum-wrap {
    position: relative; width: 220px; height: 220px;
    border-radius: 6px; overflow: hidden; cursor: crosshair;
    border: 1px solid var(--border2);
  }
  .spectrum-canvas { display: block; width: 220px; height: 220px; }
  .cursor {
    position: absolute; width: 12px; height: 12px;
    border-radius: 50%; border: 2px solid #fff;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.5);
    transform: translate(-6px, -6px);
    pointer-events: none;
  }
  .lum-wrap {
    position: relative; width: 20px; height: 220px;
    border-radius: 4px; overflow: visible; cursor: ns-resize;
  }
  .lum-canvas {
    display: block; width: 20px; height: 220px;
    border-radius: 4px; border: 1px solid var(--border2);
  }
  .lum-cursor {
    position: absolute; left: -4px; right: -4px; height: 3px;
    background: #fff; border-radius: 2px;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.4);
    transform: translateY(-1px);
    pointer-events: none;
  }

  /* Inputs */
  .inputs-area { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .preview {
    height: 40px; border-radius: 6px; border: 1px solid var(--border2);
    margin-bottom: 4px; flex-shrink: 0;
  }
  .field-row { display: flex; align-items: center; gap: 6px; }
  .field-label { font-size: 10px; font-weight: 700; color: var(--text-dim); width: 16px; flex-shrink: 0; }
  .field-input {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 4px; padding: 4px 6px; font-size: 12px; color: var(--text);
    font-family: monospace; outline: none; min-width: 0;
    transition: border-color 0.1s;
  }
  .field-input:focus { border-color: var(--accent); }
  .field-input-hex { text-transform: uppercase; }
  /* Remove number input arrows */
  .field-input::-webkit-inner-spin-button, .field-input::-webkit-outer-spin-button { -webkit-appearance: none; }
  .field-input[type=number] { -moz-appearance: textfield; }

  /* Swatches */
  .swatch-section { padding: 0 16px 12px; }
  .swatch-label { font-size: 10px; font-weight: 700; color: var(--text-dim); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 6px; }
  .swatches { display: flex; flex-wrap: wrap; gap: 4px; }
  .sw {
    width: 20px; height: 20px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.08); cursor: pointer;
    transition: transform 0.1s, box-shadow 0.1s;
    flex-shrink: 0;
  }
  .sw:hover { transform: scale(1.2); box-shadow: 0 2px 8px rgba(0,0,0,0.4); }
  .sw.empty { background: var(--surface); border: 1px dashed var(--border2); }
  .sw-add {
    width: 20px; height: 20px; border-radius: 4px;
    background: var(--surface); border: 1px dashed var(--border2);
    color: var(--text-dim); font-size: 14px; cursor: pointer; line-height: 1;
    display: flex; align-items: center; justify-content: center;
    transition: border-color 0.1s, color 0.1s;
  }
  .sw-add:hover { border-color: var(--accent); color: var(--text); }

  /* Footer */
  .picker-footer {
    padding: 12px 16px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end;
  }
  .pbtn {
    padding: 8px 20px; border-radius: 5px; font-size: 13px; cursor: pointer;
    border: 1px solid var(--border2); background: var(--surface); color: var(--text);
    transition: all 0.1s;
  }
  .pbtn-accent { background: var(--accent-bg); border-color: var(--accent); font-weight: 600; }
  .pbtn-accent:hover { border-color: var(--accent2); }
</style>
