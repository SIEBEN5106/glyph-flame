import { defineConfig } from 'vitest/config';

export default defineConfig({
	test: {
		testTimeout: 15000, // 15 seconds default timeout for all tests
		hookTimeout: 15000,
	},
});
