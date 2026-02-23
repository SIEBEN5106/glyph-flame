<script lang="ts">
	import { Window, WindowBody, TitleBar, Button, GroupBox } from '$lib/components/98css';

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
	}

	interface Props {
		detail: ColorDetail;
		onclose: () => void;
	}

	let { detail, onclose }: Props = $props();

	const rgb565ToCss = (color: number): string => {
		const r = Math.round(((color >> 11) & 0x1f) * 255 / 31);
		const g = Math.round(((color >> 5) & 0x3f) * 255 / 63);
		const b = Math.round((color & 0x1f) * 255 / 31);
		return `rgb(${r}, ${g}, ${b})`;
	};

	const rgb565ToComponents = (color: number) => {
		const r = (color >> 11) & 0x1f;
		const g = (color >> 5) & 0x3f;
		const b = color & 0x1f;
		return { r, g, b };
	};

	const formatBytes = (bytes: number[] | undefined): string => {
		if (!bytes || bytes.length === 0) return 'N/A';
		return bytes.map((b) => '0x' + b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
	};

	const components = $derived(rgb565ToComponents(detail.color));
</script>

<div class="color-detail-wrapper">
	<Window width="550px">
		<TitleBar onclose={onclose}>Color Properties</TitleBar>
		<WindowBody>
			<div class="detail-layout">
				<!-- Preview Section -->
				<GroupBox title="Preview">
					<div class="preview-section">
						<div class="color-preview-large" style="background-color: {rgb565ToCss(detail.color)};">
						</div>
						<div class="preview-info">
							<div class="info-row">
								<span class="label">Semantic:</span>
								<span class="value">{detail.semantic}</span>
							</div>
							{#if detail.themeId !== undefined}
								<div class="info-row">
									<span class="label">Theme ID:</span>
									<span class="value">{detail.themeId}</span>
								</div>
							{/if}
							{#if detail.register !== undefined}
								<div class="info-row">
									<span class="label">Register:</span>
									<span class="value">R{detail.register}</span>
								</div>
							{/if}
						</div>
					</div>
				</GroupBox>

				<!-- Technical Details -->
				<GroupBox title="Technical Details">
					<div class="technical-section">
						<div class="info-row">
							<span class="label">RGB565 Value:</span>
							<span class="value mono">0x{detail.color.toString(16).padStart(4, '0').toUpperCase()}</span>
						</div>
						<div class="info-row">
							<span class="label">Decimal:</span>
							<span class="value mono">{detail.color}</span>
						</div>
						<div class="info-row">
							<span class="label">Binary:</span>
							<span class="value mono binary">{detail.color.toString(2).padStart(16, '0')}</span>
						</div>
						<div class="separator"></div>
						<div class="info-row">
							<span class="label">Red (5-bit):</span>
							<span class="value mono">{components.r} (0x{components.r.toString(16).toUpperCase()})</span>
						</div>
						<div class="info-row">
							<span class="label">Green (6-bit):</span>
							<span class="value mono">{components.g} (0x{components.g.toString(16).toUpperCase()})</span>
						</div>
						<div class="info-row">
							<span class="label">Blue (5-bit):</span>
							<span class="value mono">{components.b} (0x{components.b.toString(16).toUpperCase()})</span>
						</div>
						<div class="separator"></div>
						<div class="info-row">
							<span class="label">Normalized RGB:</span>
							<span class="value mono"
								>{Math.round(components.r * 255 / 31)}, {Math.round(components.g * 255 / 63)}, {Math.round(components.b * 255 / 31)}</span
							>
						</div>
					</div>
				</GroupBox>

				<!-- Instruction Details -->
				<GroupBox title="Instruction Details">
					<div class="instruction-section">
						{#if detail.isPatched !== undefined}
							<div class="info-row">
								<span class="label">Code Path:</span>
								<span class="value" class:patched={detail.isPatched} class:unpatched={!detail.isPatched}>
									{detail.isPatched ? 'PATCHED' : 'Unpatched'}
								</span>
							</div>
						{/if}
						{#if detail.movwAddress && detail.movwInstruction}
							<div class="info-row">
								<span class="label">MOVW Addr:</span>
								<span class="value mono">{detail.movwAddress}</span>
							</div>
							<div class="info-row">
								<span class="label">MOVW Instr:</span>
								<span class="value mono">{detail.movwInstruction}</span>
							</div>
						{/if}
						{#if detail.strhAddress && detail.strhInstruction}
							<div class="info-row">
								<span class="label">STRH Addr:</span>
								<span class="value mono">{detail.strhAddress}</span>
							</div>
							<div class="info-row">
								<span class="label">STRH Instr:</span>
								<span class="value mono">{detail.strhInstruction}</span>
							</div>
						{/if}
						{#if detail.address && detail.instruction && !detail.movwAddress}
							<div class="info-row">
								<span class="label">Address:</span>
								<span class="value mono">{detail.address}</span>
							</div>
							<div class="info-row">
								<span class="label">Instruction:</span>
								<span class="value mono">{detail.instruction}</span>
							</div>
						{/if}
						{#if detail.rawBytes && detail.rawBytes.length > 0}
							<div class="info-row">
								<span class="label">Raw Bytes:</span>
								<span class="value mono">{formatBytes(detail.rawBytes)}</span>
							</div>
						{/if}
					</div>
				</GroupBox>

				<!-- Buttons -->
				<div class="button-row">
					<Button onclick={onclose}>Close</Button>
				</div>
			</div>
		</WindowBody>
	</Window>
</div>

<style>
	.color-detail-wrapper {
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

	.detail-layout {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 400px;
		max-width: 500px;
	}

	.preview-section {
		display: flex;
		gap: 16px;
		align-items: flex-start;
	}

	.color-preview-large {
		width: 80px;
		height: 80px;
		border: 2px solid #808080;
		flex-shrink: 0;
	}

	.preview-info {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.technical-section,
	.instruction-section {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 12px;
	}

	.label {
		color: #000000;
		font-weight: normal;
	}

	.value {
		color: #000000;
	}

	.value.mono,
	.value.binary {
		font-family: 'Courier New', monospace;
		font-size: 11px;
	}

	.value.patched {
		color: #008000;
		font-weight: bold;
	}

	.value.unpatched {
		color: #800000;
	}

	.separator {
		height: 1px;
		background-color: #c0c0c0;
		border-top: 1px solid #ffffff;
		margin: 4px 0;
	}

	.button-row {
		display: flex;
		justify-content: flex-end;
		gap: 4px;
	}
</style>
