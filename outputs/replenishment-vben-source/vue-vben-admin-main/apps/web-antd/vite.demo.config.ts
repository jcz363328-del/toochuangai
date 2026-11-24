import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({ plugins: [vue()], server: { host: '127.0.0.1', port: 5678 }, build: { outDir: 'dist-demo', rollupOptions: { input: 'replenishment-demo.html' } } });
