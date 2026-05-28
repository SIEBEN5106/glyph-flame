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
    try { const s = localStorage.getItem(storageKey); if (s) { const p = JSON.parse(s); if (Array.isArray(p)) customColors = [...p.slice(0,16), ...Array(16).fill('')].slice(0,16); } } catch {}
  });

  $effect(() => { try { localStorage.setItem(storageKey, JSON.stringify(customColors)); } catch {} });

  const rgb = $derived.by(() => {
    const [r,g,b] = oklchToRgb(oklch.l, oklch.c, oklch.h);
    return { r, g, b };
  });

  $effect(() => { hexInput = '#' + rgb.r.toString(16).padStart(2,'0') + rgb.g.toString(16).padStart(2,'0') + rgb.b.toString(16).padStart(2,'0'); });

  $effect(() => {
    if (!spectrumCanvas) return;
    oklch.l;
    const ctx = spectrumCanvas.getContext('2d')!;
    const w = 200, h = 200;
    const d = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
      const c = MAX_CHROMA * (1 - y/h);
      for (let x = 0; x < w; x++) {
        const hh = (x/w) * 360;
        const [r,g,b] = oklchToRgb(oklch.l, c, hh);
        const i = (y*w+x)*4;
        d.data[i]=r; d.data[i+1]=g; d.data[i+2]=b; d.data[i+3]=255;
      }
    }
    ctx.putImageData(d, 0, 0);
  });

  $effect(() => {
    if (!lumCanvas) return;
    oklch.h; oklch.c;
    const ctx = lumCanvas.getContext('2d')!;
    const d = ctx.createImageData(16, 200);
    for (let y = 0; y < 200; y++) {
      const l = 1 - y/200;
      const [r,g,b] = oklchToRgb(l, oklch.c, oklch.h);
      for (let x = 0; x < 16; x++) {
        const i = (y*16+x)*4;
        d.data[i]=r; d.data[i+1]=g; d.data[i+2]=b; d.data[i+3]=255;
      }
    }
    ctx.putImageData(d, 0, 0);
  });

  $effect(() => {
    const up = () => { isDraggingSpectrum = false; isDraggingLum = false; };
    const mv = (e: MouseEvent) => { if (isDraggingSpectrum) onSMove(e); if (isDraggingLum) onLMove(e); };
    window.addEventListener('mouseup', up); window.addEventListener('mousemove', mv);
    return () => { window.removeEventListener('mouseup', up); window.removeEventListener('mousemove', mv); };
  });

  function clamp(x: number, lo: number, hi: number) { return Math.min(Math.max(x, lo), hi); }
  function linToSrgb(c: number) { return c >= 0.0031308 ? 1.055*Math.pow(c,1/2.4)-0.055 : 12.92*c; }
  function srgbToLin(c: number) { return c >= 0.04045 ? Math.pow((c+0.055)/1.055,2.4) : c/12.92; }

  function oklchToRgb(l: number, c: number, h: number): [number,number,number] {
    const hr = h*Math.PI/180, a = c*Math.cos(hr), b = c*Math.sin(hr);
    const l_ = l+0.3963377774*a+0.2158037573*b;
    const m_ = l-0.1055613458*a-0.0638541728*b;
    const s_ = l-0.0894841775*a-1.291485548*b;
    const l3=l_**3, m3=m_**3, s3=s_**3;
    let r=4.0767416621*l3-3.3077115913*m3+0.2309699292*s3;
    let g=-1.2684380046*l3+2.6097574011*m3-0.3413193965*s3;
    let bv=-0.0041960863*l3-0.7034186147*m3+1.707614701*s3;
    return [Math.round(clamp(linToSrgb(r),0,1)*255),Math.round(clamp(linToSrgb(g),0,1)*255),Math.round(clamp(linToSrgb(bv),0,1)*255)];
  }

  function rgbToOklch(r: number, g: number, b: number) {
    r=srgbToLin(r/255); g=srgbToLin(g/255); b=srgbToLin(b/255);
    const l_=Math.cbrt(0.4122214708*r+0.5363325363*g+0.0514459929*b);
    const m_=Math.cbrt(0.2119034982*r+0.6806995451*g+0.1073969566*b);
    const s_=Math.cbrt(0.0883024619*r+0.2817188376*g+0.6299787005*b);
    const L=0.2104542553*l_+0.793617785*m_-0.004072*s_;
    const a=1.9779984951*l_-2.428592205*m_+0.7827717662*s_-0.808675766*s_;
    const B=0.0259040371*l_+0.7827717662*m_-0.808675766*s_;
    let H=Math.atan2(B,a)*180/Math.PI; if(H<0)H+=360;
    return { l:L, c:Math.sqrt(a*a+B*B), h:H };
  }

  function onSMove(e: MouseEvent) {
    if (!spectrumCanvas) return;
    const r = spectrumCanvas.getBoundingClientRect();
    const x = clamp(e.clientX-r.left,0,200), y = clamp(e.clientY-r.top,0,200);
    oklch = { ...oklch, h: (x/200)*360, c: MAX_CHROMA*(1-y/200) };
  }
  function onLMove(e: MouseEvent) {
    if (!lumCanvas) return;
    const r = lumCanvas.getBoundingClientRect();
    oklch = { ...oklch, l: 1-clamp(e.clientY-r.top,0,200)/200 };
  }
  function onHexInput(e: Event) {
    const val = (e.target as HTMLInputElement).value.trim().replace('#','');
    if (val.length === 6 && /^[0-9a-fA-F]+$/.test(val)) {
      oklch = rgbToOklch(parseInt(val.slice(0,2),16),parseInt(val.slice(2,4),16),parseInt(val.slice(4,6),16));
    }
  }
  function onRgbIn(field: 'r'|'g'|'b', val: string) {
    const v = clamp(parseInt(val)||0,0,255);
    const c = rgb;
    oklch = rgbToOklch(field==='r'?v:c.r, field==='g'?v:c.g, field==='b'?v:c.b);
  }
  function addCustom() { customColors = [`rgb(${rgb.r},${rgb.g},${rgb.b})`, ...customColors.slice(0,15)]; }
  function pickSwatch(s: string) {
    if (!s) return;
    if (s.startsWith('#')) {
      const h=s.slice(1); oklch=rgbToOklch(parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16));
    } else { const m=s.match(/\d+/g); if(m){const[r,g,b]=[+m[0],+m[1],+m[2]]; oklch=rgbToOklch(r,g,b); onColorSelect?.({r,g,b}); } }
  }
  function confirm() { onColorSelect?.(rgb); onClose?.(); }

  const PALETTE = [
    '#ffffff','#d4d4d4','#a0a0a0','#707070','#404040','#202020','#000000','#ff4444',
    '#ff8844','#ffcc00','#88cc00','#00cc88','#0088ff','#8844ff','#ff44cc','#884444',
    '#cc3300','#ff6600','#ffaa00','#99cc33','#33cc99','#3399ff','#6633cc','#cc3399',
    '#550000','#884400','#886600','#446600','#004433','#003366','#220044','#440022',
  ];
</script>

<div class="backdrop" onclick={(e) => e.target === e.currentTarget && onClose?.()}>
  <div class="picker">
    <div class="picker-head">color picker</div>
    <div class="picker-body">
      <div class="canvas-area">
        <div class="spectrum-wrap"
          onmousedown={(e) => { isDraggingSpectrum=true; onSMove(e); }}
          role="slider" tabindex="0" aria-label="hue/chroma" aria-valuenow={Math.round(oklch.h)}>
          <canvas bind:this={spectrumCanvas} width={200} height={200} class="sp-canvas"></canvas>
          <div class="sp-cursor" style="left:{(oklch.h/360)*200}px;top:{(1-oklch.c/MAX_CHROMA)*200}px;"></div>
        </div>
        <div class="lum-wrap"
          onmousedown={(e) => { isDraggingLum=true; onLMove(e); }}
          role="slider" tabindex="0" aria-label="lightness" aria-valuenow={Math.round(oklch.l*100)}>
          <canvas bind:this={lumCanvas} width={16} height={200} class="lum-canvas"></canvas>
          <div class="lum-cursor" style="top:{(1-oklch.l)*200}px;"></div>
        </div>
      </div>
      <div class="inputs-area">
        <div class="preview" style="background:rgb({rgb.r},{rgb.g},{rgb.b});"></div>
        <div class="field"><span class="fl">hex</span>
          <input class="fi fi-hex" value={hexInput} oninput={onHexInput} spellcheck="false" maxlength="7" /></div>
        <div class="field"><span class="fl">r</span>
          <input class="fi" type="number" min="0" max="255" value={rgb.r} oninput={(e)=>onRgbIn('r',(e.target as HTMLInputElement).value)} /></div>
        <div class="field"><span class="fl">g</span>
          <input class="fi" type="number" min="0" max="255" value={rgb.g} oninput={(e)=>onRgbIn('g',(e.target as HTMLInputElement).value)} /></div>
        <div class="field"><span class="fl">b</span>
          <input class="fi" type="number" min="0" max="255" value={rgb.b} oninput={(e)=>onRgbIn('b',(e.target as HTMLInputElement).value)} /></div>
        <div class="field"><span class="fl">h</span>
          <input class="fi" type="number" min="0" max="360" value={Math.round(oklch.h)} oninput={(e)=>oklch={...oklch,h:clamp(+(e.target as HTMLInputElement).value,0,360)}} /></div>
        <div class="field"><span class="fl">l</span>
          <input class="fi" type="number" min="0" max="100" value={Math.round(oklch.l*100)} oninput={(e)=>oklch={...oklch,l:clamp(+(e.target as HTMLInputElement).value,0,100)/100}} /></div>
      </div>
    </div>
    <div class="swatch-sec">
      <div class="sw-label">palette</div>
      <div class="swatches">
        {#each PALETTE as s}<button class="sw" style="background:{s};" onclick={() => pickSwatch(s)} title={s}></button>{/each}
      </div>
    </div>
    <div class="swatch-sec">
      <div class="sw-label">saved <button class="sw-add-btn" onclick={addCustom}>+ save current</button></div>
      <div class="swatches">
        {#each customColors as s}<button class="sw" class:sw-empty={!s} style={s?`background:${s}`:''} onclick={()=>s&&pickSwatch(s)}></button>{/each}
      </div>
    </div>
    <div class="picker-foot">
      <button class="dbtn dbtn-accent" onclick={confirm}>select</button>
    </div>
  </div>
</div>

<style>
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 10002; }
  .picker { background: var(--bg); border: 1px solid var(--border2); border-radius: 5px; width: 400px; overflow: hidden; display: flex; flex-direction: column; }
  .picker-head { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); }
  .picker-body { display: flex; gap: 14px; padding: 14px 16px; }
  .canvas-area { display: flex; gap: 8px; flex-shrink: 0; }
  .spectrum-wrap { position: relative; width: 200px; height: 200px; cursor: crosshair; border: 1px solid var(--border); border-radius: 3px; overflow: hidden; }
  .sp-canvas { display: block; width: 200px; height: 200px; }
  .sp-cursor { position: absolute; width: 10px; height: 10px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.4); transform: translate(-5px,-5px); pointer-events: none; }
  .lum-wrap { position: relative; width: 16px; height: 200px; cursor: ns-resize; }
  .lum-canvas { display: block; width: 16px; height: 200px; border-radius: 3px; border: 1px solid var(--border); }
  .lum-cursor { position: absolute; left: -3px; right: -3px; height: 2px; background: #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.4); transform: translateY(-1px); pointer-events: none; }
  .inputs-area { flex: 1; display: flex; flex-direction: column; gap: 5px; }
  .preview { height: 36px; border-radius: 3px; border: 1px solid var(--border); margin-bottom: 4px; flex-shrink: 0; }
  .field { display: flex; align-items: center; gap: 6px; border-bottom: 1px solid var(--border); padding: 3px 0; }
  .fl { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-faint); width: 14px; flex-shrink: 0; }
  .fi { flex: 1; background: transparent; border: none; padding: 2px 0; font-size: 11px; color: var(--text-dim); font-family: 'DM Mono', monospace; outline: none; min-width: 0; }
  .fi:focus { color: var(--text); }
  .fi-hex { text-transform: uppercase; }
  .fi::-webkit-inner-spin-button, .fi::-webkit-outer-spin-button { -webkit-appearance: none; }
  .fi[type=number] { -moz-appearance: textfield; }
  .swatch-sec { padding: 0 16px 10px; }
  .sw-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-faint); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
  .sw-add-btn { background: none; border: none; font-family: 'DM Mono', monospace; font-size: 10px; color: var(--text-faint); cursor: pointer; padding: 0; transition: color 0.15s; }
  .sw-add-btn:hover { color: var(--accent); }
  .swatches { display: flex; flex-wrap: wrap; gap: 3px; }
  .sw { width: 18px; height: 18px; border-radius: 3px; border: 1px solid rgba(255,255,255,0.06); cursor: pointer; transition: transform 0.1s; flex-shrink: 0; }
  .sw:hover { transform: scale(1.2); }
  .sw-empty { background: var(--surface2) !important; border: 1px dashed var(--border2) !important; }
  .picker-foot { padding: 10px 16px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }
  .dbtn { background: none; border: none; border-bottom: 1px solid var(--border2); color: var(--text-dim); font-family: 'DM Mono', monospace; font-size: 12px; padding: 3px 0; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .dbtn:hover { color: var(--text); border-bottom-color: var(--text-dim); }
  .dbtn-accent { color: var(--accent); border-bottom-color: var(--accent); }
  .dbtn-accent:hover { opacity: 0.7; }
</style>
