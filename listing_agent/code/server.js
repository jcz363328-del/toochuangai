const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const ROOT_PREFIX = ROOT.endsWith(path.sep) ? ROOT : `${ROOT}${path.sep}`;
loadLocalEnv(".env");
loadLocalEnv(".env.local");

const HOST = process.env.HOST || "127.0.0.1";
const PORT = Number(process.env.PORT || 5177);
const DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1";
const DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3-VL-8B-Instruct";
const DEFAULT_SELLFOX_DASHBOARD_URL = "http://127.0.0.1:8765";
const DEFAULT_SELLFOX_RANKING_FILE = path.resolve(
  ROOT,
  "..",
  "data",
  "ABA四核心词综合排名看板_2026-06-28~2026-07-04.html"
);
const VISION_MODEL_FALLBACKS = [
  DEFAULT_SILICONFLOW_MODEL,
  "Qwen/Qwen3-VL-32B-Instruct",
  "Qwen/Qwen3-VL-30B-A3B-Instruct",
  "zai-org/GLM-4.5V"
];
const MAX_BODY_BYTES = 26 * 1024 * 1024;

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".svg": "image/svg+xml"
};
const PUBLIC_FILES = new Set(["/index.html", "/app.js", "/styles.css"]);

const DO_NOT_INFER = [
  "不要仅凭图片推断材质、成分、低敏、无乳胶、防水、佩戴时长、可复用次数、无刺激、无残留或敏感眼可用等声明。",
  "胶水、封层、卸除液、镊子/夹子等侧边道具，不能默认视为包含物；必须由包装、SKU 数据或用户确认。",
  "包装印刷文字和托盘标签的证据等级高于视觉风格猜测。"
];

const EXTRACTION_PROMPT = `你是 Amazon 假睫毛产品图片事实提取助手。

请只提取图片中可见的事实，并按以下证据等级判断：
1. 包装印刷文字和托盘标签。
2. 清楚可见的产品内容物。
3. 只能对风格词做视觉推断，例如 wispy、natural、spiky、manga、bunny eye、cat eye、doll eye、soft glam。

只返回严格 JSON，不要输出 Markdown 或解释。JSON 字段名保持英文，字段值尽量使用中文：
{
  "facts": [
    {
      "key": "brandName | productType | lengths | curl | pieceCount | bandType | styleAngle | contents | packageText | rowCount | clustersPerRow | lengthBreakdown",
      "label": "简短中文标签",
      "value": "图片中可见的值",
      "source": "包装文字 | 托盘标签 | 可见内容物 | 视觉推断",
      "confidence": "high | medium | low"
    }
  ],
  "needsConfirmation": [
    "需要人工确认的中文短句"
  ],
  "doNotInfer": [
    "禁止仅凭图片推断的中文短句"
  ]
}

规则：
- 如果根数只是根据可见行数估算，value 必须写“图片可见估算”，confidence 用 medium 或 low。
- 如果长度或卷度看不清，不要猜，放入 needsConfirmation。
- 如果品牌、包装完整文字或包含工具不清楚，放入 needsConfirmation。
- 每个可见内容物单独输出一个 fact，key 使用 "contents"。
- 不要输出代码块、Markdown 或 JSON 之外的内容。`;

const server = http.createServer(async (req, res) => {
  try {
    if ((req.method === "GET" || req.method === "HEAD") && req.url === "/api/health") {
      sendJson(res, 200, {
        ok: true,
        model: getSiliconFlowModel(),
        hasApiKey: Boolean(process.env.SILICONFLOW_API_KEY)
      }, req.method === "HEAD");
      return;
    }

    if (req.url === "/api/settings") {
      if (req.method === "GET" || req.method === "HEAD") {
        sendJson(res, 200, getPublicSettings(), req.method === "HEAD");
        return;
      }
      if (req.method === "POST") {
        await handleSaveSettings(req, res);
        return;
      }
    }

    if (req.method === "POST" && req.url === "/api/extract-image") {
      await handleExtractImage(req, res);
      return;
    }

    if (req.method === "POST" && req.url === "/api/generate-listings") {
      await handleGenerateListings(req, res);
      return;
    }

    if (req.url.startsWith("/api/sellfox/")) {
      if ((req.method === "GET" || req.method === "HEAD") && req.url === "/api/sellfox/ranking-file") {
        handleSellfoxRankingFile(res, req.method === "HEAD");
        return;
      }
      await handleSellfoxProxy(req, res);
      return;
    }

    if (req.method === "GET" || req.method === "HEAD") {
      serveStatic(req, res);
      return;
    }

    sendJson(res, 405, { error: "Method not allowed" });
  } catch (error) {
    sendJson(res, 500, { error: error.message || "Server error" });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Listing Agent Studio running at http://${HOST}:${PORT}`);
  console.log(`Vision model: ${getSiliconFlowModel()}`);
});

server.on("error", (error) => {
  console.error(`Failed to start local server: ${error.message}`);
  process.exit(1);
});

async function handleExtractImage(req, res) {
  const apiKey = process.env.SILICONFLOW_API_KEY;
  if (!apiKey) {
    sendJson(res, 500, {
      error: "SILICONFLOW_API_KEY is not set. Start the server with your SiliconFlow key in the environment."
    });
    return;
  }

  const payload = await readJsonBody(req);
  const images = Array.isArray(payload.images) ? payload.images.slice(0, 4) : [];
  const validImages = images
    .map((image) => ({
      name: String(image.name || "uploaded-image"),
      type: String(image.type || ""),
      dataUrl: String(image.dataUrl || "")
    }))
    .filter((image) => image.dataUrl.startsWith("data:image/"));

  if (!validImages.length) {
    sendJson(res, 400, { error: "No valid image dataUrl values were provided." });
    return;
  }

  const modelPayload = {
    messages: [
      {
        role: "user",
        content: [
          {
            type: "text",
            text: [
              EXTRACTION_PROMPT,
              "",
              `Marketplace: ${payload.marketplace || "US"}`,
              `Selected category: ${payload.category || "false eyelashes"}`,
              `Image filenames: ${validImages.map((image) => image.name).join(", ")}`
            ].join("\n")
          },
          ...validImages.map((image) => ({
            type: "image_url",
            image_url: {
              url: image.dataUrl
            }
          }))
        ]
      }
    ],
    temperature: 0.1,
    max_tokens: 1400
  };

  const result = await callSiliconFlowWithFallbacks(apiKey, modelPayload);
  if (!result.ok) {
    const reason = result.error || {};
    sendJson(res, 502, {
      error: "SiliconFlow request failed",
      siliconFlowStatus: result.status,
      siliconFlowCode: reason.code || "",
      siliconFlowMessage: reason.message || safeDetail(result.text || ""),
      model: result.model || getSiliconFlowModel()
    });
    return;
  }

  const completion = JSON.parse(result.text);
  const content = completion?.choices?.[0]?.message?.content || "";
  const parsed = parseJsonFromText(content);
  if (!parsed) {
    sendJson(res, 200, {
      facts: [],
      needsConfirmation: [
        "视觉模型已返回内容，但无法解析为 JSON。请手动填写图片可见事实。"
      ],
      doNotInfer: DO_NOT_INFER,
      source: `SiliconFlow ${result.model} returned unparsed text.`
    });
    return;
  }

  sendJson(res, 200, {
    facts: normalizeFacts(parsed.facts),
    needsConfirmation: normalizeStrings(parsed.needsConfirmation || parsed.needs),
    doNotInfer: normalizeStrings(parsed.doNotInfer || parsed.blocked).concat(DO_NOT_INFER),
    source: `SiliconFlow ${result.model}`
  });
}

async function handleGenerateListings(req, res) {
  const apiKey = process.env.SILICONFLOW_API_KEY;
  if (!apiKey) {
    sendJson(res, 500, { error: "SILICONFLOW_API_KEY is not set. Configure it before generating AI listings." });
    return;
  }

  const input = await readJsonBody(req);
  const promptPayload = normalizeListingGenerationInput(input);
  if (!promptPayload.product?.type) {
    sendJson(res, 400, { error: "Confirmed product facts are required before generating listings." });
    return;
  }

  const modelPayload = {
    model: getSiliconFlowTextModel(),
    temperature: 0.65,
    max_tokens: 6200,
    messages: [
      {
        role: "system",
        content: `You are an Amazon listing copywriter for beauty products. Write compliant, specific English listing copy from confirmed product facts only. Never invent materials, certifications, safety claims, wear time, waterproof performance, reusable count, package contents, or medical claims. Never use any forbidden term supplied by the user. Respect title, bullet, description and backend-search-term limits. Return strict JSON only, with this shape:
{
  "variants": [
    {
      "id": "balanced | style | search",
      "title": "string",
      "highlights": ["string", "string", "string"],
      "bullets": ["string", "string", "string", "string", "string"],
      "description": "string",
      "searchTerms": "string",
      "reasons": ["short Chinese explanation", "short Chinese explanation"]
    }
  ]
}
Return exactly three variants: balanced, style, search. The copy fields must be English. Reasons must be Chinese. Do not use markdown.`
      },
      {
        role: "user",
        content: JSON.stringify(promptPayload)
      }
    ]
  };

  const result = await callSiliconFlow(apiKey, modelPayload);
  if (!result.ok) {
    const reason = result.error || {};
    sendJson(res, 502, {
      error: "SiliconFlow text generation failed",
      siliconFlowStatus: result.status,
      siliconFlowCode: reason.code || "",
      siliconFlowMessage: reason.message || safeDetail(result.text || ""),
      model: result.model
    });
    return;
  }

  const completion = parseJsonFromText(result.text);
  const content = completion?.choices?.[0]?.message?.content || "";
  const parsed = parseJsonFromText(content);
  const variants = normalizeGeneratedListingVariants(parsed?.variants);
  if (variants.length !== 3) {
    sendJson(res, 502, {
      error: "SiliconFlow returned an incomplete listing payload.",
      model: result.model,
      detail: safeDetail(content)
    });
    return;
  }

  sendJson(res, 200, { ok: true, model: result.model, variants });
}

function normalizeListingGenerationInput(input) {
  const data = input && typeof input === "object" ? input : {};
  const list = (items, max = 12) => Array.isArray(items) ? items.map((item) => clean(item)).filter(Boolean).slice(0, max) : [];
  const terms = (items) => list(items, 10).map((item) => ({
    term: clean(item.term),
    rank: Number.isFinite(Number(item.rank)) ? Number(item.rank) : null,
    growth: Number.isFinite(Number(item.growth)) ? Number(item.growth) : null,
    clickShare: Number.isFinite(Number(item.clickShare)) ? Number(item.clickShare) : null,
    conversionShare: Number.isFinite(Number(item.conversionShare)) ? Number(item.conversionShare) : null
  })).filter((item) => item.term);
  const product = data.product && typeof data.product === "object" ? data.product : {};
  const skill = data.skill && typeof data.skill === "object" ? data.skill : {};
  const limits = data.limits && typeof data.limits === "object" ? data.limits : {};

  return {
    marketplace: clean(data.marketplace) || "US",
    product: {
      brand: clean(product.brand),
      type: clean(product.type),
      style: clean(product.style),
      lengths: clean(product.lengths),
      curl: clean(product.curl),
      bandType: clean(product.bandType),
      pieceCount: clean(product.pieceCount),
      contents: list(product.contents, 8),
      verifiedClaims: list(product.verifiedClaims, 8),
      imageFacts: clean(product.imageFacts).slice(0, 2400),
      needsConfirmation: list(product.needsConfirmation, 8)
    },
    keywords: {
      t1: list(data.keywords?.t1, 10),
      t2: list(data.keywords?.t2, 10),
      t3: list(data.keywords?.t3, 10),
      rankingPriority: terms(data.keywords?.rankingPriority),
      growthPriority: terms(data.keywords?.growthPriority),
      conversionPriority: terms(data.keywords?.conversionPriority),
      backendPriority: terms(data.keywords?.backendPriority)
    },
    compliance: {
      forbiddenTerms: list(data.compliance?.forbiddenTerms, 80),
      customRules: clean(data.compliance?.customRules).slice(0, 3000)
    },
    skill: {
      name: clean(skill.name),
      titleStrategy: clean(skill.titleStrategy),
      tone: clean(skill.tone),
      bulletPattern: clean(skill.bulletPattern),
      learnedRules: list(skill.learnedRules, 12),
      historicalReference: clean(skill.historicalReference).slice(0, 5000)
    },
    limits: {
      title: Math.min(Math.max(Number(limits.title) || 75, 30), 200),
      bullet: Math.min(Math.max(Number(limits.bullet) || 500, 100), 1000),
      description: Math.min(Math.max(Number(limits.description) || 2000, 300), 4000),
      searchTermsBytes: Math.min(Math.max(Number(limits.searchTermsBytes) || 249, 80), 500)
    },
    variants: Array.isArray(data.variants)
      ? data.variants.slice(0, 3).map((variant) => ({
          id: clean(variant?.id),
          name: clean(variant?.name),
          direction: clean(variant?.direction)
        })).filter((variant) => variant.id)
      : []
  };
}

function normalizeGeneratedListingVariants(variants) {
  const expectedIds = ["balanced", "style", "search"];
  const source = Array.isArray(variants) ? variants : [];
  const normalized = source.map((variant, index) => {
    const value = variant && typeof variant === "object" ? variant : {};
    const id = expectedIds.includes(clean(value.id)) ? clean(value.id) : expectedIds[index];
    return {
      id,
      title: clean(value.title),
      highlights: normalizeStrings(value.highlights).slice(0, 3),
      bullets: normalizeStrings(value.bullets).slice(0, 5),
      description: clean(value.description),
      searchTerms: clean(value.searchTerms),
      reasons: normalizeStrings(value.reasons).slice(0, 4)
    };
  }).filter((variant) => variant.id && variant.title && variant.highlights.length && variant.bullets.length && variant.description && variant.searchTerms);

  const byId = new Map(normalized.map((variant) => [variant.id, variant]));
  return expectedIds.map((id) => byId.get(id)).filter(Boolean);
}

async function handleSellfoxProxy(req, res) {
  const requestUrl = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  const pathName = requestUrl.pathname;
  const dashboardPath = getSellfoxDashboardPath(pathName);

  if (!dashboardPath) {
    sendJson(res, 404, { error: "Unknown Sellfox integration endpoint." });
    return;
  }

  try {
    const targetUrl = new URL(dashboardPath, `${getSellfoxDashboardUrl()}/`);
    if (requestUrl.search) targetUrl.search = requestUrl.search;
    const isWrite = req.method === "POST";
    const payload = isWrite ? await readJsonBody(req) : undefined;
    const response = await fetch(targetUrl, {
      method: req.method,
      headers: isWrite ? { "Content-Type": "application/json" } : undefined,
      body: isWrite ? JSON.stringify(payload) : undefined,
      signal: AbortSignal.timeout(30000)
    });
    const text = await response.text();
    const result = parseJsonFromText(text) || { ok: false, message: safeDetail(text) };
    sendJson(res, response.status, result, req.method === "HEAD");
  } catch (error) {
    sendJson(res, 502, {
      ok: false,
      message: `无法连接赛虎广告看板（${getSellfoxDashboardUrl()}）。请先启动它的本地服务。`,
      detail: safeDetail(error.message)
    });
  }
}

function handleSellfoxRankingFile(res, headOnly) {
  try {
    const sourcePath = getSellfoxRankingFile();
    const source = fs.readFileSync(sourcePath, "utf8");
    const dashboardData = extractDashboardData(source);
    const rows = Array.isArray(dashboardData.rows) ? dashboardData.rows.map(mapDashboardRow).filter(Boolean) : [];
    const stat = fs.statSync(sourcePath);
    sendJson(res, 200, {
      ok: true,
      source: path.basename(sourcePath),
      updatedAt: stat.mtime.toISOString(),
      meta: dashboardData.meta || {},
      summary: {
        rawRows: rows.length,
        uniqueTerms: dashboardData.meta?.uniqueTermCount || rows.length,
        top30000Count: dashboardData.meta?.top30000Count || 0
      },
      rows
    }, headOnly);
  } catch (error) {
    sendJson(res, 500, {
      ok: false,
      message: "无法读取已绑定的赛虎 ABA 看板文件。",
      detail: safeDetail(error.message)
    }, headOnly);
  }
}

function getSellfoxRankingFile() {
  return process.env.SELLFOX_RANKING_FILE || DEFAULT_SELLFOX_RANKING_FILE;
}

function extractDashboardData(source) {
  const marker = "const DATA =";
  const markerIndex = source.indexOf(marker);
  if (markerIndex === -1) throw new Error("看板中未找到 DATA 数据集。");
  const start = source.indexOf("{", markerIndex + marker.length);
  if (start === -1) throw new Error("看板 DATA 数据格式不完整。");
  const jsonText = extractBalancedJson(source, start);
  return JSON.parse(jsonText);
}

function extractBalancedJson(source, start) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < source.length; index += 1) {
    const char = source[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error("看板 DATA 数据未完整闭合。");
}

function mapDashboardRow(row) {
  if (!Array.isArray(row) || !row[1] || !Number.isFinite(Number(row[2]))) return null;
  const rank = Number(row[2]);
  const mom = Number(row[3]);
  const previousRank = Number.isFinite(mom) && mom < 1 ? Math.max(1, Math.round(rank / (1 - mom))) : null;
  return {
    marketplace: clean(row[0]),
    searchTerm: clean(row[1]),
    searchFrequencyRank: rank,
    previousSearchFrequencyRank: previousRank,
    rankMoM: Number.isFinite(mom) ? mom : null,
    rankYoY: Number.isFinite(Number(row[4])) ? Number(row[4]) : null,
    top3AsinClickShare: Number(row[5]) || 0,
    top3AsinConversionShare: Number(row[6]) || 0,
    top3AsinList: [row[7], row[14], row[21]].filter(Boolean),
    topBrands: [row[11], row[18], row[25]].map(clean).filter(Boolean),
    sourceMask: Number(row[29]) || 0,
    sourceCount: Number(row[30]) || 0
  };
}

function getSellfoxDashboardPath(pathName) {
  if (pathName === "/api/sellfox/status") return "/api/connectivity";
  if (pathName === "/api/sellfox/marketplaces") return "/api/marketplaces";
  if (pathName === "/api/sellfox/aba/jobs") return "/api/aba/top-keywords/jobs";
  if (/^\/api\/sellfox\/aba\/jobs\/[a-z0-9]+$/i.test(pathName)) {
    return pathName.replace(/^\/api\/sellfox\/aba\/jobs/, "/api/aba/top-keywords/jobs");
  }
  if (/^\/api\/sellfox\/aba\/jobs\/[a-z0-9]+\/cancel$/i.test(pathName)) {
    return pathName.replace(/^\/api\/sellfox\/aba\/jobs/, "/api/aba/top-keywords/jobs");
  }
  return "";
}

async function callSiliconFlowWithFallbacks(apiKey, modelPayload) {
  const models = uniqueModels([getSiliconFlowModel(), ...VISION_MODEL_FALLBACKS]);
  let lastResult = null;

  for (const model of models) {
    const result = await callSiliconFlow(apiKey, {
      ...modelPayload,
      model
    });
    lastResult = result;

    if (result.ok) return result;
    if (!isModelUnavailable(result)) return result;
  }

  return lastResult;
}

async function callSiliconFlow(apiKey, payload) {
  const response = await fetch(`${getSiliconFlowBaseUrl()}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    text,
    model: payload.model,
    error: parseJsonFromText(text)
  };
}

function isModelUnavailable(result) {
  const code = Number(result?.error?.code);
  const message = clean(result?.error?.message).toLowerCase();
  return code === 30003 || message.includes("model disabled") || message.includes("model not");
}

async function handleSaveSettings(req, res) {
  const payload = await readJsonBody(req);
  const apiKey = clean(payload.apiKey);
  const model = clean(payload.model) || DEFAULT_SILICONFLOW_MODEL;
  const textModel = clean(payload.textModel);

  if (apiKey) {
    process.env.SILICONFLOW_API_KEY = apiKey;
  }
  process.env.SILICONFLOW_MODEL = model;
  process.env.SILICONFLOW_TEXT_MODEL = textModel;

  if (!process.env.SILICONFLOW_API_KEY) {
    sendJson(res, 400, {
      error: "SILICONFLOW_API_KEY is required before image extraction can run."
    });
    return;
  }

  saveLocalSettings();
  sendJson(res, 200, getPublicSettings());
}

function serveStatic(req, res) {
  const requestPath = req.url === "/" ? "/index.html" : req.url.split("?")[0];
  const decoded = decodeURIComponent(requestPath);
  if (!PUBLIC_FILES.has(decoded)) {
    sendJson(res, 404, { error: "Not found" });
    return;
  }

  const filePath = path.normalize(path.join(ROOT, decoded));

  if (filePath !== ROOT && !filePath.startsWith(ROOT_PREFIX)) {
    sendJson(res, 403, { error: "Forbidden" });
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      sendJson(res, 404, { error: "Not found" });
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
      "Cache-Control": "no-store"
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    res.end(data);
  });
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    let body = "";
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("Request body is too large."));
        req.destroy();
        return;
      }
      body += chunk;
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch {
        reject(new Error("Invalid JSON request body."));
      }
    });
    req.on("error", reject);
  });
}

function parseJsonFromText(text) {
  const clean = String(text || "")
    .trim()
    .replace(/^```(?:json)?/i, "")
    .replace(/```$/i, "")
    .trim();

  try {
    return JSON.parse(clean);
  } catch {
    const start = clean.indexOf("{");
    const end = clean.lastIndexOf("}");
    if (start === -1 || end === -1 || end <= start) return null;
    try {
      return JSON.parse(clean.slice(start, end + 1));
    } catch {
      return null;
    }
  }
}

function normalizeFacts(facts) {
  if (!Array.isArray(facts)) return [];
  return facts
    .map((fact) => ({
      key: clean(fact.key),
      label: clean(fact.label || fact.key),
      value: clean(Array.isArray(fact.value) ? fact.value.join(", ") : fact.value),
      source: clean(fact.source || "vision model"),
      confidence: normalizeConfidence(fact.confidence)
    }))
    .filter((fact) => fact.key && fact.value);
}

function normalizeStrings(items) {
  if (!Array.isArray(items)) return [];
  return items.map(clean).filter(Boolean);
}

function uniqueModels(models) {
  return Array.from(new Set(models.map(clean).filter(Boolean)));
}

function normalizeConfidence(value) {
  const cleanValue = clean(value).toLowerCase();
  if (["high", "medium", "low"].includes(cleanValue)) return cleanValue;
  return "medium";
}

function clean(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function safeDetail(text) {
  return String(text || "").slice(0, 800);
}

function sendJson(res, status, payload, headOnly = false) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  if (headOnly) {
    res.end();
    return;
  }
  res.end(JSON.stringify(payload));
}

function loadLocalEnv(filename) {
  const envPath = path.join(ROOT, filename);
  if (!fs.existsSync(envPath)) return;

  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;

    const separator = trimmed.indexOf("=");
    if (separator === -1) return;

    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim().replace(/^['"]|['"]$/g, "");
    if (key && process.env[key] === undefined) {
      process.env[key] = value;
    }
  });
}

function getPublicSettings() {
  return {
    hasApiKey: Boolean(process.env.SILICONFLOW_API_KEY),
    model: getSiliconFlowModel(),
    textModel: getSiliconFlowTextModel()
  };
}

function getSiliconFlowBaseUrl() {
  return process.env.SILICONFLOW_BASE_URL || DEFAULT_SILICONFLOW_BASE_URL;
}

function getSiliconFlowModel() {
  return process.env.SILICONFLOW_MODEL || DEFAULT_SILICONFLOW_MODEL;
}

function getSiliconFlowTextModel() {
  return process.env.SILICONFLOW_TEXT_MODEL || getSiliconFlowModel();
}

function getSellfoxDashboardUrl() {
  return (process.env.SELLFOX_DASHBOARD_URL || DEFAULT_SELLFOX_DASHBOARD_URL).replace(/\/+$/, "");
}

function saveLocalSettings() {
  const lines = [
    `SILICONFLOW_API_KEY=${serializeEnvValue(process.env.SILICONFLOW_API_KEY || "")}`,
    `SILICONFLOW_MODEL=${serializeEnvValue(getSiliconFlowModel())}`,
    `SILICONFLOW_TEXT_MODEL=${serializeEnvValue(process.env.SILICONFLOW_TEXT_MODEL || "")}`,
    `PORT=${PORT}`
  ];
  fs.writeFileSync(path.join(ROOT, ".env.local"), `${lines.join("\n")}\n`, "utf8");
}

function serializeEnvValue(value) {
  return String(value || "").replace(/[\r\n]/g, "").trim();
}
