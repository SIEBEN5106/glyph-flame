<script lang="ts">
  import { Window, WindowBody } from '../98css';
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

  function handleCancel() {
    onClose();
  }

  // Load image data from firmware via worker
  async function loadImage(image: BitmapFileInfo): Promise<{ name: string; width: number; height: number; rgb565Data: Uint8Array } | null> {
    return new Promise((resolve, reject) => {
      const handler = (e: MessageEvent) => {
        const { type, id, result, error } = e.data;
        if (id === 'loadSequenceImage') {
          worker.removeEventListener('message', handler);
          if (type === 'success') {
            resolve(result as { name: string; width: number; height: number; rgb565Data: Uint8Array });
          } else {
            reject(new Error(error || 'Failed to load image'));
          }
        }
      };

      worker.addEventListener('message', handler);
      worker.postMessage({
        type: 'extractImage',
        id: 'loadSequenceImage',
        firmware: new Uint8Array(),
        imageName: image.name,
        width: image.width,
        height: image.height,
        offset: image.offset,
      });
    });
  }
</script>

<Window
  title="Replace Image Sequence"
  class="sequence-replacer-window-wrapper"
  onclose={onClose}
>
  <WindowBody>
    <SequenceReplacer
      {targetImages}
      onLoadImage={loadImage}
      onApply={handleApply}
      onCancel={handleCancel}
    />
  </WindowBody>
</Window>

<style>
  :global(.sequence-replacer-window-wrapper) {
    max-width: 1024px;
    max-height: 768px;
    width: 100%;
    height: auto;
    margin: 64px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
  }

  :global(.sequence-replacer-window-wrapper .window-body) {
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>
