import { readFile, rename, writeFile } from "node:fs/promises";
import { config } from "../server/config.mjs";
import { DEPARTMENT_MAPPINGS } from "../server/departments.mjs";
import { createMssqlAdapter } from "../server/db/mssql.mjs";
import { buildQueryContext, queryCatalog, shiftPeriod } from "../server/queries/catalog.mjs";
import { shapeCategorySegments } from "../server/queries/shape-workbook.mjs";

const snapshotUrl = new URL("../app/data/workbook-data.json", import.meta.url);

function currentPeriod(timezone, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  return `${year}-${month}`;
}

function requestedPeriods() {
  const option = process.argv.find((argument) => argument.startsWith("--periods="));
  const periods = option
    ? option.slice("--periods=".length).split(",").map((period) => period.trim()).filter(Boolean)
    : Array.from(
      { length: 6 },
      (_, index) => shiftPeriod(currentPeriod(config.dashboard.timezone), index - 5),
    );
  if (!periods.length || periods.some((period) => !/^\d{4}-(0[1-9]|1[0-2])$/.test(period))) {
    throw new Error("--periods must be a comma-separated list of YYYY-MM values");
  }
  return [...new Set(periods)].sort();
}

function validate(period, categorySegments) {
  const expectedDepartments = DEPARTMENT_MAPPINGS.map((mapping) => mapping.display);
  if (categorySegments.categories.length !== 2) {
    throw new Error(`${period}: expected paired and cluster category snapshots`);
  }
  for (const category of categorySegments.categories) {
    const actual = category.departments.map((row) => row.department);
    if (JSON.stringify(actual) !== JSON.stringify(expectedDepartments)) {
      throw new Error(`${period}: department mapping is incomplete`);
    }
  }
}

if (!config.database.configured) throw new Error("SQL Server is not configured");

const periods = requestedPeriods();
const adapter = createMssqlAdapter(config.database);

try {
  const data = JSON.parse(await readFile(snapshotUrl, "utf8"));
  const snapshots = { ...(data.categorySegmentsByPeriod || {}) };

  for (const period of periods) {
    const context = buildQueryContext({
      period,
      basis: "full",
      department: null,
      operator: null,
      store: null,
    });
    const rows = await adapter.query(queryCatalog.categorySegments, context);
    const shaped = shapeCategorySegments(rows);
    validate(period, shaped);
    snapshots[period] = shaped;
    console.log(`[category-snapshot] ${period}: ${rows.length} rows`);
  }

  const capturedAt = new Date().toISOString();
  const defaultPeriod = data.performance.periods.find((period) => period.key === "current")?.label;
  const cachedPeriods = Object.keys(snapshots).sort();
  data.categorySegmentsByPeriod = snapshots;
  data.categorySegments = snapshots[defaultPeriod] || snapshots[periods.at(-1)];
  data.meta.categorySnapshot = {
    periods: cachedPeriods,
    capturedAt,
    source: "SQL Server category segment query",
    departmentMapping: Object.fromEntries(
      DEPARTMENT_MAPPINGS.map((mapping) => [mapping.source, mapping.display]),
    ),
  };
  data.meta.rowCounts.categorySegments = data.categorySegments.categories.length;
  data.meta.dateRanges.categorySegments = {
    start: `${shiftPeriod(cachedPeriods[0], -1)}-01`,
    end: `${shiftPeriod(cachedPeriods.at(-1), 1)}-01`,
  };

  const temporaryUrl = new URL(`${snapshotUrl.pathname}.tmp`, snapshotUrl);
  await writeFile(temporaryUrl, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  await rename(temporaryUrl, snapshotUrl);
  console.log(`[category-snapshot] wrote ${periods.length} periods to workbook-data.json`);
} finally {
  await adapter.close();
}
