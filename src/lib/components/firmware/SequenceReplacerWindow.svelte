<script lang="ts">
  import SequenceReplacer from './SequenceReplacer.svelte';
  import type { BitmapFileInfo } from '../../rse/types';

  interface Props {
    targetImages: BitmapFileInfo[];
    worker: Worker;
    onApply: (mappings: { target: BitmapFileInfo; source: File }[]) => void;
    onClose: () => void;
  }

  let { targetImages, worker, onApply, onClose }: Props = $props();

  function handleApply(mappings: { target: BitmapFileInfo; source: File }[]) {
    onApply(mappings);
    onClose();
  }

  async function loadImage(image: BitmapFileInfo): Promise<{ name: string; width: number; height: number; rgb565Data: Uint8Array } | null> {
    return new Promise((resolve, reject) => {
      const handler = (e: MessageEvent) => {
        const { type, id, result, error } = e.data;
        if (id === 'loadSequenceImage') {
          worker.removeEventListener('message', handler);
          if (type === 'success') resolve(result);
          else reject(new Error(error || 'Failed to load image'));
        }
      };
      worker.addEventListener('message', handler);
      worker.postMessage({
        type: 'extractImage', id: 'loadSequenceImage',
        firmware: new Uint8Array(), imageName: image.name,
        width: image.width, height: image.height, offset: image.offset,
      });
    });
  }
</script>

<div class="sr-backdrop">
  <div class="sr-shell">
    <div class="sr-header">
      <span class="sr-title">Sequence Replacer</span>
      <button class="sr-close" onclick={onClose} title="Close">✕</button>
    </div>
    <div class="sr-body">
      <SequenceReplacer {targetImages} onLoadImage={loadImage} onApply={handleApply} onCancel={onClose} />
    </div>
  </div>
</div>

<style>
  .sr-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.8);
    display: flex; align-items: center; justify-content: center;
    z-index: 9998; padding: 24px;
  }
  .sr-shell {
    background: var(--panel); border: 1px solid var(--border2);
    border-radius: 10px; overflow: hidden;
    width: 100%; max-width: 1100px; height: 100%; max-height: 700px;
    display: flex; flex-direction: column;
    box-shadow: 0 32px 80px rgba(0,0,0,0.7);
  }
  .sr-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 20px; border-bottom: 1px solid var(--border);
    background: var(--surface); flex-shrink: 0;
  }
  .sr-title { font-size: 14px; font-weight: 600; color: var(--text); }
  .sr-close {
    width: 28px; height: 28px; border-radius: 5px;
    background: transparent; border: 1px solid var(--border);
    color: var(--text-dim); cursor: pointer; font-size: 13px;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.1s;
  }
  .sr-close:hover { background: #2a1010; border-color: #803020; color: #e09080; }
  .sr-body { flex: 1; overflow: hidden; min-height: 0; }
</style>
