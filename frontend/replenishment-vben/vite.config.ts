import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
export default defineConfig({plugins:[vue()],base:'/static/replenishment-vben/',build:{outDir:'../../static/replenishment-vben',emptyOutDir:true}});
