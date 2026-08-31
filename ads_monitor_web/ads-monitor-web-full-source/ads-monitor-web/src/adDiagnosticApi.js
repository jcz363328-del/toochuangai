import { PILOT_SHOP } from "./adDiagnosticModel.js";

const APP_BASE_URL = import.meta.env?.BASE_URL || "/";
export const DIAGNOSTIC_ENDPOINT = APP_BASE_URL.startsWith("/ai/ads-monitor/")
  ? "/api/ads-monitor/diagnostic"
  : "/api/diagnostic";

export function buildDiagnosticShopsUrl() {
  return `${DIAGNOSTIC_ENDPOINT}/shops`;
}

export function buildDiagnosticUrl({ shopId = PILOT_SHOP.id, campaignId, refresh = false, section } = {}) {
  const params = new URLSearchParams({ shop_id: String(shopId) });
  if (campaignId) params.set("campaign_id", String(campaignId));
  if (refresh) params.set("refresh", "1");
  if (section) params.set("section", String(section));
  return `${DIAGNOSTIC_ENDPOINT}?${params.toString()}`;
}

export function buildSearchTermsUrl({ shopId = PILOT_SHOP.id, campaignId, kind, page = 1, pageSize = 10 } = {}) {
  const params = new URLSearchParams({
    shop_id: String(shopId),
    campaign_id: String(campaignId || ""),
    kind: String(kind || ""),
    page: String(page),
    page_size: String(pageSize),
  });
  return `${DIAGNOSTIC_ENDPOINT}/search-terms?${params.toString()}`;
}

export function buildSpControlCapabilitiesUrl({ shopId = PILOT_SHOP.id, campaignId, refresh = false } = {}) {
  const params = new URLSearchParams({
    shop_id: String(shopId),
    campaign_id: String(campaignId || ""),
  });
  if (refresh) params.set("refresh", "1");
  return `${DIAGNOSTIC_ENDPOINT}/sp-controls/capabilities?${params.toString()}`;
}

export class DiagnosticApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.name = "DiagnosticApiError";
    this.status = status;
  }
}

export async function fetchDiagnostic(options = {}) {
  const response = await fetch(buildDiagnosticUrl(options), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: options.signal,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("json") ? await response.json() : null;
  if (!response.ok) {
    const detail = payload?.error?.message || payload?.message || (typeof payload?.error === "string" ? payload.error : null) || `HTTP ${response.status}`;
    throw new DiagnosticApiError(`赛狐诊断接口读取失败：${detail}`, response.status);
  }
  if (!payload || typeof payload !== "object") {
    throw new DiagnosticApiError("赛狐诊断接口未返回 JSON 数据。", response.status);
  }
  return payload;
}

export async function fetchDiagnosticShops(options = {}) {
  const response = await fetch(buildDiagnosticShopsUrl(), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: options.signal,
  });
  return parseResponse(response, "诊断店铺清单读取失败");
}

export async function fetchSearchTermsPage(options = {}) {
  const response = await fetch(buildSearchTermsUrl(options), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: options.signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || typeof payload !== "object") {
    const detail = payload?.error?.message || payload?.message || `HTTP ${response.status}`;
    throw new DiagnosticApiError(`搜索词分页读取失败：${detail}`, response.status);
  }
  return payload;
}

async function parseResponse(response, prefix) {
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || typeof payload !== "object") {
    const detail = payload?.error?.message || payload?.message || `HTTP ${response.status}`;
    throw new DiagnosticApiError(`${prefix}：${detail}`, response.status);
  }
  return payload;
}

export async function fetchSpControlCapabilities(options = {}) {
  const response = await fetch(buildSpControlCapabilitiesUrl(options), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal: options.signal,
  });
  return parseResponse(response, "SP调控能力读取失败");
}

async function postSpControl(action, payload, controlToken, signal) {
  const response = await fetch(`${DIAGNOSTIC_ENDPOINT}/sp-controls/${action}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-SP-Control-Token": controlToken,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
    signal,
  });
  return parseResponse(response, action === "preview" ? "SP调控预览失败" : "SP调控执行失败");
}

export const previewSpControl = (payload, controlToken, signal) => postSpControl("preview", payload, controlToken, signal);
export const executeSpControl = (payload, controlToken, signal) => postSpControl("execute", payload, controlToken, signal);
