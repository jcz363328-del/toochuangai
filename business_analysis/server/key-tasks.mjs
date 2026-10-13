import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const KEY_TASK_DEPARTMENTS = Object.freeze([
  "运营一部",
  "运营二部",
  "运营三部",
  "运营六部",
  "运营七部",
]);

export const KEY_TASK_DEPARTMENT_OWNERS = Object.freeze({
  "运营一部": "周雪",
  "运营二部": "王钰媛",
  "运营三部": "大张雯",
  "运营六部": "郭鑫",
  "运营七部": "侯瑞昕",
});

export const KEY_TASK_PROJECTS = Object.freeze([
  { id: "product-pilot", label: "产品部门试点" },
  { id: "amazon-sop", label: "亚马逊SOP" },
  { id: "tk-joint", label: "TK联营" },
  { id: "standard-line", label: "普通产品线" },
  { id: "low-price-line", label: "低价产品线" },
  { id: "new-site", label: "新站点" },
  { id: "other", label: "其他" },
]);

export const KEY_TASK_STATUSES = Object.freeze([
  { id: "not_started", label: "未启动", tone: "neutral" },
  { id: "started", label: "已启动", tone: "info" },
  { id: "verifying", label: "待验证", tone: "warning" },
  { id: "phased_output", label: "已有阶段产出", tone: "positive" },
  { id: "completed", label: "已完成", tone: "success" },
  { id: "blocked", label: "阻塞", tone: "danger" },
]);

const defaultFile = fileURLToPath(new URL("../data/key-tasks.json", import.meta.url));
const departmentSet = new Set(KEY_TASK_DEPARTMENTS);
const projectSet = new Set(KEY_TASK_PROJECTS.map((item) => item.id));
const statusSet = new Set(KEY_TASK_STATUSES.map((item) => item.id));
const allowedFields = [
  "department",
  "project",
  "task",
  "owner",
  "output",
  "nextCheckpoint",
  "risk",
  "status",
];

function problem(status, code, message) {
  const error = new Error(message);
  error.status = status;
  error.code = code;
  return error;
}

function text(value, field, maximum, required = false) {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (required && !normalized) throw problem(400, "INVALID_TASK", `${field}不能为空`);
  if (normalized.length > maximum) throw problem(400, "INVALID_TASK", `${field}内容过长`);
  if (/\u0000/.test(normalized)) throw problem(400, "INVALID_TASK", `${field}包含无效字符`);
  return normalized;
}

function normalizeScope(raw = {}) {
  const role = ["business_owner", "department_leader", "member", "ratio_viewer"].includes(raw.role)
    ? raw.role
    : "ratio_viewer";
  const department = departmentSet.has(raw.department) ? raw.department : "";
  return {
    role,
    department,
    userName: text(raw.userName, "userName", 80) || "本地用户",
    canViewAll: role === "business_owner" || role === "ratio_viewer",
    canEditAll: role === "business_owner",
  };
}

function assertDepartmentAccess(scope, department) {
  if (!scope.canEditAll && (scope.role === "ratio_viewer" || department !== scope.department)) {
    throw problem(403, "TASK_DEPARTMENT_FORBIDDEN", "当前账号无权维护该部门的关键任务");
  }
}

function normalizePersonName(value) {
  return String(value || "").trim().replace(/\s*[（(][^（）()]{1,40}[）)]\s*$/, "").replace(/\s+/g, "");
}

function taskIsVisible(task, scope) {
  if (scope.canViewAll) return true;
  if (!task || task.department !== scope.department) return false;
  if (scope.role === "department_leader") return true;
  if (scope.role !== "member") return false;
  const userName = normalizePersonName(scope.userName);
  return [task.owner, task.createdBy].some((value) => normalizePersonName(value) === userName);
}

function assertTaskAccess(scope, task) {
  if (!taskIsVisible(task, scope)) {
    throw problem(403, "TASK_OWNER_FORBIDDEN", "当前账号只能维护本人负责的关键任务");
  }
}

function normalizeTaskInput(raw, scope) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw problem(400, "INVALID_TASK", "任务内容格式不正确");
  }
  const department = text(raw.department, "所属部门", 40, true);
  const project = text(raw.project, "关键专项", 60, true);
  if (!departmentSet.has(department)) throw problem(400, "INVALID_TASK", "所属部门不在经营分析范围内");
  if (!projectSet.has(project)) throw problem(400, "INVALID_TASK", "关键专项不存在");
  assertDepartmentAccess(scope, department);

  const normalized = {
    department,
    project,
    task: text(raw.task, "具体任务", 300, true),
    owner: text(raw.owner, "负责人", 80),
    output: text(raw.output, "最新具体产出", 500),
    nextCheckpoint: text(raw.nextCheckpoint, "下一检查点", 500),
    risk: text(raw.risk, "风险或阻塞", 500),
    status: text(raw.status, "任务状态", 40) || "not_started",
  };
  if (scope.role === "member") {
    const requestedOwner = normalizePersonName(normalized.owner);
    const currentUser = normalizePersonName(scope.userName);
    if (requestedOwner && requestedOwner !== currentUser) {
      throw problem(403, "TASK_OWNER_FORBIDDEN", "普通成员只能为本人创建关键任务");
    }
    normalized.owner = scope.userName;
  }
  if (!statusSet.has(normalized.status)) throw problem(400, "INVALID_TASK", "任务状态不存在");
  return normalized;
}

function emptyDocument() {
  return { version: 1, updatedAt: null, tasks: [] };
}

function normalizeDocument(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.tasks)) return emptyDocument();
  return {
    version: 1,
    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : null,
    tasks: raw.tasks.filter((task) => task && typeof task === "object"),
  };
}

async function readDocument(filePath) {
  try {
    return normalizeDocument(JSON.parse(await fs.readFile(filePath, "utf8")));
  } catch (error) {
    if (error?.code === "ENOENT") return emptyDocument();
    if (error instanceof SyntaxError) throw problem(500, "TASK_FILE_INVALID", "关键任务 JSON 文件格式无效");
    throw error;
  }
}

async function writeDocument(filePath, document) {
  const directory = path.dirname(filePath);
  await fs.mkdir(directory, { recursive: true });
  const temporary = `${filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(document, null, 2)}\n`, "utf8");
  await fs.rename(temporary, filePath);
}

function publicEnvelope(document, scope) {
  const tasks = document.tasks.filter((task) => taskIsVisible(task, scope));
  return {
    version: document.version,
    updatedAt: document.updatedAt,
    tasks,
    meta: {
      departments: KEY_TASK_DEPARTMENTS,
      departmentOwners: KEY_TASK_DEPARTMENT_OWNERS,
      projects: KEY_TASK_PROJECTS,
      statuses: KEY_TASK_STATUSES,
      scope,
    },
  };
}

export function createKeyTaskStore(options = {}) {
  const filePath = path.resolve(options.filePath || process.env.SALES_KEY_TASKS_FILE || defaultFile);
  let mutationQueue = Promise.resolve();

  const mutate = (callback) => {
    const result = mutationQueue.then(async () => {
      const document = await readDocument(filePath);
      const value = await callback(document);
      document.updatedAt = new Date().toISOString();
      await writeDocument(filePath, document);
      return value;
    });
    mutationQueue = result.catch(() => undefined);
    return result;
  };

  return {
    filePath,

    async list(rawScope) {
      const scope = normalizeScope(rawScope);
      return publicEnvelope(await readDocument(filePath), scope);
    },

    async create(rawInput, rawScope) {
      const scope = normalizeScope(rawScope);
      const inputs = Array.isArray(rawInput?.tasks) ? rawInput.tasks : [rawInput];
      if (!inputs.length || inputs.length > 200) {
        throw problem(400, "INVALID_TASK_BATCH", "每次需提交 1 至 200 条任务");
      }
      const normalized = inputs.map((item) => normalizeTaskInput(item, scope));
      const created = await mutate((document) => {
        const now = new Date().toISOString();
        const rows = normalized.map((item) => ({
          id: crypto.randomUUID(),
          ...item,
          createdAt: now,
          updatedAt: now,
          createdBy: scope.userName,
          updatedBy: scope.userName,
        }));
        document.tasks.push(...rows);
        return rows;
      });
      return { created, count: created.length };
    },

    async update(id, rawInput, rawScope) {
      const scope = normalizeScope(rawScope);
      const normalized = normalizeTaskInput(rawInput, scope);
      return mutate((document) => {
        const index = document.tasks.findIndex((item) => item.id === id);
        if (index < 0) throw problem(404, "TASK_NOT_FOUND", "关键任务不存在或已被删除");
        assertTaskAccess(scope, document.tasks[index]);
        const current = document.tasks[index];
        const next = {
          ...current,
          ...Object.fromEntries(allowedFields.map((field) => [field, normalized[field]])),
          updatedAt: new Date().toISOString(),
          updatedBy: scope.userName,
        };
        document.tasks[index] = next;
        return next;
      });
    },

    async remove(id, rawScope) {
      const scope = normalizeScope(rawScope);
      return mutate((document) => {
        const index = document.tasks.findIndex((item) => item.id === id);
        if (index < 0) throw problem(404, "TASK_NOT_FOUND", "关键任务不存在或已被删除");
        assertTaskAccess(scope, document.tasks[index]);
        const [removed] = document.tasks.splice(index, 1);
        return removed;
      });
    },
  };
}
