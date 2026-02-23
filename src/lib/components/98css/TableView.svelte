<script lang="ts">
	import type { ClassValue } from 'svelte/elements';
	import { clsx } from 'clsx';

	export interface TableCell {
		content: string;
		class?: ClassValue;
		style?: string;
	}

	export interface TableRow {
		cells: TableCell[];
		class?: ClassValue;
		highlighted?: boolean;
		key?: string;
	}

	interface Props {
		class?: ClassValue;
		headers: string[];
		rows: TableRow[];
		interactive?: boolean;
		selectedRow?: string | null;
		onSelect?: (rowKey: string | null) => void;
		onRowDoubleClick?: (rowKey: string) => void;
		height?: string;
		width?: string;
	}

	let {
		class: className,
		headers,
		rows,
		interactive = false,
		selectedRow = $bindable(null as string | null),
		onSelect,
		onRowDoubleClick,
		height = '120px',
		width = '240px'
	}: Props = $props();

	function handleRowClick(rowKey: string): void {
		if (!interactive) return;

		if (selectedRow === rowKey) {
			selectedRow = null;
		} else {
			selectedRow = rowKey;
		}
		onSelect?.(selectedRow);
	}

	function handleRowDoubleClick(rowKey: string): void {
		if (!interactive) return;
		onRowDoubleClick?.(rowKey);
	}

	function isRowHighlighted(row: TableRow): boolean {
		return row.highlighted === true || row.key === selectedRow;
	}

	const panelStyle = $derived(`height: ${height}; width: ${width};`);
	const tableClass = $derived(clsx(className, interactive ? 'interactive' : ''));
</script>

<div class="sunken-panel" style={panelStyle}>
	<table class={tableClass}>
		<thead>
			<tr>
				{#each headers as header}
					<th>{header}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as row}
				<tr
					class={row.class}
					class:highlighted={isRowHighlighted(row)}
					onclick={() => row.key && handleRowClick(row.key)}
					ondblclick={() => row.key && handleRowDoubleClick(row.key)}
				>
					{#each row.cells as cell}
						<td class={cell.class} style={cell.style}>{cell.content}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	table {
		width: 100%;
	}
</style>