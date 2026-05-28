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

  let { title = 'loading', message, progress = 0, showProgress = true, children }: Props = $props();

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
    <div class="dialog-head">{title}</div>
    <div class="dialog-body">
      {#if showProgress}
        <div class="prog-row">
          <div class="prog-track"><div class="prog-fill" style="width:{displayedProgress}%"></div></div>
          <span class="prog-pct">{Math.round(displayedProgress)}%</span>
        </div>
      {/if}
      {#if message}<p class="msg">{message}</p>{/if}
      {#if children}{@render children()}{/if}
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 10001;
  }
  .dialog {
    background: var(--bg); border: 1px solid var(--border2);
    border-radius: 5px; width: 320px; overflow: hidden;
  }
  .dialog-head {
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim);
  }
  .dialog-body { padding: 16px; }
  .prog-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .prog-track { flex: 1; height: 1px; background: var(--border2); }
  .prog-fill { height: 100%; background: var(--accent); transition: width 0.1s; }
  .prog-pct { font-size: 10px; color: var(--text-faint); width: 28px; text-align: right; flex-shrink: 0; }
  .msg { font-size: 11px; color: var(--text-faint); }
</style>
