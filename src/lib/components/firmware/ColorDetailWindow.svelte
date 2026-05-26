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
  const isFlac = $derived(detail.semantic.includes('Codec Info') || detail.semantic.includes('FLAC'));

  const isEditable = $derived(
    detail.semantic.includes('Progress Bar') ||
    detail.semantic.includes('Marquee Overlay') ||
    (detail.semantic.includes('Codec Info') && detail.isFlacPatched)
  );
  const showUnlock = $derived(detail.semantic.includes('Codec Info') && !detail.isFlacPatched);

  interface InstrRow { key: string; value: string; }
  const rows = $derived.by<InstrRow[]>(() => {
    const r: InstrRow[] = [];
    const keyLabel = isFlac ? 'FLAC' : (detail.register !== undefined ? `R${detail.register}` : '—');
    r.push({ key: keyLabel, value: colorHex });
    r.push({
      key: detail.movwAddress ?? '(preload)',
      value: detail.movwInstruction ?? '(preload)',
    });
    if (detail.strhAddress || detail.strhInstruction) {
      r.push({
        key: detail.strhAddress ?? '—',
        value: detail.strhInstruction ?? '—',
      });
    }
    return r;
  });
</script>

<div class="backdrop" onclick={(e) => e.target === e.currentTarget && onclose()}>
  <div class="modal">

    <!-- Color preview bar -->
    <div class="color-bar" style="background:{colorCss};"></div>

    <div class="modal-body">
      <!-- Info section -->
      <div class="info-grid">
        <div class="info-row">
          <span class="info-label">Property</span>
          <span class="info-value">{detail.semantic}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Hex Value</span>
          <span class="info-value mono">{colorHex}</span>
        </div>
        {#if detail.themeId !== undefined}
          <div class="info-row">
            <span class="info-label">Theme</span>
            <span class="info-value">Theme {detail.themeId}</span>
          </div>
        {/if}
        {#if detail.register !== undefined}
          <div class="info-row">
            <span class="info-label">Register</span>
            <span class="info-value mono">R{detail.register}</span>
          </div>
        {/if}
        <div class="info-row">
          <span class="info-label">Status</span>
          <span class="info-value" class:patched={detail.isPatched}>
            {detail.isPatched ? 'Patched' : 'Default'}
          </span>
        </div>
      </div>

      <!-- Instructions table -->
      <div class="instr-section">
        <div class="instr-label">Instructions</div>
        <div class="instr-table">
          {#each rows as row}
            <div class="instr-row">
              <span class="instr-key mono">{row.key}</span>
              <span class="instr-val mono">{row.value}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="modal-footer">
    {#if showUnlock && onunlock}
      <button class="fbtn fbtn-warn" onclick={onunlock}>Unlock FLAC Editing</button>
    {:else if isEditable && onedit}
      <button class="fbtn fbtn-accent" onclick={() => onedit?.()}>Edit Color</button>
    {/if}
      <button class="fbtn" onclick={onclose}>Done</button>
    </div>

  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 10000;
  }
  .modal {
    background: var(--panel); border: 1px solid var(--border2);
    border-radius: 8px; width: 420px; overflow: hidden;
    box-shadow: 0 24px 64px rgba(0,0,0,0.6);
  }
  .color-bar { height: 6px; width: 100%; }

  .modal-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }

  .info-grid { display: flex; flex-direction: column; gap: 0; }
  .info-row {
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 6px 0; border-bottom: 1px solid var(--border); gap: 16px;
  }
  .info-row:last-child { border-bottom: none; }
  .info-label { font-size: 11px; color: var(--text-dim); flex-shrink: 0; }
  .info-value { font-size: 12px; color: var(--text); text-align: right; word-break: break-all; }
  .info-value.patched { color: var(--accent2); }

  .instr-section { display: flex; flex-direction: column; gap: 6px; }
  .instr-label { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; color: var(--text-dim); text-transform: uppercase; }
  .instr-table {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 5px; overflow: hidden;
  }
  .instr-row {
    display: flex; align-items: center; gap: 12px; padding: 6px 10px;
    border-bottom: 1px solid var(--border);
  }
  .instr-row:last-child { border-bottom: none; }
  .instr-key { font-size: 11px; color: var(--text-dim); width: 100px; flex-shrink: 0; }
  .instr-val { font-size: 11px; color: var(--text); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: 'SF Mono', 'Fira Code', monospace; }

  .modal-footer {
    display: flex; align-items: center; justify-content: flex-end; gap: 8px;
    padding: 12px 16px; border-top: 1px solid var(--border);
  }
  .fbtn {
    padding: 7px 16px; border-radius: 5px; font-size: 12px; cursor: pointer;
    border: 1px solid var(--border2); background: var(--surface); color: var(--text);
    transition: all 0.1s; min-width: 64px;
  }
  .fbtn:hover { background: var(--surface2); border-color: var(--border2); }
  .fbtn-accent { background: var(--accent-bg); border-color: var(--accent); color: var(--text); font-weight: 500; }
  .fbtn-accent:hover { border-color: var(--accent2); }
  .fbtn-warn { background: #2a1a08; border-color: #7a4010; color: #d08040; }
  .fbtn-warn:hover { border-color: #c06020; color: #e09050; }
</style>
