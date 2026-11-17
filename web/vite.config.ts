import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { parseChangelog } from "./src/lib/release";

const webDir = dirname(fileURLToPath(import.meta.url));
const localVersion = readFileSync(resolve(webDir, "../VERSION"), "utf8").trim() || "dev";
const localChangelog = readFileSync(resolve(webDir, "../CHANGELOG.md"), "utf8");
const externalCacheDir = process.env.INFINITE_CANVAS_VITE_CACHE_DIR?.trim();
const externalBuildDir = process.env.INFINITE_CANVAS_BUILD_DIR?.trim();
const hostAppUrl = process.env.XIAOHA_HOST_APP_URL?.trim() || "http://127.0.0.1:8000";

export default defineConfig(({ command }) => ({
    base: process.env.VITE_BASE || (command === "build" ? "/infinite-canvas/" : "/"),
    ...(externalCacheDir ? { cacheDir: resolve(externalCacheDir) } : {}),
    plugins: [react()],
    server: {
        allowedHosts: ["www.toochuangai.com", "toochuangai.com"],
        proxy: {
            "/lashforge/api/bootstrap-config": {
                target: hostAppUrl,
                changeOrigin: false,
                rewrite: () => "/api/infinite-canvas/bootstrap-config",
            },
        },
    },
    ...(externalBuildDir ? { build: { outDir: resolve(externalBuildDir), emptyOutDir: true } } : {}),
    resolve: {
        alias: {
            "@": resolve(webDir, "src"),
        },
    },
    define: {
        __APP_VERSION__: JSON.stringify(localVersion),
        __APP_RELEASES__: JSON.stringify(parseChangelog(localChangelog)),
    },
}));
