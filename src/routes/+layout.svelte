<script lang="ts">
	import { onMount } from 'svelte';
	import favicon from '$lib/assets/favicon.svg';
	import { debugMode } from '$lib/stores';

	let { children } = $props();

	onMount(() => {
		const unsub = debugMode.subscribe((v) => {
			document.body.classList.toggle('debug-mode', v);
		});
		return unsub;
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<link href="https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&family=Newsreader:ital,opsz,wght@0,6..72,400;1,6..72,400&display=swap" rel="stylesheet" />
	<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" crossorigin="anonymous" />
</svelte:head>

{@render children()}

<style>
	:global(*, *::before, *::after) { box-sizing: border-box; margin: 0; padding: 0; }

	:global(html, body) {
		height: 100vh; overflow: hidden;
		font-family: 'DM Mono', monospace;
		font-size: 13px;
		line-height: 1.55;
		-webkit-font-smoothing: antialiased;
		background: var(--bg);
		color: var(--text);
		transition: background 0.25s, color 0.25s;
	}

	:global(button) { font-family: 'DM Mono', monospace; font-size: 13px; }
	:global(input)  { font-family: 'DM Mono', monospace; font-size: 12px; }

	/* ── reign (default) ── */
	:global(:root), :global(:root.theme-reign) {
		--bg:        #1a1917;
		--panel:     #23221f;
		--surface:   #23221f;
		--surface2:  #2a2926;
		--border:    #33312c;
		--border2:   #3d3a34;
		--accent:    #9b6fd4;
		--accent2:   #b080e0;
		--accent-bg: #261e35;
		--text:      #e8e4dc;
		--text-dim:  #8a857b;
		--text-faint:#504d47;
		--danger:    #c06050;
		--blue:      #6b9bd4;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Catppuccin Mocha ── */
	:global(:root.theme-mocha) {
		--bg:        #1e1e2e;
		--panel:     #181825;
		--surface:   #313244;
		--surface2:  #45475a;
		--border:    #313244;
		--border2:   #45475a;
		--accent:    #cba6f7;
		--accent2:   #d6b9fa;
		--accent-bg: #2a1f3d;
		--text:      #cdd6f4;
		--text-dim:  #a6adc8;
		--text-faint:#585b70;
		--danger:    #f38ba8;
		--blue:      #89b4fa;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Catppuccin Frappé ── */
	:global(:root.theme-frappe) {
		--bg:        #303446;
		--panel:     #292c3c;
		--surface:   #414559;
		--surface2:  #51576d;
		--border:    #414559;
		--border2:   #51576d;
		--accent:    #ca9ee6;
		--accent2:   #d6b4f0;
		--accent-bg: #2a2040;
		--text:      #c6d0f5;
		--text-dim:  #a5adce;
		--text-faint:#626880;
		--danger:    #e78284;
		--blue:      #8caaee;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Catppuccin Macchiato ── */
	:global(:root.theme-macchiato) {
		--bg:        #24273a;
		--panel:     #1e2030;
		--surface:   #363a4f;
		--surface2:  #494d64;
		--border:    #363a4f;
		--border2:   #494d64;
		--accent:    #c6a0f6;
		--accent2:   #d2b0f8;
		--accent-bg: #28203a;
		--text:      #cad3f5;
		--text-dim:  #a5adcb;
		--text-faint:#5b6078;
		--danger:    #ed8796;
		--blue:      #8aadf4;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Catppuccin Latte ── */
	:global(:root.theme-latte) {
		--bg:        #eff1f5;
		--panel:     #e6e9ef;
		--surface:   #ccd0da;
		--surface2:  #bcc0cc;
		--border:    #ccd0da;
		--border2:   #acb0be;
		--accent:    #8839ef;
		--accent2:   #7a35d6;
		--accent-bg: #ede0ff;
		--text:      #4c4f69;
		--text-dim:  #6c6f85;
		--text-faint:#9ca0b0;
		--danger:    #d20f39;
		--blue:      #1e66f5;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Dark Orange ── */
	:global(:root.theme-dark-orange) {
		--bg:        #18140e;
		--panel:     #221c14;
		--surface:   #2a2418;
		--surface2:  #302818;
		--border:    #3a3020;
		--border2:   #4a4028;
		--accent:    #d4821a;
		--accent2:   #e89218;
		--accent-bg: #3a2810;
		--text:      #c4b080;
		--text-dim:  #8a7a5a;
		--text-faint:#4a3a22;
		--danger:    #c04030;
		--blue:      #4a7ab0;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Parchment ── */
	:global(:root.theme-parchment) {
		--bg:        #f2ece0;
		--panel:     #e8dfc8;
		--surface:   #ddd3b5;
		--surface2:  #d0c8a0;
		--border:    #c8b888;
		--border2:   #b8a068;
		--accent:    #8b5a2b;
		--accent2:   #c07830;
		--accent-bg: #f0e0c0;
		--text:      #2a1a08;
		--text-dim:  #5a4030;
		--text-faint:#9a8060;
		--danger:    #8b1a1a;
		--blue:      #1a5a8b;
		--swatch-black:  #1a1a1a;
		--swatch-blue:   #1e3a5f;
		--swatch-green:  #1a3a1a;
		--swatch-orange: #3a1e0a;
		--swatch-pink:   #3a1a2a;
	}

	/* ── Scrollbars ── */
	:global(::-webkit-scrollbar) { width: 3px; height: 3px; }
	:global(::-webkit-scrollbar-track) { background: transparent; }
	:global(::-webkit-scrollbar-thumb) { background: var(--border2); border-radius: 4px; }
	:global(::-webkit-scrollbar-thumb:hover) { background: var(--text-dim); }
</style>
