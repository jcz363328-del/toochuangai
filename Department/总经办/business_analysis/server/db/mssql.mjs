import sql from "mssql";

const stableCodes = new Set([
  "DB_NOT_CONFIGURED",
  "DB_TIMEOUT",
  "DB_UNAVAILABLE",
  "QUERY_INVALID_RESULT",
]);

export class DatabaseError extends Error {
  constructor(code, cause) {
    super(code, { cause });
    this.name = "DatabaseError";
    this.code = stableCodes.has(code) ? code : "DB_UNAVAILABLE";
  }
}

function normalizeError(error) {
  if (error instanceof DatabaseError) return error;
  const code = String(error?.code || "").toUpperCase();
  const timedOut = code.includes("TIMEOUT") || code === "ETIMEOUT";
  return new DatabaseError(timedOut ? "DB_TIMEOUT" : "DB_UNAVAILABLE", error);
}

const types = {
  date: sql.Date,
  int: sql.Int,
  text: sql.NVarChar(80),
};

export function createMssqlAdapter(databaseConfig) {
  let pool = null;
  let connecting = null;

  async function connect() {
    if (!databaseConfig.configured) throw new DatabaseError("DB_NOT_CONFIGURED");
    if (pool?.connected) return pool;
    if (connecting) return connecting;
    const nextPool = new sql.ConnectionPool({
      server: databaseConfig.server,
      port: databaseConfig.port,
      database: databaseConfig.database,
      user: databaseConfig.user,
      password: databaseConfig.password,
      connectionTimeout: databaseConfig.connectTimeoutMs,
      requestTimeout: databaseConfig.requestTimeoutMs,
      pool: { min: databaseConfig.poolMin, max: databaseConfig.poolMax, idleTimeoutMillis: 30_000 },
      options: {
        encrypt: databaseConfig.encrypt,
        trustServerCertificate: databaseConfig.trustServerCertificate,
        enableArithAbort: true,
      },
    });
    connecting = nextPool.connect().then((connected) => {
      pool = connected;
      pool.on("error", () => {});
      return pool;
    }).catch((error) => {
      nextPool.close().catch(() => {});
      throw normalizeError(error);
    }).finally(() => {
      connecting = null;
    });
    return connecting;
  }

  async function query(spec, values) {
    try {
      const connected = await connect();
      const requestTimeout = Math.max(databaseConfig.requestTimeoutMs, spec.minimumTimeoutMs || 0);
      const request = connected.request({ requestTimeout });
      for (const param of spec.params) {
        const raw = values[param.name] ?? null;
        const value = param.type === "date" && raw ? new Date(`${raw}T00:00:00.000Z`) : raw;
        request.input(param.name, types[param.type], value);
      }
      const result = await request.query(spec.text);
      if (!Array.isArray(result.recordset)) throw new DatabaseError("QUERY_INVALID_RESULT");
      return result.recordset;
    } catch (error) {
      throw normalizeError(error);
    }
  }

  async function health() {
    const startedAt = performance.now();
    if (!databaseConfig.configured) {
      return { configured: false, status: "down", latencyMs: null, code: "DB_NOT_CONFIGURED" };
    }
    try {
      const connected = await connect();
      await connected.request().query("SELECT 1 AS ok");
      return { configured: true, status: "up", latencyMs: Math.round(performance.now() - startedAt) };
    } catch (error) {
      const normalized = normalizeError(error);
      return { configured: true, status: "down", latencyMs: null, code: normalized.code };
    }
  }

  async function close() {
    const connected = pool;
    pool = null;
    if (connected) await connected.close().catch(() => {});
  }

  return { query, health, close };
}
