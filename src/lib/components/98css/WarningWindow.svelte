<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    title?: string;
    message?: string;
    children?: Snippet;
    onconfirm?: () => void;
    oncancel?: () => void;
    confirmText?: string;
    cancelText?: string;
    showCancel?: boolean;
  }

  let { title = 'warning', message, children, onconfirm, oncancel, confirmText = 'ok', cancelText = 'cancel', showCancel = true }: Props = $props();
</script>

<div class="backdrop">
  <div class="dialog">
    <div class="dialog-head">{title}</div>
    <div class="dialog-body">
      {#if message}<p class="msg">{message}</p>{/if}
      {#if children}{@render children()}{/if}
    </div>
    <div class="dialog-foot">
      {#if showCancel}
        <button class="dbtn" onclick={() => oncancel?.()}>{cancelText}</button>
      {/if}
      <button class="dbtn dbtn-accent" onclick={() => onconfirm?.()}>{confirmText}</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 99999;
  }
  .dialog {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 360px; overflow: hidden;
  }
  .dialog-head {
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim);
  }
  .dialog-body { padding: 16px 16px 12px; }
  .msg { font-size: 12px; color: var(--text-dim); line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
  .dialog-foot {
    padding: 10px 16px; border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 16px;
  }
  .dbtn {
    background: none; border: none; border-bottom: 1px solid var(--border2);
    color: var(--text-dim); font-family: 'DM Mono', monospace; font-size: 12px;
    padding: 3px 0; cursor: pointer; transition: color 0.15s, border-color 0.15s; min-width: 40px;
  }
  .dbtn:hover { color: var(--text); border-bottom-color: var(--text-dim); }
  .dbtn-accent { color: var(--accent); border-bottom-color: var(--accent); }
  .dbtn-accent:hover { opacity: 0.7; }
</style>
