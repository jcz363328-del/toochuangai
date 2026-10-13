import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const businessAnalysisRoot = fileURLToPath(new URL("../", import.meta.url));

export default defineConfig({
  root: fileURLToPath(new URL("../flask", import.meta.url)),
  base: "/ai/business-analysis/assets/",
  plugins: [
    react(),
    {
      name: "business-analysis-qa-scope",
      configureServer(server) {
        server.middlewares.use("/api/ai/business-analysis/scope", (_request, response) => {
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          response.end(JSON.stringify({
            scope: {
              role: "business_owner",
              department: "",
              operator: "",
              canViewAmounts: true,
            },
          }));
        });
      },
    },
  ],
  resolve: {
    alias: {
      "@business-analysis": businessAnalysisRoot,
    },
  },
  server: {
    proxy: {
      "/api/ai/business-analysis/dashboard": {
        target: "http://127.0.0.1:4311",
        rewrite: (path) => path.replace("/api/ai/business-analysis/dashboard", "/api/dashboard"),
      },
      "/api/ai/business-analysis/key-tasks": {
        target: "http://127.0.0.1:4311",
        rewrite: (path) => path.replace("/api/ai/business-analysis/key-tasks", "/api/key-tasks"),
        configure(proxy) {
          proxy.on("proxyReq", (proxyRequest) => {
            proxyRequest.setHeader("x-business-scope-role", "business_owner");
            proxyRequest.setHeader("x-business-scope-user", encodeURIComponent("周俊成"));
          });
        },
      },
    },
  },
});
