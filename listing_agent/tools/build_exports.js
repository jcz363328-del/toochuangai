const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const DATA_DIR = path.join(ROOT, "data");
const OUTPUT_DIR = path.join(ROOT, "outputs");
const CODE_DIR = path.join(ROOT, "code");
const DASHBOARD_NAME = "ABA四核心词综合排名看板_2026-06-28~2026-07-04.html";

const source = fs.readFileSync(path.join(DATA_DIR, DASHBOARD_NAME), "utf8");
const dashboardData = extractDashboardData(source);
const rows = (dashboardData.rows || []).map(mapDashboardRow).filter(Boolean);

fs.writeFileSync(
  path.join(DATA_DIR, "aba-ranking-export.json"),
  JSON.stringify({ meta: dashboardData.meta || {}, rows }, null, 2),
  "utf8"
);

const csvColumns = [
  "marketplace",
  "searchTerm",
  "searchFrequencyRank",
  "previousSearchFrequencyRank",
  "rankMoM",
  "rankYoY",
  "top3AsinClickShare",
  "top3AsinConversionShare",
  "top3AsinList",
  "topBrands"
];
const csv = [
  csvColumns.join(","),
  ...rows.map((row) => csvColumns.map((column) => csvCell(
    Array.isArray(row[column]) ? row[column].join("|") : row[column]
  )).join(","))
].join("\n");
fs.writeFileSync(path.join(DATA_DIR, "aba-ranking-export.csv"), csv, "utf8");

const snapshot = {
  rows,
  request: { dateRange: "2026-06-28 至 2026-07-04" },
  summary: { rawRows: rows.length },
  fetchedAt: new Date().toISOString(),
  source: DASHBOARD_NAME
};
const sampleData = {
  marketplace: "US",
  brandName: "ALICE",
  productType: "lash clusters",
  styleAngle: "natural wispy",
  lengths: "10mm/11mm/12mm/13mm/14mm",
  curl: "D Curl",
  bandType: "clear band",
  pieceCount: "120pcs",
  contents: ["lash tray", "bond", "seal", "applicator"],
  verifiedClaims: [],
  imageFacts: "Packaging shows 10/12/14mm, D Curl and clear band. Tray appears to include 120pcs.",
  imageExtractionConfirmed: true,
  imageExtractionNeeds: [],
  t1Keywords: ["lash clusters", "cluster lashes", "eyelash clusters"],
  t2Keywords: ["beginner friendly", "easy to apply", "anti lift", "natural look"],
  t3Keywords: ["office", "date", "vacation", "clean girl makeup", "soft glam"],
  abaRankings: rows
    .filter((row) => row.searchFrequencyRank <= 30000)
    .sort((a, b) => a.searchFrequencyRank - b.searchFrequencyRank)
    .slice(0, 12)
    .map((row) => `#${row.searchFrequencyRank} ${row.searchTerm}`)
    .join("; "),
  forbiddenRankings: "High risk: waterproof, hypoallergenic, latex-free, 24-hour. Medium risk: reusable.",
  mcpSummary: "ABA ranking, growth, click share and conversion share are supplied by the bundled dashboard export.",
  competitorNotes: "Review themes include lifting corners, poking, visible bands and difficult placement.",
  sellfoxSnapshot: snapshot
};

const sandbox = {
  console,
  TextEncoder,
  Blob,
  URL,
  setTimeout,
  clearTimeout,
  fetch: async () => { throw new Error("Network calls are disabled in export mode."); },
  navigator: {},
  localStorage: { getItem: () => null, setItem: () => {} },
  window: { location: { protocol: "file:" } },
  document: {
    addEventListener: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => ({}),
    body: { appendChild: () => {}, removeChild: () => {} }
  }
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(CODE_DIR, "app.js"), "utf8"), sandbox);
const result = vm.runInContext(
  `generateListing(${JSON.stringify(sampleData)}, DEFAULT_SKILL)`,
  sandbox
);

fs.writeFileSync(
  path.join(OUTPUT_DIR, "示例Listing_三版.json"),
  JSON.stringify(result, null, 2),
  "utf8"
);
fs.writeFileSync(
  path.join(OUTPUT_DIR, "示例Listing_三版.md"),
  renderListingMarkdown(result),
  "utf8"
);

console.log(`Exported ${rows.length} ABA rows and ${result.variants.length} listing variants.`);

function extractDashboardData(html) {
  const marker = "const DATA =";
  const markerIndex = html.indexOf(marker);
  if (markerIndex === -1) throw new Error("Dashboard DATA block was not found.");
  const start = html.indexOf("{", markerIndex + marker.length);
  return JSON.parse(extractBalancedJson(html, start));
}

function extractBalancedJson(text, start) {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') inString = false;
      continue;
    }
    if (char === '"') inString = true;
    else if (char === "{") depth += 1;
    else if (char === "}") {
      depth -= 1;
      if (depth === 0) return text.slice(start, index + 1);
    }
  }
  throw new Error("Dashboard DATA block is incomplete.");
}

function mapDashboardRow(row) {
  if (!Array.isArray(row) || !row[1] || !Number.isFinite(Number(row[2]))) return null;
  const rank = Number(row[2]);
  const mom = Number(row[3]);
  const previousRank = Number.isFinite(mom) && mom < 1
    ? Math.max(1, Math.round(rank / (1 - mom)))
    : null;
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
    topBrands: [row[11], row[18], row[25]].map(clean).filter(Boolean)
  };
}

function renderListingMarkdown(result) {
  return result.variants.map((variant) => [
    `# ${variant.name}`,
    "",
    `推荐分：${variant.score}/100`,
    "",
    "## Title",
    "",
    variant.title,
    "",
    "## Highlights",
    "",
    ...variant.highlights.map((item) => `- ${item}`),
    "",
    "## Bullets",
    "",
    ...variant.bullets.map((item, index) => `${index + 1}. ${item}`),
    "",
    "## Description",
    "",
    variant.description,
    "",
    "## Search Terms",
    "",
    variant.searchTerms,
    "",
    "## Compliance Check",
    "",
    ...variant.selfCheck.map((item) => `- ${item.status.toUpperCase()}: ${item.text}`),
    ""
  ].join("\n")).join("\n---\n\n");
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function clean(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}
