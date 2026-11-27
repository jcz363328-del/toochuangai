import { spawn } from "node:child_process";
import { closeSync, existsSync, mkdirSync, openSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const WEB_ROOT = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(WEB_ROOT, "..");
const DIAGNOSTIC_HEALTH = "http://127.0.0.1:4174/api/diagnostic/health";

const wait = (milliseconds) => new Promise((resolveWait) => setTimeout(resolveWait, milliseconds));

async function diagnosticReady() {
  try {
    const response = await fetch(DIAGNOSTIC_HEALTH, { signal: AbortSignal.timeout(800) });
    return response.ok;
  } catch {
    return false;
  }
}

function diagnosticService() {
  return {
    name: "sellfox-diagnostic-service",
    async configureServer(server) {
      if (await diagnosticReady()) return;

      const logDir = resolve(WEB_ROOT, ".logs");
      const python = resolve(REPO_ROOT, ".venv", "Scripts", "python.exe");
      const script = resolve(REPO_ROOT, "sellfox_ad_diagnostic_server.py");
      mkdirSync(logDir, { recursive: true });
      const stdout = openSync(resolve(logDir, "diagnostic.out.log"), "a");
      const stderr = openSync(resolve(logDir, "diagnostic.err.log"), "a");
      const child = spawn(existsSync(python) ? python : "python", [script], {
        cwd: REPO_ROOT,
        stdio: ["ignore", stdout, stderr],
        windowsHide: true,
      });

      for (let attempt = 0; attempt < 40 && !(await diagnosticReady()); attempt += 1) await wait(150);
      if (!(await diagnosticReady())) {
        child.kill();
        closeSync(stdout);
        closeSync(stderr);
        throw new Error("4174 diagnostic service failed to start; see .logs/diagnostic.err.log");
      }

      server.httpServer?.once("close", () => {
        if (!child.killed) child.kill();
        closeSync(stdout);
        closeSync(stderr);
      });
    },
  };
}

export default defineConfig({
  build: {
    outDir: "dist/client",
  },
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    host: "127.0.0.1",
    allowedHosts: ["terminal.local"],
    proxy: {
      "/api/diagnostic": {
        target: "http://127.0.0.1:4174",
        changeOrigin: true,
      },
    },
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [diagnosticService(), react()],
});
