<script lang="ts">
	import { TableView, type TableRow, type TableCell } from '$lib/components/98css';

	function rgb565ToCss(color: number): string {
		const r = Math.round(((color >> 11) & 0x1f) * 255 / 31);
		const g = Math.round(((color >> 5) & 0x3f) * 255 / 63);
		const b = Math.round((color & 0x1f) * 255 / 31);
		return `rgb(${r}, ${g}, ${b})`;
	}

	export interface ColorEntry {
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
		entries: ColorEntry[];
		title?: string;
		onDoubleClick?: (entry: ColorEntry) => void;
		height?: string;
	}

	let { entries, title = 'Colors', onDoubleClick, height = '300px' }: Props = $props();

	let selectedKey = $state<string | null>(null);

	const headers = ['Property', 'Theme', 'Register', 'Source', 'Color Value', 'Preview'];

	// Convert to table rows
	const rows = $derived.by(() => {
		const result = entries.map((entry, idx) => {
			const colorHex = '0x' + entry.color.toString(16).padStart(4, '0').toUpperCase();
			const themeDisplay = entry.themeId !== undefined ? `Theme ${entry.themeId}` : 'N/A';
			const regDisplay = entry.register !== undefined ? `R${entry.register}` : 'N/A';
			const sourceDisplay = entry.isPatched ? 'Patched' : 'Normal';
			const colorCss = rgb565ToCss(entry.color);

			const cells: TableCell[] = [
				{ content: entry.semantic },
				{ content: themeDisplay },
				{ content: regDisplay },
				{ content: sourceDisplay },
				{ content: colorHex, class: 'mono' },
				{ content: '', class: 'color-preview', style: `--color-bg: ${colorCss}` }
			];

			return {
				key: `${entry.semantic}-${entry.themeId ?? 0}-${entry.register ?? 0}-${idx}`,
				cells,
				extra: entry
			} as TableRow & { extra: ColorEntry };
		});
		return result;
	});

	function handleRowSelect(rowKey: string | null) {
		selectedKey = rowKey;
	}

	function handleRowDoubleClick(rowKey: string) {
		const row = rows.find((r) => r.key === rowKey);
		if (row?.extra && onDoubleClick) {
			onDoubleClick(row.extra);
		}
	}
</script>

<div class="color-table-container">
	<TableView
		{headers}
		{rows}
		interactive={true}
		bind:selectedRow={selectedKey}
		onSelect={handleRowSelect}
		onRowDoubleClick={handleRowDoubleClick}
		{height}
		width="100%"
	/>
</div>

<style>
	.color-table-container {
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}

	:global(.color-table-container .sunken-panel) {
		border: 2px inset #c0c0c0;
		background-color: #ffffff;
		overflow-y: auto;
	}

	/* Ensure table header stays on top */
	:global(.color-table-container thead) {
		position: sticky;
		top: 0;
		z-index: 10;
		background-color: #ffffff;
	}

	/* Color preview cell - need to inject it into the table cells */
	:global(.color-table-container td:last-child) {
		width: 50px;
		padding: 2px !important;
		text-align: center;
	}

	/* Color preview using CSS variable */
	:global(.color-table-container td.color-preview::after) {
		content: '';
		display: inline-block;
		width: 32px;
		height: 12px;
		background-color: var(--color-bg);
		border: 1px solid #808080;
	}
</style>
