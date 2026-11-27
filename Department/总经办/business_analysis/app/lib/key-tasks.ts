export type KeyTaskStatusId =
  | "not_started"
  | "started"
  | "verifying"
  | "phased_output"
  | "completed"
  | "blocked";

export interface KeyTask {
  id: string;
  department: string;
  project: string;
  task: string;
  owner: string;
  output: string;
  nextCheckpoint: string;
  risk: string;
  status: KeyTaskStatusId;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
}

export type KeyTaskDraft = Pick<
  KeyTask,
  "department" | "project" | "task" | "owner" | "output" | "nextCheckpoint" | "risk" | "status"
>;

export interface KeyTaskEnvelope {
  version: number;
  updatedAt: string | null;
  tasks: KeyTask[];
  meta: {
    departments: string[];
    departmentOwners: Record<string, string>;
    projects: Array<{ id: string; label: string }>;
    statuses: Array<{ id: KeyTaskStatusId; label: string; tone: string }>;
    scope: {
      role: "business_owner" | "department_leader" | "member" | "ratio_viewer";
      department: string;
      userName: string;
      canViewAll: boolean;
      canEditAll: boolean;
    };
  };
}

class KeyTaskRequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "KeyTaskRequestError";
  }
}

const keyTaskApi = () =>
  globalThis.document?.documentElement.dataset.keyTasksApi || "/api/key-tasks";

async function request<T>(path = "", init?: RequestInit): Promise<T> {
  const response = await fetch(`${keyTaskApi()}${path}`, {
    cache: "no-store",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    // The status-aware fallback below is more useful than a JSON parse error.
  }
  if (!response.ok) {
    const record = payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
    const nested = record.error && typeof record.error === "object"
      ? record.error as Record<string, unknown>
      : {};
    throw new KeyTaskRequestError(
      typeof nested.message === "string" ? nested.message : `关键任务请求失败（HTTP ${response.status}）`,
      response.status,
    );
  }
  return payload as T;
}

export const fetchKeyTasks = () => request<KeyTaskEnvelope>();

export const createKeyTasks = (tasks: KeyTaskDraft[]) =>
  request<{ created: KeyTask[]; count: number }>("", {
    method: "POST",
    body: JSON.stringify(tasks.length === 1 ? tasks[0] : { tasks }),
  });

export const updateKeyTask = (id: string, task: KeyTaskDraft) =>
  request<{ task: KeyTask }>(`/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(task),
  });

export const deleteKeyTask = (id: string) =>
  request<{ removed: KeyTask }>(`/${encodeURIComponent(id)}`, { method: "DELETE" });
