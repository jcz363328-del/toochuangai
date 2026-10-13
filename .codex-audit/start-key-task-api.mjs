import { fileURLToPath } from "node:url";

process.env.SALES_API_PORT = "4391";
process.env.SALES_KEY_TASKS_FILE = fileURLToPath(new URL(
  "../business_analysis/data/key-tasks.json",
  import.meta.url,
));

await import("../business_analysis/server/index.mjs");
