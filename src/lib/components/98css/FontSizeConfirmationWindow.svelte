<script lang="ts">
	import { Window, WindowBody, Button, Radio, GroupBox } from './index.js';
	import type { FontDebugImage } from '$lib/rse/utils/font-detection';

	interface Props {
		fileName: string;
		debugImages?: FontDebugImage[];
		oncancel: () => void;
		onconfirm: (fontType: 'SMALL' | 'LARGE') => void;
	}

	let {
		fileName,
		debugImages = [],
		oncancel,
		onconfirm
	}: Props = $props();

	let selectedSize = $state<'SMALL' | 'LARGE'>('SMALL');
</script>

<div class="confirmation-wrapper">
	<Window title="Confirm Font Size" width="500px" showClose={false}>
		<WindowBody>
			<div class="confirmation-content">
				<div class="message">
					<p>
						The font <strong>{fileName}</strong> could not be automatically identified as 12px
						(SMALL) or 16px (LARGE). Please select the appropriate size manually.
					</p>
				</div>

				<GroupBox label="Font Size">
					<div class="radio-options">
						<Radio
							label="12px (SMALL) - Basic Latin, Latin-1, symbols"
							name="fontSize"
							value="SMALL"
							bind:checked={selectedSize}
						/>
						<Radio
							label="16px (LARGE) - CJK characters (Chinese, Japanese, Korean)"
							name="fontSize"
							value="LARGE"
							bind:checked={selectedSize}
						/>
					</div>
				</GroupBox>

				{#if debugImages && debugImages.length > 0}
					<div class="debug-preview">
						<p class="debug-title">Rendered preview at tested sizes:</p>
						<div class="debug-images">
							{#each debugImages as img}
								<div class="debug-image">
									<img src={img.dataUrl} alt="Font preview at {img.fontSize}px" />
									<span>{img.fontSize}px</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<div class="buttons">
					<Button onclick={oncancel}>Cancel</Button>
					<Button variant="primary" onclick={() => onconfirm(selectedSize)}>
						Confirm {selectedSize === 'SMALL' ? '12px' : '16px'}
					</Button>
				</div>
			</div>
		</WindowBody>
	</Window>
</div>

<style>
	.confirmation-wrapper {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 10000;
		background-color: rgba(0, 0, 0, 0.1);
	}

	.confirmation-content {
		padding-top: 8px;
		padding-left: 8px;
		padding-right: 4px;
		padding-bottom: 4px;
	}

	.message {
		margin-bottom: 16px;
	}

	.message p {
		margin: 0;
		font-size: 12px;
		color: #000000;
		white-space: pre-wrap;
		word-wrap: break-word;
	}

	.radio-options {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 8px;
	}

	.radio-options :global(.field-row) {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.radio-options :global(label) {
		font-size: 12px;
		cursor: pointer;
	}

	.debug-preview {
		margin-top: 16px;
		padding: 8px;
		background-color: #f0f0f0;
		border: 1px inset #c0c0c0;
	}

	.debug-title {
		margin: 0 0 8px 0;
		font-size: 11px;
		color: #666;
	}

	.debug-images {
		display: flex;
		gap: 16px;
		justify-content: center;
	}

	.debug-image {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.debug-image img {
		border: 1px solid #999;
		image-rendering: pixelated;
		max-width: 200px;
	}

	.debug-image span {
		font-size: 11px;
		color: #666;
	}

	.buttons {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 16px;
	}

	:global(.buttons button) {
		min-width: 75px;
	}
</style>
