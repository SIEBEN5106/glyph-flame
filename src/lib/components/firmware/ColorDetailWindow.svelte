<script lang="ts">
  export interface ColorDetail {
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
    isFlacPatched?: boolean;
  }

  interface Props {
    detail: ColorDetail;
    onclose: () => void;
    onedit?: () => void;
    onunlock?: () => void;
  }

  let { detail, onclose, onedit, onunlock }: Props = $props();

  function rgb565ToCss(color: number): string {
    const r = Math.round(((color >> 11) & 0x1f) * 255 / 31);
    const g = Math.round(((color >> 5) & 0x3f) * 255 / 63);
    const b = Math.round((color & 0x1f) * 255 / 31);
    return `rgb(${r},${g},${b})`;
  }

  const colorCss = $derived(rgb565ToCss(detail.color));
  const colorHex = $derived('0x' + detail.color.toString(16).padStart(4, '0').toUpperCase());

  const isEditable = $derived(
    detail.semantic.includes('Progress Bar') ||
    detail.semantic.includes('Marquee Overlay') ||
    (detail.semantic.includes('Codec Info') && detail.isFlacPatched)
  );
  const showUnlock = $derived(detail.semantic.includes('Codec Info') && !detail.isFlacPatched);

  const infoRows = $derived([
    { key: 'property', val: detail.semantic },
    { key: 'hex', val: colorHex },
    ...(detail.themeId !== undefined ? [{ key: 'theme', val: `theme ${detail.themeId}` }] : []),
    ...(detail.register !== undefined ? [{ key: 'register', val: `r${detail.register}` }] : []),
    { key: 'status', val: detail.isPatched ? 'patched' : 'default' },
  ]);
</script>

<div class="backdrop" onclick={(e) => e.target === e.currentTarget && onclose()}>
  <div class="modal">
    <div class="color-bar" style="background:{colorCss};"></div>
    <div class="modal-head">color detail</div>
    <div class="modal-body">
      <div class="info-rows">
        {#each infoRows as row}
          <div class="info-row">
            <span class="info-key">{row.key}</span>
            <span class="info-val" class:mono={row.key === 'hex' || row.key === 'register'}>{row.val}</span>
          </div>
        {/each}
      </div>
      {#if detail.movwInstruction || detail.strhInstruction}
        <div class="instr-label">instructions</div>
        <div class="instr-rows">
          {#if detail.movwAddress}
            <div class="instr-row">
              <span class="instr-key">{detail.movwAddress}</span>
              <span class="instr-val">{detail.movwInstruction}</span>
            </div>
          {/if}
          {#if detail.strhAddress}
            <div class="instr-row">
              <span class="instr-key">{detail.strhAddress}</span>
              <span class="instr-val">{detail.strhInstruction}</span>
            </div>
          {/if}
        </div>
      {/if}
    </div>
    <div class="modal-foot">
      {#if showUnlock && onunlock}
        <button class="dbtn dbtn-warn" onclick={onunlock}>unlock flac editing</button>
      {:else if isEditable && onedit}
        <button class="dbtn dbtn-accent" onclick={() => onedit?.()}>edit color</button>
      {/if}
      <button class="dbtn" onclick={onclose}>done</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 10000;
  }
  .modal {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 400px; overflow: hidden;
  }
  .color-bar { height: 3px; width: 100%; }
  .modal-head {
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim);
  }
  .modal-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; }

  .info-rows { display: flex; flex-direction: column; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .info-row {
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 6px 0; border-bottom: 1px solid var(--border); gap: 12px;
  }
  .info-row:last-child { border-bottom: none; }
  .info-key { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-faint); flex-shrink: 0; }
  .info-val { font-size: 12px; color: var(--text-dim); text-align: right; word-break: break-all; }
  .info-val.mono { font-family: 'DM Mono', monospace; font-size: 11px; }

  .instr-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-faint); }
  .instr-rows { display: flex; flex-direction: column; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
  .instr-row { display: flex; gap: 12px; padding: 5px 0; border-bottom: 1px solid var(--border); }
  .instr-row:last-child { border-bottom: none; }
  .instr-key { font-size: 10px; color: var(--text-faint); width: 90px; flex-shrink: 0; font-family: 'DM Mono', monospace; }
  .instr-val { font-size: 10px; color: var(--text-dim); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: 'DM Mono', monospace; }

  .modal-foot {
    padding: 10px 16px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 16px;
  }
  .dbtn {
    background: none; border: none; border-bottom: 1px solid var(--border2);
    color: var(--text-dim); font-family: 'DM Mono', monospace; font-size: 12px;
    padding: 3px 0; cursor: pointer; transition: color 0.15s, border-color 0.15s;
  }
  .dbtn:hover { color: var(--text); border-bottom-color: var(--text-dim); }
  .dbtn-accent { color: var(--accent); border-bottom-color: var(--accent); }
  .dbtn-accent:hover { opacity: 0.7; }
  .dbtn-warn { color: #a07040; border-bottom-color: #a07040; }
  .dbtn-warn:hover { opacity: 0.7; }
</style>
