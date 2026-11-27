import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  base: '/static/replenishment-vben/',
  build: {
    outDir: fileURLToPath(new URL('../../../static/replenishment-vben', import.meta.url)),
    emptyOutDir: true,
  },
});
