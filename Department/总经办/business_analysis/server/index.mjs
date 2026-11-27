import http from "node:http";
import { config } from "./config.mjs";
import { createDashboardService } from "./dashboard.mjs";
import { createMssqlAdapter } from "./db/mssql.mjs";
import { publicFormulaCatalog } from "./formulas/evaluate.mjs";
import { createKeyTaskStore } from "./key-tasks.mjs";

const adapter = createMssqlAdapter(config.database);
const dashboardService = createDashboardService({
  adapter,
  cacheOptions: config.cache,
  timezone: config.dashboard.timezone,
  refreshAfterMs: config.dashboard.refreshAfterMs,
});
const keyTaskStore = createKeyTaskStore();

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

function requestScope(request) {
  const encodedUser = String(request.headers["x-business-scope-user"] || "本地用户").trim();
  let userName = encodedUser;
  try {
    userName = decodeURIComponent(encodedUser);
  } catch {
    // Invalid percent encoding is normalized by the task service below.
  }
  return {
    role: String(request.headers["x-business-scope-role"] || "ratio_viewer").trim(),
    department: String(request.headers["x-business-scope-department"] || "").trim(),
    userName,
  };
}

async function parseJsonBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 2 * 1024 * 1024) {
      const error = badRequest("Request body is too large");
      error.status = 413;
      error.code = "PAYLOAD_TOO_LARGE";
      throw error;
    }
    chunks.push(chunk);
  }
  if (!chunks.length) throw badRequest("JSON body is required");
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw badRequest("Request body must be valid JSON");
  }
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
  const url = new URL(request.url || "/", `http://${config.api.host}:${config.api.port}`);
  if (url.pathname === "/api/health") {
    if (request.method !== "GET") {
      json(response, 405, { error: { code: "METHOD_NOT_ALLOWED", message: "Only GET is supported" } });
      return;
    }
    const database = await adapter.health();
    const newest = dashboardService.newestCache();
    json(response, 200, {
      service: "ok",
      database,
      lastSuccessAt: dashboardService.lastSuccessAt(),
      cacheAgeMs: newest?.ageMs ?? null,
      storeTierRefresh: dashboardService.tierRefreshStatus(),
    });
    return;
  }
  if (url.pathname === "/api/dashboard") {
    if (request.method !== "GET") {
      json(response, 405, { error: { code: "METHOD_NOT_ALLOWED", message: "Only GET is supported" } });
      return;
    }
    const input = parseDashboardRequest(url);
    json(response, 200, await dashboardService.dashboard(input, config.database.configured));
    return;
  }
  if (url.pathname === "/api/formulas") {
    if (request.method !== "GET") {
      json(response, 405, { error: { code: "METHOD_NOT_ALLOWED", message: "Only GET is supported" } });
      return;
    }
    json(response, 200, { formulas: publicFormulaCatalog() });
    return;
  }
  const keyTaskMatch = url.pathname.match(/^\/api\/key-tasks(?:\/([^/]+))?$/);
  if (keyTaskMatch) {
    const id = keyTaskMatch[1] ? decodeURIComponent(keyTaskMatch[1]) : "";
    const scope = requestScope(request);
    if (request.method === "GET" && !id) {
      json(response, 200, await keyTaskStore.list(scope));
      return;
    }
    if (request.method === "POST" && !id) {
      json(response, 201, await keyTaskStore.create(await parseJsonBody(request), scope));
      return;
    }
    if (request.method === "PUT" && id) {
      json(response, 200, { task: await keyTaskStore.update(id, await parseJsonBody(request), scope) });
      return;
    }
    if (request.method === "DELETE" && id) {
      json(response, 200, { removed: await keyTaskStore.remove(id, scope) });
      return;
    }
    json(response, 405, { error: { code: "METHOD_NOT_ALLOWED", message: "Method is not supported" } });
    return;
  }
  json(response, 404, { error: { code: "NOT_FOUND", message: "Route not found" } });
}

const server = http.createServer((request, response) => {
  route(request, response).catch((error) => {
    const status = Number.isInteger(error?.status) && error.status >= 400 && error.status < 600
      ? error.status
      : 500;
    const code = status < 500 ? error.code : "INTERNAL_ERROR";
    if (status === 500) console.warn(`[sales-api] ${code}`);
    json(response, status, { error: { code, message: status < 500 ? error.message : "Request failed" } });
  });
});

server.listen(config.api.port, config.api.host, () => {
  console.log(`[sales-api] listening on http://${config.api.host}:${config.api.port}`);
  // Keep the store-tier partition warm across the Asia/Shanghai day boundary.
  // The dashboard request path also keys the cache by local date, so a missed
  // timer still refreshes safely on the next poll.
  dashboardService.startDailyRefresh(config.database.configured);
});

let closing = false;
async function shutdown() {
  if (closing) return;
  closing = true;
  dashboardService.stopDailyRefresh();
  server.close();
  await adapter.close();
}

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
