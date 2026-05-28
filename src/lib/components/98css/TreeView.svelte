<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { ClassValue } from 'svelte/elements';
  import { clsx } from 'clsx';

  interface TreeNode {
    id: string;
    label: string;
    children?: TreeNode[];
    expanded?: boolean;
    disabled?: boolean;
  }

  interface Props {
    class?: ClassValue;
    nodes: TreeNode[];
    expanded?: Set<string>;
    selected?: string;
    replacedImages?: string[];
    onToggle?: (nodeId: string) => void;
    onSelect?: (nodeId: string) => void;
    children?: Snippet;
  }

  let { class: className, nodes, expanded = $bindable(new Set<string>()), selected = $bindable(''), replacedImages = [], onToggle, onSelect, children }: Props = $props();

  const treeViewClass = $derived(clsx('tree-view', className));
  let programmaticUpdates = $state(new Set<string>());

  function isSelected(nodeId: string): boolean { return selected === nodeId; }

  function toggleNode(nodeId: string): void {
    const newExpanded = new Set(expanded);
    if (expanded.has(nodeId)) newExpanded.delete(nodeId); else newExpanded.add(nodeId);
    programmaticUpdates.add(nodeId);
    expanded = newExpanded;
    requestAnimationFrame(() => { programmaticUpdates.delete(nodeId); });
    onToggle?.(nodeId);
  }

  function handleToggle(nodeId: string, e: Event): void {
    if (programmaticUpdates.has(nodeId)) { e.preventDefault(); e.stopPropagation(); return; }
    toggleNode(nodeId);
  }

  function handleLeafKeydown(nodeId: string, e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(nodeId); }
  }
</script>

{#snippet renderNodes(nodeList: TreeNode[])}
  {#each nodeList as node (node.id)}
    <li>
      {#if node.children && node.children.length > 0}
        <details open={expanded.has(node.id)} ontoggle={(e) => handleToggle(node.id, e)}>
          <summary>{node.label}</summary>
          <ul>{@render renderNodes(node.children)}</ul>
        </details>
      {:else}
        <span class="leaf-node" class:selected={isSelected(node.id)} class:replaced={replacedImages.includes(node.label)}
          onclick={() => onSelect?.(node.id)}
          onkeydown={(e) => handleLeafKeydown(node.id, e)}
          role="button" tabindex="0">{node.label}</span>
      {/if}
    </li>
  {/each}
{/snippet}

<ul class={treeViewClass}>
  {@render renderNodes(nodes)}
  {#if children}{@render children()}{/if}
</ul>

<style>
  .tree-view { max-height: 100%; overflow-y: auto; user-select: none; -webkit-user-select: none; }
  .leaf-node { cursor: pointer; padding: 2px 4px; display: inline-block; }
  .leaf-node.selected { background-color: transparent; color: var(--accent); }
  .leaf-node.replaced { color: var(--blue); }
  .leaf-node:focus { outline: none; }
</style>
