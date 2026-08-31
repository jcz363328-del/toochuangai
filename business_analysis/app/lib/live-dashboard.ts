import type { WorkbookData } from "./dashboard";

export type LivePhase = "live" | "refreshing" | "degraded";
export type LiveSourceMode = "database" | "memory-cache" | "workbook-snapshot";
export type LiveDatabaseStatus = "up" | "down" | "unknown";

export interface LiveDatabaseSource {
  configured: boolean;
  status: LiveDatabaseStatus;
  latencyMs: number | null;
}

export interface LiveDashboardSource {
  mode: LiveSourceMode;
  stale: boolean;
  fetchedAt: string;
  lastSuccessAt: string | null;
  latencyMs: number | null;
  warning: string | null;
  database: LiveDatabaseSource;
}

export interface FormulaTraceInput {
  key: string;
  label: string;
  value: number | null;
  source: string;
}

export interface FormulaTrace {
  id: string;
  label: string;
  expression: string;
  value: number | null;
  unit: "CNY" | "count" | "ratio";
  status: "ok" | "missing-input" | "divide-by-zero" | "stale";
  inputs: FormulaTraceInput[];
  evaluatedAt: string;
}

export interface LiveDashboardEnvelope {
  data: WorkbookData;
  formulas: FormulaTrace[];
  source: LiveDashboardSource;
  refreshAfterMs: number;
}

export interface DashboardRequestOptions {
  force?: boolean;
  signal?: AbortSignal;
}

export class LiveDashboardError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(
    code: string,
    message: string,
    status: number | null = null,
  ) {
    super(message);
    this.name = "LiveDashboardError";
    this.code = code;
    this.status = status;
  }
}

const SOURCE_MODES = new Set<LiveSourceMode>([
  "database",
  "memory-cache",
  "workbook-snapshot",
]);
const DB_STATUSES = new Set<LiveDatabaseStatus>(["up", "down", "unknown"]);
const PERIOD_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const finiteOrNull = (value: unknown) =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const stringOrNull = (value: unknown) =>
  typeof value === "string" && value.length > 0 ? value : null;

const nowIso = () => new Date().toISOString();

function isWorkbookData(value: unknown): value is WorkbookData {
  return (
    isRecord(value) &&
    isRecord(value.meta) &&
    isRecord(value.performance) &&
    Array.isArray(value.slowMoving) &&
    Array.isArray(value.shipping)
  );
}

function normalizeDatabase(
  value: unknown,
  mode: LiveSourceMode,
): LiveDatabaseSource {
  const fallback: LiveDatabaseSource = {
    configured: mode !== "workbook-snapshot",
    status: mode === "database" ? "up" : "unknown",
    latencyMs: null,
  };

  if (typeof value === "string") {
    return {
      ...fallback,
      status: DB_STATUSES.has(value as LiveDatabaseStatus)
        ? (value as LiveDatabaseStatus)
        : "unknown",
    };
  }
  if (!isRecord(value)) return fallback;

  const status =
    typeof value.status === "string" &&
    DB_STATUSES.has(value.status as LiveDatabaseStatus)
      ? (value.status as LiveDatabaseStatus)
      : fallback.status;

  return {
    configured:
      typeof value.configured === "boolean"
        ? value.configured
        : fallback.configured,
    status,
    latencyMs: finiteOrNull(value.latencyMs),
  };
}

function normalizeSource(
  value: unknown,
  requestLatencyMs: number,
): LiveDashboardSource {
  const raw = isRecord(value) ? value : {};
  const mode =
    typeof raw.mode === "string" && SOURCE_MODES.has(raw.mode as LiveSourceMode)
      ? (raw.mode as LiveSourceMode)
      : "database";
  const fetchedAt = stringOrNull(raw.fetchedAt) ?? nowIso();

  return {
    mode,
    stale: raw.stale === true,
    fetchedAt,
    lastSuccessAt:
      stringOrNull(raw.lastSuccessAt) ?? (mode === "database" ? fetchedAt : null),
    latencyMs: finiteOrNull(raw.latencyMs) ?? requestLatencyMs,
    warning: stringOrNull(raw.warning),
    database: normalizeDatabase(raw.database, mode),
  };
}

function normalizeFormulas(value: unknown): FormulaTrace[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is FormulaTrace => {
    if (!isRecord(item) || !Array.isArray(item.inputs)) return false;
    return (
      typeof item.id === "string" &&
      typeof item.label === "string" &&
      typeof item.expression === "string" &&
      typeof item.evaluatedAt === "string"
    );
  });
}

function errorDetails(payload: unknown, status: number) {
  const root = isRecord(payload) ? payload : {};
  const nested = isRecord(root.error) ? root.error : null;
  const code =
    stringOrNull(nested?.code) ??
    stringOrNull(root.code) ??
    `HTTP_${status}`;
  const message =
    stringOrNull(nested?.message) ??
    (typeof root.error === "string" ? root.error : null) ??
    stringOrNull(root.message) ??
    `数据接口请求失败（HTTP ${status}）`;
  return { code, message };
}

export function createWorkbookSnapshotSource(
  data: WorkbookData,
): LiveDashboardSource {
  return {
    mode: "workbook-snapshot",
    stale: true,
    fetchedAt: data.meta.extractedAt || nowIso(),
    lastSuccessAt: null,
    latencyMs: null,
    warning: "当前显示 Excel 快照，等待数据库数据",
    database: { configured: false, status: "unknown", latencyMs: null },
  };
}

export function normalizeLiveDashboardEnvelope(
  payload: unknown,
  requestLatencyMs = 0,
): LiveDashboardEnvelope {
  const root = isRecord(payload) ? payload : null;
  const envelope = root && isRecord(root.result) ? root.result : root;
  const directData = isWorkbookData(envelope) ? envelope : null;
  const data = directData ?? (envelope && isWorkbookData(envelope.data) ? envelope.data : null);

  if (!data) {
    throw new LiveDashboardError(
      "INVALID_RESPONSE",
      "数据服务返回了无法识别的内容",
    );
  }

  return {
    data,
    formulas: directData ? [] : normalizeFormulas(envelope?.formulas),
    source: directData
      ? normalizeSource({ mode: "database" }, requestLatencyMs)
      : normalizeSource(envelope?.source, requestLatencyMs),
    refreshAfterMs:
      (directData ? null : finiteOrNull(envelope?.refreshAfterMs)) ?? 60_000,
  };
}

export async function fetchLiveDashboard(
  period: string,
  options: DashboardRequestOptions = {},
): Promise<LiveDashboardEnvelope> {
  if (!PERIOD_PATTERN.test(period)) {
    throw new LiveDashboardError("INVALID_PERIOD", "月份必须使用 YYYY-MM 格式");
  }

  const query = new URLSearchParams({ period });
  if (options.force) query.set("force", "1");
  const dashboardApi =
    globalThis.document?.documentElement.dataset.dashboardApi ||
    "/api/dashboard";
  const startedAt = globalThis.performance?.now() ?? Date.now();
  let response: Response;

  try {
    response = await fetch(`${dashboardApi}?${query.toString()}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new LiveDashboardError("NETWORK_ERROR", "无法连接本地数据服务");
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) {
      throw new LiveDashboardError(
        "INVALID_RESPONSE",
        "数据服务未返回有效 JSON",
        response.status,
      );
    }
  }

  if (!response.ok) {
    const details = errorDetails(payload, response.status);
    throw new LiveDashboardError(details.code, details.message, response.status);
  }

  const endedAt = globalThis.performance?.now() ?? Date.now();
  return normalizeLiveDashboardEnvelope(payload, Math.round(endedAt - startedAt));
}

export function liveErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "实时数据刷新失败";
}
