import { spawn } from "node:child_process";

const options = { cwd: process.cwd(), env: process.env, stdio: "inherit", windowsHide: true };
const api = spawn(process.execPath, ["--watch", "server/index.mjs"], options);
const npmCli = process.env.npm_execpath;
const web = npmCli
  ? spawn(process.execPath, [npmCli, "run", "dev:web", "--", ...process.argv.slice(2)], options)
  : spawn(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "dev:web", "--", ...process.argv.slice(2)], {
      ...options,
      shell: process.platform === "win32",
    });
const children = [api, web];
let stopping = false;

function stop(signal = "SIGTERM", exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) if (!child.killed) child.kill(signal);
  process.exitCode = exitCode;
}

for (const child of children) {
  child.on("error", () => stop("SIGTERM", 1));
  child.on("exit", (code, signal) => {
    if (!stopping) stop("SIGTERM", code ?? (signal ? 1 : 0));
  });
}

process.once("SIGINT", () => stop("SIGINT", 0));
process.once("SIGTERM", () => stop("SIGTERM", 0));
