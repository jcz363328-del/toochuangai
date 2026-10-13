import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const root = path.resolve("business_analysis/dist-flask");
const dashboardSnapshotPath = path.resolve("business_analysis/app/data/workbook-data.json");
const host = "127.0.0.1";
const port = Number(process.env.PREVIEW_PORT || 4395);
const mime = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function ownerDashboardSnapshot() {
  const data = JSON.parse(fs.readFileSync(dashboardSnapshotPath, "utf8"));
  data.meta = data.meta || {};
  data.meta.accessScope = {
    role: "business_owner",
    department: null,
    operator: null,
    userName: "周俊成",
    canViewAmounts: true,
    categoryRatioVisible: true,
  };
  const now = new Date().toISOString();
  return {
    data,
    formulas: [],
    source: {
      mode: "database",
      stale: false,
      fetchedAt: now,
      lastSuccessAt: now,
      latencyMs: 1,
      warning: null,
      database: { configured: true, status: "up", latencyMs: 1 },
    },
    refreshAfterMs: 60_000,
  };
}

function previewIndexHtml(filePath) {
  const payload = JSON.stringify(ownerDashboardSnapshot()).replace(/</g, "\\u003c");
  const bootstrap = `<script data-preview-owner-bootstrap>
    (() => {
      const dashboard = ${payload};
      const nativeFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (url.includes("/api/ai/business-analysis/dashboard")) {
          return Promise.resolve(new Response(JSON.stringify(dashboard), {
            status: 200,
            headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
          }));
        }
        return nativeFetch(input, init);
      };
    })();
  </script>`;
  return fs.readFileSync(filePath, "utf8").replace("</head>", `${bootstrap}</head>`);
}

function proxy(request, response, pathname) {
  const upstreamPath = pathname.replace("/api/ai/business-analysis/key-tasks", "/api/key-tasks");
  const upstream = http.request({
    hostname: "127.0.0.1",
    port: 4391,
    path: upstreamPath,
    method: request.method,
    headers: {
      accept: "application/json",
      "content-type": request.headers["content-type"] || "application/json",
      "x-business-scope-role": "business_owner",
      "x-business-scope-user": encodeURIComponent("周俊成"),
    },
  }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
    upstreamResponse.pipe(response);
  });
  upstream.on("error", () => {
    response.writeHead(502, { "content-type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ error: { message: "Preview API unavailable" } }));
  });
  request.pipe(upstream);
}

http.createServer((request, response) => {
  const url = new URL(request.url || "/", `http://${host}:${port}`);
  if (url.pathname.startsWith("/api/ai/business-analysis/key-tasks")) {
    proxy(request, response, url.pathname);
    return;
  }
  if (url.pathname === "/api/ai/business-analysis/dashboard") {
    response.writeHead(200, {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    });
    response.end(JSON.stringify(ownerDashboardSnapshot()));
    return;
  }

  const relative = url.pathname === "/"
    ? "index.html"
    : url.pathname.replace(/^\/ai\/business-analysis\/assets\//, "");
  const filePath = path.resolve(root, relative);
  if (!filePath.startsWith(root) || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  if (path.basename(filePath) === "index.html") {
    response.writeHead(200, {
      "content-type": mime[".html"],
      "cache-control": "no-store",
    });
    response.end(previewIndexHtml(filePath));
    return;
  }
  response.writeHead(200, {
    "content-type": mime[path.extname(filePath)] || "application/octet-stream",
    "cache-control": "no-store",
  });
  fs.createReadStream(filePath).pipe(response);
}).listen(port, host, () => {
  console.log(`Key task preview listening on http://${host}:${port}`);
});
