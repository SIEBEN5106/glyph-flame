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

	function handleConfirm() {
		onconfirm(selectedSize);
	}
</script>

<div class="confirmation-wrapper">
	<Window title="Confirm Font Size" width="550px" showClose={false}>
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
							checked={selectedSize === 'SMALL'}
							onchange={() => selectedSize = 'SMALL'}
						/>
						<Radio
							label="16px (LARGE) - CJK characters (Chinese, Japanese, Korean)"
							name="fontSize"
							value="LARGE"
							checked={selectedSize === 'LARGE'}
							onchange={() => selectedSize = 'LARGE'}
						/>
					</div>
				</GroupBox>

				{#if debugImages && debugImages.length > 0}
					<div class="preview-section">
						<div class="preview-scroll">
							<div class="preview-row">
								<div class="row-label">
									<span class="size-label">12px</span>
								</div>
								<div class="row-content">
									{#each debugImages as img}
										{#if img.fontSize === 12}
											<div class="preview-image">
												<img src={img.dataUrl} alt="Font preview at {img.fontSize}px" />
												<span class="preview-info">{img.fontSize}px ({img.antiAliasedCount} aa)</span>
											</div>
										{/if}
									{/each}
								</div>
							</div>
							<div class="preview-row">
								<div class="row-label">
									<span class="size-label">16px</span>
								</div>
								<div class="row-content">
									{#each debugImages as img}
										{#if img.fontSize === 16}
											<div class="preview-image">
												<img src={img.dataUrl} alt="Font preview at {img.fontSize}px" />
												<span class="preview-info">{img.fontSize}px ({img.antiAliasedCount} aa)</span>
											</div>
										{/if}
									{/each}
								</div>
							</div>
						</div>
					</div>
				{/if}

				<div class="buttons">
					<Button onclick={oncancel}>Cancel</Button>
					<Button variant="primary" onclick={handleConfirm}>
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

	.preview-section {
		margin-top: 16px;
		border: 2px inset #c0c0c0;
	}

	.preview-scroll {
		max-height: 300px;
		overflow-y: auto;
		overflow-x: auto;
		padding: 8px;
		background-color: #ffffff;
	}

	.preview-row {
		display: flex;
		gap: 8px;
		margin-bottom: 8px;
	}

	.preview-row:last-child {
		margin-bottom: 0;
	}

	.row-label {
		flex-shrink: 0;
		width: 60px;
		display: flex;
		align-items: flex-start;
		padding-top: 2px;
	}

	.size-label {
		font-size: 12px;
		font-weight: bold;
		color: #000080;
	}

	.row-content {
		display: flex;
		gap: 16px;
		flex-wrap: nowrap;
	}

	.preview-image {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 4px;
	}

	.preview-image img {
		border: 1px solid #808080;
		background-color: #e0e0e0;
		image-rendering: pixelated;
	}

	.preview-info {
		font-size: 11px;
		color: #666;
	}

	.buttons {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		margin-top: 16px;
		padding-top: 8px;
		border-top: 1px solid #c0c0c0;
	}

	:global(.buttons button) {
		min-width: 75px;
	}
</style>
