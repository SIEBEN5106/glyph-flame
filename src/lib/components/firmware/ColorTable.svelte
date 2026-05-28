<script lang="ts">
  export interface ColorEntry {
    semantic: string;
    color: number;
    themeId?: number;
    register?: number;
    instruction?: string;
    address?: string;
    rawBytes?: number[];
    movwInstruction?: string;
    movwAddress?: string;
    strhInstruction?: string;
    strhAddress?: string;
    isPatched?: boolean;
  }

  interface Props {
    entries: ColorEntry[];
    onDoubleClick?: (entry: ColorEntry) => void;
    height?: string;
    hideProperty?: boolean;
    hideSource?: boolean;
  }

  let { entries, onDoubleClick, height = '100%', hideProperty = false, hideSource = false }: Props = $props();

  let selectedIdx = $state<number | null>(null);

  function rgb565ToCss(color: number): string {
    const r = Math.round(((color >> 11) & 0x1f) * 255 / 31);
    const g = Math.round(((color >> 5) & 0x3f) * 255 / 63);
    const b = Math.round((color & 0x1f) * 255 / 31);
    return `rgb(${r},${g},${b})`;
  }
</script>

<div class="ct" style="height:{height}">
  <div class="ct-head">
    {#if !hideProperty}<span class="ch flex3">property</span>{/if}
    <span class="ch flex1">theme</span>
    <span class="ch flex1">reg</span>
    {#if !hideSource}<span class="ch flex1">status</span>{/if}
    <span class="ch flex1">value</span>
    <span class="ch swatch-col">color</span>
  </div>
  <div class="ct-body">
    {#each entries as entry, i}
      {@const css = rgb565ToCss(entry.color)}
      {@const hex = '0x' + entry.color.toString(16).padStart(4,'0').toUpperCase()}
      <div class="ct-row" class:selected={selectedIdx === i}
        onclick={() => (selectedIdx = i)}
        ondblclick={() => { selectedIdx = i; onDoubleClick?.(entry); }}
        role="row" tabindex="0"
        onkeydown={(e) => e.key === 'Enter' && onDoubleClick?.(entry)}
        aria-selected={selectedIdx === i}>
        {#if !hideProperty}
          <span class="cd flex3" title={entry.semantic}>{entry.semantic}</span>
        {/if}
        <span class="cd flex1">{entry.themeId !== undefined ? `t${entry.themeId}` : '—'}</span>
        <span class="cd flex1 mono">{entry.register !== undefined ? `r${entry.register}` : '—'}</span>
        {#if !hideSource}
          <span class="cd flex1" class:patched={entry.isPatched}>{entry.isPatched ? 'patched' : 'default'}</span>
        {/if}
        <span class="cd flex1 mono">{hex}</span>
        <span class="cd swatch-col"><span class="sw" style="background:{css};"></span></span>
      </div>
    {/each}
  </div>
  {#if entries.length > 0}
    <div class="ct-hint">→ double-click to view details</div>
  {/if}
</div>

<style>
  .ct { display: flex; flex-direction: column; overflow: hidden; width: 100%; }
  .ct-head {
    display: flex; align-items: center; padding: 6px 16px;
    border-bottom: 1px solid var(--border2); flex-shrink: 0;
  }
  .ch { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ct-body { flex: 1; overflow-y: auto; min-height: 0; }
  .ct-row {
    display: flex; align-items: center; padding: 7px 16px;
    border-bottom: 1px solid var(--border); cursor: pointer; outline: none;
    transition: background 0.1s;
  }
  .ct-row:hover { background: var(--surface2); }
  .ct-row.selected { background: var(--accent-bg); }
  .ct-row.selected .cd { color: var(--text); }
  .cd { font-size: 11px; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cd.patched { color: var(--accent); }
  .mono { font-family: 'DM Mono', monospace; font-size: 10px; }
  .flex1 { flex: 1; min-width: 0; padding-right: 8px; }
  .flex3 { flex: 3; min-width: 0; padding-right: 8px; }
  .swatch-col { width: 40px; flex-shrink: 0; display: flex; justify-content: center; }
  .sw { width: 24px; height: 12px; border-radius: 2px; border: 1px solid rgba(255,255,255,0.08); display: inline-block; }
  .ct-hint { padding: 5px 16px; font-size: 10px; color: var(--text-faint); border-top: 1px solid var(--border); flex-shrink: 0; }
</style>
