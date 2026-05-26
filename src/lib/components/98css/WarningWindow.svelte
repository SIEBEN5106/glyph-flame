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
    icon?: 'warning' | 'error' | 'info' | 'question';
    showCancel?: boolean;
  }

  let {
    title = 'Warning',
    message,
    children,
    onconfirm,
    oncancel,
    confirmText = 'OK',
    cancelText = 'Cancel',
    icon = 'warning',
    showCancel = true,
  }: Props = $props();

  const icons: Record<string, string> = {
    warning: '⚠',
    error: '✕',
    info: 'ℹ',
    question: '?',
  };
</script>

<div class="backdrop">
  <div class="dialog">
    <div class="dialog-header">
      <span class="icon-badge" class:warning={icon==='warning'} class:error={icon==='error'}>
        {icons[icon]}
      </span>
      {title}
    </div>
    <div class="dialog-body">
      {#if message}
        <p class="msg">{message}</p>
      {/if}
      {#if children}
        {@render children()}
      {/if}
    </div>
    <div class="dialog-footer">
      {#if showCancel}
        <button class="btn btn-ghost" onclick={() => oncancel?.()}>{cancelText}</button>
      {/if}
      <button class="btn btn-primary" onclick={() => onconfirm?.()}>{confirmText}</button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 99999;
  }
  .dialog {
    background: var(--panel);
    border: 1px solid var(--border2);
    border-radius: 8px;
    width: 380px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  }
  .dialog-header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 16px;
    font-size: 13px; font-weight: 600;
    color: var(--text);
    display: flex; align-items: center; gap: 10px;
  }
  .icon-badge {
    width: 24px; height: 24px;
    border-radius: 50%;
    background: var(--accent-bg);
    border: 1px solid var(--accent);
    color: var(--accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700;
    flex-shrink: 0;
  }
  .icon-badge.error {
    background: #2a1010; border-color: #c04030; color: #e06050;
  }
  .dialog-body {
    padding: 20px 16px;
  }
  .msg {
    color: var(--text-dim);
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .dialog-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    display: flex; justify-content: flex-end; gap: 8px;
  }
  .btn {
    padding: 7px 18px;
    border-radius: 5px;
    font-size: 12px; font-weight: 500;
    cursor: pointer;
    border: 1px solid;
    transition: all 0.1s;
    min-width: 72px;
  }
  .btn-primary {
    background: var(--accent-bg);
    border-color: var(--accent);
    color: var(--accent2);
  }
  .btn-primary:hover { background: var(--surface2); border-color: var(--accent2); color: #fff; }
  .btn-ghost {
    background: transparent;
    border-color: var(--border2);
    color: var(--text-dim);
  }
  .btn-ghost:hover { background: var(--surface); color: var(--text); }
</style>
