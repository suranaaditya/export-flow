import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import proxyOptions from './proxyOptions';

// https://vitejs.dev/config/
export default defineConfig({
	plugins: [react()],
	server: {
		port: 8080,
		proxy: proxyOptions,
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src'),
		},
	},
	build: {
		outDir: '../exportflow/public/frontend',
		emptyOutDir: true,
		target: 'es2017',
	},
});
