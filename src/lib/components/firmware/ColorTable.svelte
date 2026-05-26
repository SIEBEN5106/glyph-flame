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
    title?: string;
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
    {#if !hideProperty}<span class="ch flex3">Property</span>{/if}
    <span class="ch flex1">Theme</span>
    <span class="ch flex1">Reg</span>
    {#if !hideSource}<span class="ch flex1">Status</span>{/if}
    <span class="ch flex1">Value</span>
    <span class="ch swatch-col">Color</span>
  </div>
  <div class="ct-body">
    {#each entries as entry, i}
      {@const css = rgb565ToCss(entry.color)}
      {@const hex = '0x' + entry.color.toString(16).padStart(4,'0').toUpperCase()}
      <div
        class="ct-row"
        class:selected={selectedIdx === i}
        onclick={() => (selectedIdx = i)}
        ondblclick={() => { selectedIdx = i; onDoubleClick?.(entry); }}
        role="row"
        tabindex="0"
        onkeydown={(e) => e.key === 'Enter' && onDoubleClick?.(entry)}
        aria-selected={selectedIdx === i}
      >
        {#if !hideProperty}
          <span class="cd flex3" title={entry.semantic}>{entry.semantic}</span>
        {/if}
        <span class="cd flex1">{entry.themeId !== undefined ? `T${entry.themeId}` : '—'}</span>
        <span class="cd flex1 mono">{entry.register !== undefined ? `R${entry.register}` : '—'}</span>
        {#if !hideSource}
          <span class="cd flex1" class:patched={entry.isPatched}>{entry.isPatched ? 'Patched' : 'Default'}</span>
        {/if}
        <span class="cd flex1 mono">{hex}</span>
        <span class="cd swatch-col">
          <span class="swatch" style="background:{css};"></span>
        </span>
      </div>
    {/each}
  </div>
  {#if entries.length > 0}
    <div class="ct-hint">Double-click a row to view details</div>
  {/if}
</div>

<style>
  .ct {
    display: flex; flex-direction: column;
    overflow: hidden; width: 100%;
  }
  .ct-head {
    display: flex; align-items: center;
    padding: 6px 12px;
    background: var(--surface);
    border-bottom: 2px solid var(--border2);
    flex-shrink: 0;
    gap: 8px;
  }
  .ch {
    font-size: 10px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-dim);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .ct-body {
    flex: 1; overflow-y: auto; min-height: 0;
  }
  .ct-row {
    display: flex; align-items: center;
    padding: 7px 12px; gap: 8px;
    border-bottom: 1px solid var(--border);
    cursor: pointer; transition: background 0.1s;
    outline: none;
  }
  .ct-row:hover { background: var(--surface); }
  .ct-row.selected { background: var(--accent-bg); border-left: 2px solid var(--accent); padding-left: 10px; }
  .cd {
    font-size: 12px; color: var(--text); overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }
  .cd.patched { color: var(--accent2); }
  .mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 11px; }
  .flex1 { flex: 1; min-width: 0; }
  .flex3 { flex: 3; min-width: 0; }
  .swatch-col { width: 48px; flex-shrink: 0; display: flex; justify-content: center; }
  .swatch {
    width: 28px; height: 14px; border-radius: 3px;
    border: 1px solid rgba(255,255,255,0.1);
    display: inline-block;
  }
  .ct-hint {
    padding: 6px 12px; font-size: 10px; color: var(--text-faint);
    border-top: 1px solid var(--border); flex-shrink: 0; text-align: right;
  }
</style>
