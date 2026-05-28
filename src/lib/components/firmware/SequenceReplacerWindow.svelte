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
    onApply(mappings); onClose();
  }

  async function loadImage(image: BitmapFileInfo): Promise<{ name: string; width: number; height: number; rgb565Data: Uint8Array } | null> {
    return new Promise((resolve, reject) => {
      const handler = (e: MessageEvent) => {
        const { type, id, result, error } = e.data;
        if (id === 'loadSequenceImage') {
          worker.removeEventListener('message', handler);
          if (type === 'success') resolve(result);
          else reject(new Error(error || 'Failed'));
        }
      };
      worker.addEventListener('message', handler);
      worker.postMessage({ type: 'extractImage', id: 'loadSequenceImage', firmware: new Uint8Array(), imageName: image.name, width: image.width, height: image.height, offset: image.offset });
    });
  }
</script>

<div class="sr-backdrop">
  <div class="sr-shell">
    <div class="sr-head">
      <span class="sr-title">sequence replacer</span>
      <button class="sr-close" onclick={onClose}><i class="fa-solid fa-xmark"></i></button>
    </div>
    <div class="sr-body">
      <SequenceReplacer {targetImages} onLoadImage={loadImage} onApply={handleApply} onCancel={onClose} />
    </div>
  </div>
</div>

<style>
  .sr-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 9998; padding: 24px; }
  .sr-shell { background: var(--bg); border: 1px solid var(--border2); border-radius: 5px; width: 100%; max-width: 1100px; height: 100%; max-height: 680px; display: flex; flex-direction: column; overflow: hidden; }
  .sr-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
  .sr-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1.4px; color: var(--text-dim); }
  .sr-close { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 12px; padding: 2px; transition: color 0.15s; }
  .sr-close:hover { color: var(--text); }
  .sr-body { flex: 1; overflow: hidden; min-height: 0; }
</style>
