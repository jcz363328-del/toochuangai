import { copyFile, mkdir, readFile, readdir, rename, stat, unlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = path.resolve(projectRoot, "..", "outputs");
const destination = path.join(projectRoot, "public", "data", "ads-monitor.json");

async function findPayloads(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return findPayloads(target);
    return entry.name === "sellfox_ads_monitor_payload.json" ? [target] : [];
  }));
  return nested.flat();
}

const args = process.argv.slice(2);
const allowDemo = args.includes("--allow-demo");
const sourceArg = args.find((arg) => arg !== "--allow-demo");
const explicitSource = sourceArg ? path.resolve(sourceArg) : null;
const candidates = explicitSource ? [explicitSource] : await findPayloads(outputRoot);
if (!candidates.length) throw new Error("No Sellfox advertising payload was found.");

const inspected = await Promise.all(candidates.map(async (file) => {
  try {
    const payload = JSON.parse(await readFile(file, "utf8"));
    return { file, modified: (await stat(file)).mtimeMs, mode: payload?.meta?.mode };
  } catch {
    return null;
  }
}));
const ranked = inspected.filter((item) => item && (allowDemo || item.mode === "live"));
if (!ranked.length) throw new Error("No live Sellfox advertising payload was found.");
ranked.sort((a, b) => b.modified - a.modified);
await mkdir(path.dirname(destination), { recursive: true });
const temporary = `${destination}.tmp-${process.pid}-${Date.now()}`;
try {
  await copyFile(ranked[0].file, temporary);
  await rename(temporary, destination);
} catch (error) {
  await unlink(temporary).catch(() => {});
  throw error;
}
console.log(JSON.stringify({ source: ranked[0].file, destination }));
