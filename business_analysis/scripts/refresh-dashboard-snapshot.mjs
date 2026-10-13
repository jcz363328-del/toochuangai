import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { config } from "../server/config.mjs";
import { createDashboardService } from "../server/dashboard.mjs";
import { createMssqlAdapter } from "../server/db/mssql.mjs";
import { localDateKey } from "../server/store-tiers.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputPath = path.join(root, "data", "dashboard-snapshot.json");
const temporaryPath = `${outputPath}.${process.pid}.tmp`;
const period = localDateKey(config.dashboard.timezone).slice(0, 7);
const adapter = createMssqlAdapter({
  ...config.database,
  requestTimeoutMs: Math.max(config.database.requestTimeoutMs, 120_000),
});
const service = createDashboardService({
  adapter,
  cacheOptions: config.cache,
  timezone: config.dashboard.timezone,
  refreshAfterMs: 86_400_000,
});

try {
  if (!config.database.configured) throw new Error("DB_NOT_CONFIGURED");
  const envelope = await service.dashboard({
    period,
    basis: "auto",
    department: null,
    operator: null,
    store: null,
    force: true,
  }, true);
  const failed = Object.entries(envelope.sources || {})
    .filter(([, source]) => source?.mode !== "database" || source?.stale)
    .map(([name, source]) => `${name}:${source?.warning || source?.mode || "unknown"}`);
  if (failed.length) throw new Error(`SNAPSHOT_SOURCE_FAILED ${failed.join(",")}`);

  const generatedAt = new Date().toISOString();
  const snapshot = {
    schemaVersion: 1,
    period,
    generatedAt,
    envelope: {
      ...envelope,
      source: {
        ...envelope.source,
        mode: "daily-snapshot",
        stale: false,
        fetchedAt: generatedAt,
        lastSuccessAt: generatedAt,
        warning: null,
      },
      refreshAfterMs: 86_400_000,
    },
  };
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(temporaryPath, `${JSON.stringify(snapshot)}\n`, "utf8");
  await fs.rename(temporaryPath, outputPath);
  console.log(JSON.stringify({
    period,
    generatedAt,
    cachePath: outputPath,
    stores: envelope.data?.performance?.stores?.length || 0,
    storeTiers: envelope.data?.storeTiers?.length || 0,
  }));
} catch (error) {
  await fs.rm(temporaryPath, { force: true }).catch(() => {});
  throw error;
} finally {
  await adapter.close();
}
