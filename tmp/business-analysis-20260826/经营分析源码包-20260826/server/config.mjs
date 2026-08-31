import fs from "node:fs";

const envFile = new URL("../.env.local", import.meta.url);

if (fs.existsSync(envFile)) process.loadEnvFile(envFile);

function integer(name, fallback, minimum, maximum) {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(`${name} must be an integer from ${minimum} to ${maximum}`);
  }
  return value;
}

function boolean(name, fallback) {
  const raw = process.env[name]?.trim().toLowerCase();
  if (!raw) return fallback;
  if (["1", "true", "yes", "on"].includes(raw)) return true;
  if (["0", "false", "no", "off"].includes(raw)) return false;
  throw new Error(`${name} must be true or false`);
}

const driver = process.env.SALES_DB_DRIVER?.trim() || "mssql";
if (driver !== "mssql") throw new Error("SALES_DB_DRIVER must be mssql");

const apiHost = process.env.SALES_API_HOST?.trim() || "127.0.0.1";
if (apiHost !== "127.0.0.1") throw new Error("SALES_API_HOST must be 127.0.0.1");

const server = process.env.SALES_DB_SERVER?.trim() || "";
const database = process.env.SALES_DB_DATABASE?.trim() || "";
const user = process.env.SALES_DB_USER?.trim() || "";
const password = process.env.SALES_DB_PASSWORD || "";

export const config = Object.freeze({
  api: {
    host: apiHost,
    port: integer("SALES_API_PORT", 4311, 1024, 65535),
  },
  cache: {
    ttlMs: integer("SALES_CACHE_TTL_MS", 30_000, 1_000, 3_600_000),
    maxKeys: integer("SALES_CACHE_MAX_KEYS", 80, 8, 1_000),
  },
  dashboard: {
    refreshAfterMs: integer("SALES_POLL_INTERVAL_MS", 60_000, 5_000, 3_600_000),
    timezone: process.env.SALES_TIMEZONE?.trim() || "Asia/Shanghai",
  },
  database: {
    driver,
    configured: Boolean(server && database && user && password),
    server,
    port: integer("SALES_DB_PORT", 1433, 1, 65535),
    database,
    user,
    password,
    encrypt: boolean("SALES_DB_ENCRYPT", true),
    trustServerCertificate: boolean("SALES_DB_TRUST_SERVER_CERT", false),
    connectTimeoutMs: integer("SALES_DB_CONNECT_TIMEOUT_MS", 8_000, 1_000, 120_000),
    requestTimeoutMs: integer("SALES_DB_REQUEST_TIMEOUT_MS", 15_000, 1_000, 300_000),
    poolMin: integer("SALES_DB_POOL_MIN", 0, 0, 20),
    poolMax: integer("SALES_DB_POOL_MAX", 5, 1, 50),
  },
});

export function publicDatabaseConfig() {
  return { configured: config.database.configured, driver: config.database.driver };
}
