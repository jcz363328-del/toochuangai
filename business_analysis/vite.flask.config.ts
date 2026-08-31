import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: fileURLToPath(new URL("./flask", import.meta.url)),
  base: "/ai/business-analysis/assets/",
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL("./dist-flask", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
  },
  resolve: {
    alias: {
      "@business-analysis": projectRoot,
    },
  },
});
