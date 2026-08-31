import http from "node:http";
import { config } from "./config.mjs";
import { createDashboardService } from "./dashboard.mjs";
import { createMssqlAdapter } from "./db/mssql.mjs";
import { publicFormulaCatalog } from "./formulas/evaluate.mjs";

const adapter = createMssqlAdapter(config.database);
const dashboardService = createDashboardService({
  adapter,
  cacheOptions: config.cache,
  timezone: config.dashboard.timezone,
  refreshAfterMs: config.dashboard.refreshAfterMs,
});

function json(response, status, body) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(JSON.stringify(body));
}

function badRequest(message) {
  const error = new Error(message);
  error.status = 400;
  error.code = "INVALID_REQUEST";
  return error;
}

function parseDashboardRequest(url) {
  const allowed = new Set(["period", "basis", "department", "operator", "store", "force"]);
  for (const key of url.searchParams.keys()) if (!allowed.has(key)) throw badRequest("Unsupported query parameter");
  const period = url.searchParams.get("period") || "";
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(period)) throw badRequest("period must be YYYY-MM");
  const basis = url.searchParams.get("basis") || "auto";
  if (!["auto", "mtd", "full"].includes(basis)) throw badRequest("basis must be auto, mtd, or full");
  const text = (name) => {
    const value = url.searchParams.get(name)?.trim() || null;
    if (value && (value.length > 80 || /[\u0000-\u001f]/.test(value))) throw badRequest(`${name} is invalid`);
    return value;
  };
  const rawStore = url.searchParams.get("store");
  const store = rawStore == null || rawStore === "" ? null : Number(rawStore);
  if (store != null && (!Number.isInteger(store) || store <= 0 || store > 2_147_483_647)) {
    throw badRequest("store must be a positive integer");
  }
  const force = url.searchParams.get("force") || "0";
  if (!["0", "1"].includes(force)) throw badRequest("force must be 0 or 1");
  return { period, basis, department: text("department"), operator: text("operator"), store, force: force === "1" };
}

async function route(request, response) {
  if (request.method !== "GET") {
    json(response, 405, { error: { code: "METHOD_NOT_ALLOWED", message: "Only GET is supported" } });
    return;
  }
  const url = new URL(request.url || "/", `http://${config.api.host}:${config.api.port}`);
  if (url.pathname === "/api/health") {
    const database = await adapter.health();
    const newest = dashboardService.newestCache();
    json(response, 200, {
      service: "ok",
      database,
      lastSuccessAt: dashboardService.lastSuccessAt(),
      cacheAgeMs: newest?.ageMs ?? null,
    });
    return;
  }
  if (url.pathname === "/api/dashboard") {
    const input = parseDashboardRequest(url);
    json(response, 200, await dashboardService.dashboard(input, config.database.configured));
    return;
  }
  if (url.pathname === "/api/formulas") {
    json(response, 200, { formulas: publicFormulaCatalog() });
    return;
  }
  json(response, 404, { error: { code: "NOT_FOUND", message: "Route not found" } });
}

const server = http.createServer((request, response) => {
  route(request, response).catch((error) => {
    const status = error?.status === 400 ? 400 : 500;
    const code = status === 400 ? error.code : "INTERNAL_ERROR";
    if (status === 500) console.warn(`[sales-api] ${code}`);
    json(response, status, { error: { code, message: status === 400 ? error.message : "Request failed" } });
  });
});

server.listen(config.api.port, config.api.host, () => {
  console.log(`[sales-api] listening on http://${config.api.host}:${config.api.port}`);
});

let closing = false;
async function shutdown() {
  if (closing) return;
  closing = true;
  server.close();
  await adapter.close();
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
