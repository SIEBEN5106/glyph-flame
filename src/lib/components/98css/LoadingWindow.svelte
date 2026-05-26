<script lang="ts">
  import type { Snippet } from 'svelte';
  import { debugMode, debugAnimationComplete } from '$lib/stores';

  interface Props {
    title?: string;
    message?: string;
    progress?: number;
    showProgress?: boolean;
    children?: Snippet;
  }

  let { title = 'Loading', message, progress = 0, showProgress = true, children }: Props = $props();

  let debug = $state(false);
  let displayedProgress = $state(0);
  let frameId: number | null = null;

  debugMode.subscribe((v) => (debug = v));

  $effect(() => {
    if (debug) {
      debugAnimationComplete.set(false);
      displayedProgress = 0;
      const start = Date.now();
      const tick = () => {
        displayedProgress = Math.min(((Date.now() - start) / 10000) * 100, 100);
        if (displayedProgress < 100) frameId = requestAnimationFrame(tick);
        else debugAnimationComplete.set(true);
      };
      frameId = requestAnimationFrame(tick);
      return () => { if (frameId) cancelAnimationFrame(frameId); };
    } else {
      displayedProgress = progress;
    }
  });
</script>

<div class="backdrop">
  <div class="dialog">
    <div class="dialog-header">
      <span class="dot"></span>
      {title}
    </div>
    <div class="dialog-body">
      {#if showProgress}
        <div class="progress-wrap">
          <div class="progress-track">
            <div class="progress-fill" style="width: {displayedProgress}%"></div>
          </div>
          <span class="progress-pct">{Math.round(displayedProgress)}%</span>
        </div>
      {/if}
      {#if message}
        <p class="msg">{message}</p>
      {/if}
      {#if children}
        {@render children()}
      {/if}
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 10001;
  }
  .dialog {
    background: var(--panel);
    border: 1px solid var(--border2);
    border-radius: 8px;
    width: 360px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6);
  }
  .dialog-header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 16px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    display: flex; align-items: center; gap: 8px;
  }
  .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--accent);
    animation: pulse 1s ease-in-out infinite;
    flex-shrink: 0;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  .dialog-body { padding: 20px 16px; }
  .progress-wrap {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 12px;
  }
  .progress-track {
    flex: 1; height: 4px;
    background: var(--surface2);
    border-radius: 2px; overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.1s;
  }
  .progress-pct {
    font-size: 11px; color: var(--text-dim);
    width: 30px; text-align: right; flex-shrink: 0;
  }
  .msg {
    font-size: 12px; color: var(--text-dim);
    text-align: center;
  }
</style>
