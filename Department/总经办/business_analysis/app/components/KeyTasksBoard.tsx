"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import {
  ArrowClockwise,
  CheckCircle,
  ClipboardText,
  DownloadSimple,
  Export,
  FloppyDisk,
  Plus,
  Trash,
  UploadSimple,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import {
  createKeyTasks,
  deleteKeyTask,
  fetchKeyTasks,
  updateKeyTask,
  type KeyTask,
  type KeyTaskDraft,
  type KeyTaskEnvelope,
  type KeyTaskStatusId,
} from "../lib/key-tasks";

type DrawerMode = "single" | "batch";

const emptyDraft: KeyTaskDraft = {
  department: "",
  project: "",
  task: "",
  owner: "",
  output: "",
  nextCheckpoint: "",
  risk: "",
  status: "not_started",
};

const batchColumns = [
  "所属部门",
  "关键专项",
  "具体任务",
  "负责人",
  "最新具体产出",
  "下一检查点",
  "风险或阻塞",
  "任务状态",
];

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "关键任务操作失败，请稍后重试";
}

function downloadJson(name: string, payload: unknown) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  window.setTimeout(() => {
    anchor.remove();
    URL.revokeObjectURL(url);
  }, 10_000);
}

function taskDraft(task: KeyTask): KeyTaskDraft {
  return {
    department: task.department,
    project: task.project,
    task: task.task,
    owner: task.owner,
    output: task.output,
    nextCheckpoint: task.nextCheckpoint,
    risk: task.risk,
    status: task.status,
  };
}

function KeyTaskDrawer({
  data,
  mode,
  draft,
  editing,
  batchText,
  busy,
  onModeChange,
  onDraftChange,
  onBatchTextChange,
  onClose,
  onSave,
  onDelete,
  onBatchSave,
}: {
  data: KeyTaskEnvelope;
  mode: DrawerMode;
  draft: KeyTaskDraft;
  editing: KeyTask | null;
  batchText: string;
  busy: boolean;
  onModeChange: (mode: DrawerMode) => void;
  onDraftChange: (draft: KeyTaskDraft) => void;
  onBatchTextChange: (value: string) => void;
  onClose: () => void;
  onSave: (continueAdding: boolean) => void;
  onDelete: () => void;
  onBatchSave: () => void;
}) {
  const [validationMessage, setValidationMessage] = useState("");

  useEffect(() => {
    const close = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const update = (field: keyof KeyTaskDraft, value: string) =>
    onDraftChange({ ...draft, [field]: value });
  const scope = data.meta.scope;
  const allowedDepartments = scope.canEditAll
    ? data.meta.departments
    : data.meta.departments.filter((item) => item === scope.department);
  const validateAndSave = (continueAdding: boolean) => {
    const missing = [
      !draft.department && "所属部门",
      !draft.project && "关键专项",
      !draft.task.trim() && "具体任务",
    ].filter(Boolean);
    if (missing.length) {
      setValidationMessage(`请补充${missing.join("、")}后再保存`);
      return;
    }
    setValidationMessage("");
    onSave(continueAdding);
  };

  return (
    <div className="key-task-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="key-task-drawer" role="dialog" aria-modal="true" aria-labelledby="key-task-drawer-title">
        <header className="key-task-drawer-head">
          <div className="key-task-drawer-icon"><ClipboardText size={25} weight="duotone" /></div>
          <div>
            <h2 id="key-task-drawer-title">{editing ? "编辑关键任务" : "收集关键任务"}</h2>
            <p>统一沉淀部门重点事项，支持单条或批量追加</p>
          </div>
          <button className="key-task-close" type="button" onClick={onClose} aria-label="关闭关键任务面板">
            <X size={22} />
          </button>
        </header>

        {!editing ? (
          <nav className="key-task-entry-tabs" aria-label="录入方式">
            <button type="button" className={mode === "single" ? "active" : ""} onClick={() => onModeChange("single")}>
              <ClipboardText size={18} weight={mode === "single" ? "fill" : "regular"} /> 单条录入
            </button>
            <button type="button" className={mode === "batch" ? "active" : ""} onClick={() => onModeChange("batch")}>
              <UploadSimple size={18} weight={mode === "batch" ? "bold" : "regular"} /> 批量粘贴
            </button>
          </nav>
        ) : null}

        {mode === "single" ? (
          <form className="key-task-form" noValidate onSubmit={(event: FormEvent) => { event.preventDefault(); validateAndSave(false); }}>
            <div className="key-task-form-scroll">
              <div className="key-task-form-split key-task-form-basics">
                <label className="key-task-form-field">
                  <span>所属部门 <em aria-hidden="true">*</em></span>
                  <select value={draft.department} disabled={!scope.canEditAll} onChange={(event) => update("department", event.target.value)} aria-required="true">
                    {allowedDepartments.map((department) => <option key={department} value={department}>{department}</option>)}
                  </select>
                </label>
                <label className="key-task-form-field">
                  <span>关键专项 <em aria-hidden="true">*</em></span>
                  <select value={draft.project} onChange={(event) => update("project", event.target.value)} aria-required="true">
                    {data.meta.projects.map((project) => <option key={project.id} value={project.id}>{project.label}</option>)}
                  </select>
                </label>
              </div>
              <label className="key-task-form-field">
                <span className="key-task-field-heading"><span>具体任务 <em aria-hidden="true">*</em></span><small>{draft.task.length}/300</small></span>
                <textarea value={draft.task} onChange={(event) => update("task", event.target.value)} placeholder="例如：完成低价产品线首批上新" rows={2} maxLength={300} aria-required="true" />
              </label>
              <div className="key-task-form-split">
                <label className="key-task-form-field">
                  <span>负责人</span>
                  <input value={draft.owner} onChange={(event) => update("owner", event.target.value)} maxLength={80} autoComplete="off" placeholder="填写任务负责人" />
                </label>
                <label className="key-task-form-field">
                  <span>任务状态</span>
                  <select value={draft.status} onChange={(event) => update("status", event.target.value)}>
                    {data.meta.statuses.map((status) => <option key={status.id} value={status.id}>{status.label}</option>)}
                  </select>
                </label>
              </div>
              <div className="key-task-form-split key-task-progress-fields">
                <label className="key-task-form-field">
                  <span>最新具体产出</span>
                  <textarea value={draft.output} onChange={(event) => update("output", event.target.value)} rows={2} maxLength={500} placeholder="记录当前已经完成的成果" />
                </label>
                <label className="key-task-form-field">
                  <span>下一检查点</span>
                  <textarea value={draft.nextCheckpoint} onChange={(event) => update("nextCheckpoint", event.target.value)} rows={2} maxLength={500} placeholder="填写下一步动作或验收节点" />
                </label>
              </div>
              <label className="key-task-form-field">
                <span>风险或阻塞 <small>选填</small></span>
                <textarea value={draft.risk} onChange={(event) => update("risk", event.target.value)} rows={2} maxLength={500} placeholder="如无风险可留空" />
              </label>
              {validationMessage ? (
                <div className="key-task-validation" role="alert"><WarningCircle size={18} weight="fill" /> {validationMessage}</div>
              ) : null}
            </div>

            <footer className="key-task-drawer-actions">
              {editing ? (
                <button className="key-task-delete" type="button" disabled={busy} onClick={onDelete}>
                  <Trash size={17} /> 删除
                </button>
              ) : (
                <button className="key-task-secondary" type="button" disabled={busy} onClick={() => validateAndSave(true)}>
                  <FloppyDisk size={17} /> 保存并继续
                </button>
              )}
              <button className="key-task-primary" type="submit" disabled={busy}>
                {busy ? <ArrowClockwise className="spin" size={18} /> : <CheckCircle size={18} />}
                {editing ? "保存修改" : "保存并完成"}
              </button>
            </footer>
          </form>
        ) : (
          <section className="key-task-batch">
            <div className="key-task-batch-guide">
              <b>从表格直接复制粘贴</b>
              <p>每行一条任务，字段以制表符分隔。首行表头可保留，任务会分批追加到现有 JSON 中。</p>
            </div>
            <code>{batchColumns.join("　→　")}</code>
            <textarea
              value={batchText}
              onChange={(event) => onBatchTextChange(event.target.value)}
              rows={15}
              placeholder={`${batchColumns.join("\t")}\n运营一部\t亚马逊SOP\t完成SOP草案\t张三\t已输出初稿\t选择2家店试运行\t\t待验证`}
            />
            <footer className="key-task-drawer-actions">
              <button className="key-task-secondary" type="button" onClick={onClose}>取消</button>
              <button className="key-task-primary" type="button" disabled={busy || !batchText.trim()} onClick={onBatchSave}>
                {busy ? <ArrowClockwise className="spin" size={18} /> : <UploadSimple size={18} />}
                追加批量任务
              </button>
            </footer>
          </section>
        )}
      </aside>
    </div>
  );
}

export default function KeyTasksBoard({ visible }: { visible: boolean }) {
  const [data, setData] = useState<KeyTaskEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [perspective, setPerspective] = useState("");
  const [drawerMode, setDrawerMode] = useState<DrawerMode | null>(null);
  const [editing, setEditing] = useState<KeyTask | null>(null);
  const [draft, setDraft] = useState<KeyTaskDraft>(emptyDraft);
  const [batchText, setBatchText] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const autoLoadAttempted = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await fetchKeyTasks();
      setData(next);
      setPerspective((current) => current || (next.meta.scope.canViewAll ? "" : next.meta.scope.department));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!visible || data || loading || autoLoadAttempted.current) return;
    autoLoadAttempted.current = true;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [data, load, loading, visible]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const visibleDepartments = useMemo(() => {
    if (!data) return [];
    if (perspective) return data.meta.departments.filter((department) => department === perspective);
    return data.meta.departments;
  }, [data, perspective]);
  const visibleTasks = useMemo(
    () => data?.tasks.filter((task) => !perspective || task.department === perspective) ?? [],
    [data, perspective],
  );
  const statusMap = useMemo(
    () => new Map(data?.meta.statuses.map((status) => [status.id, status]) ?? []),
    [data],
  );

  const closeDrawer = useCallback(() => {
    if (busy) return;
    setDrawerMode(null);
    setEditing(null);
    setBatchText("");
  }, [busy]);

  const openNew = (department?: string, project?: string) => {
    if (!data) return;
    const initialDepartment = department || data.meta.scope.department || data.meta.departments[0] || "";
    setDraft({
      ...emptyDraft,
      department: initialDepartment,
      project: project || data.meta.projects[0]?.id || "",
      owner: data.meta.departmentOwners[initialDepartment] || "",
    });
    setEditing(null);
    setDrawerMode("single");
  };

  const openEdit = (task: KeyTask) => {
    setDraft(taskDraft(task));
    setEditing(task);
    setDrawerMode("single");
  };

  const saveSingle = async (continueAdding: boolean) => {
    if (!draft.department || !draft.project || !draft.task.trim()) {
      setError("请填写所属部门、关键专项和具体任务");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (editing) await updateKeyTask(editing.id, draft);
      else await createKeyTasks([draft]);
      await load();
      setNotice(editing ? "任务已更新" : "任务已写入 JSON");
      if (continueAdding && !editing) {
        setDraft((current) => ({ ...emptyDraft, department: current.department, project: current.project, owner: current.owner }));
      } else {
        setDrawerMode(null);
        setEditing(null);
      }
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!editing || !window.confirm("确定删除这条关键任务吗？")) return;
    setBusy(true);
    setError("");
    try {
      await deleteKeyTask(editing.id);
      await load();
      setDrawerMode(null);
      setEditing(null);
      setNotice("任务已删除");
    } catch (removeError) {
      setError(errorMessage(removeError));
    } finally {
      setBusy(false);
    }
  };

  const parseBatch = () => {
    if (!data) return [];
    const projects = new Map<string, string>();
    data.meta.projects.forEach((project) => {
      projects.set(project.id, project.id);
      projects.set(project.label, project.id);
    });
    const statuses = new Map<string, KeyTaskStatusId>();
    data.meta.statuses.forEach((status) => {
      statuses.set(status.id, status.id);
      statuses.set(status.label, status.id);
    });
    const rows = batchText.split(/\r?\n/).map((row) => row.trim()).filter(Boolean);
    if (rows[0]?.includes("所属部门") || rows[0]?.includes("具体任务")) rows.shift();
    return rows.map((row, index) => {
      const columns = row.includes("\t") ? row.split("\t") : row.split(",");
      const department = columns[0]?.trim() || "";
      const project = projects.get(columns[1]?.trim() || "") || "";
      const task = columns[2]?.trim() || "";
      if (!department || !project || !task) throw new Error(`第 ${index + 1} 行缺少部门、专项或具体任务`);
      return {
        department,
        project,
        task,
        owner: columns[3]?.trim() || "",
        output: columns[4]?.trim() || "",
        nextCheckpoint: columns[5]?.trim() || "",
        risk: columns[6]?.trim() || "",
        status: statuses.get(columns[7]?.trim() || "") || "not_started",
      } satisfies KeyTaskDraft;
    });
  };

  const saveBatch = async () => {
    setBusy(true);
    setError("");
    try {
      const tasks = parseBatch();
      if (!tasks.length) throw new Error("请粘贴至少一条任务");
      await createKeyTasks(tasks);
      await load();
      setDrawerMode(null);
      setBatchText("");
      setNotice(`已追加 ${tasks.length} 条任务`);
    } catch (batchError) {
      setError(errorMessage(batchError));
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !data) return;
    setBusy(true);
    setError("");
    try {
      const payload = JSON.parse(await file.text()) as unknown;
      const source = Array.isArray(payload)
        ? payload
        : payload && typeof payload === "object" && Array.isArray((payload as { tasks?: unknown }).tasks)
          ? (payload as { tasks: unknown[] }).tasks
          : [];
      if (!source.length) throw new Error("导入文件中没有可用任务");
      const projectByLabel = new Map(data.meta.projects.map((item) => [item.label, item.id]));
      const statusByLabel = new Map(data.meta.statuses.map((item) => [item.label, item.id]));
      const tasks = source.map((item) => {
        if (!item || typeof item !== "object") throw new Error("导入任务格式不正确");
        const row = item as Record<string, unknown>;
        const rawProject = String(row.project || row["关键专项"] || "").trim();
        const rawStatus = String(row.status || row["任务状态"] || "").trim();
        return {
          department: String(row.department || row["所属部门"] || "").trim(),
          project: projectByLabel.get(rawProject) || rawProject,
          task: String(row.task || row["具体任务"] || "").trim(),
          owner: String(row.owner || row["负责人"] || "").trim(),
          output: String(row.output || row["最新具体产出"] || "").trim(),
          nextCheckpoint: String(row.nextCheckpoint || row["下一检查点"] || "").trim(),
          risk: String(row.risk || row["风险或阻塞"] || "").trim(),
          status: (statusByLabel.get(rawStatus) || rawStatus || "not_started") as KeyTaskStatusId,
        } satisfies KeyTaskDraft;
      });
      await createKeyTasks(tasks);
      await load();
      setNotice(`已导入 ${tasks.length} 条任务`);
    } catch (importError) {
      setError(errorMessage(importError));
    } finally {
      setBusy(false);
    }
  };

  if (loading && !data) {
    return <div className="key-task-loading"><ArrowClockwise className="spin" size={22} /> 正在读取关键任务 JSON…</div>;
  }
  if (!data) {
    return (
      <div className="key-task-error-state">
        <b>关键任务暂时无法读取</b><span>{error || "请稍后重试"}</span>
        <button type="button" onClick={() => void load()}><ArrowClockwise size={17} /> 重新加载</button>
      </div>
    );
  }

  const downloadTemplate = () => downloadJson("关键任务导入模板.json", {
    version: 1,
    instructions: "可分批导入；风险或阻塞为选填项。",
    tasks: [{
      department: data.meta.scope.department || data.meta.departments[0],
      project: data.meta.projects[0]?.id,
      task: "填写具体任务",
      owner: "填写负责人",
      output: "",
      nextCheckpoint: "",
      risk: "",
      status: "not_started",
    }],
  });
  const exportCurrent = () => downloadJson(`关键任务-${perspective || "全部部门"}.json`, {
    version: 1,
    exportedAt: new Date().toISOString(),
    perspective: perspective || "全部部门",
    tasks: visibleTasks.map(taskDraft),
  });

  return (
    <>
      <div className="key-task-toolbar">
        <div className="key-task-perspective">
          <b>当前视角</b>
          <select value={perspective} disabled={!data.meta.scope.canViewAll} onChange={(event) => setPerspective(event.target.value)}>
            {data.meta.scope.canViewAll ? <option value="">全部部门</option> : null}
            {data.meta.departments.map((department) => <option key={department} value={department}>{department}</option>)}
          </select>
          <span>{data.meta.scope.canViewAll ? "总负责人视角：可查看全部部门" : `${data.meta.scope.department}视角：仅维护本部门任务`}</span>
        </div>
        <div className="key-task-tools">
          <button type="button" onClick={downloadTemplate}><DownloadSimple size={17} /> 下载导入模板</button>
          <button type="button" disabled={busy} onClick={() => fileInput.current?.click()}><UploadSimple size={17} /> 导入任务</button>
          <button type="button" disabled={!visibleTasks.length} onClick={exportCurrent}><Export size={17} /> 导出当前任务</button>
          <input ref={fileInput} className="sr-only" type="file" accept="application/json,.json" onChange={importFile} />
        </div>
      </div>

      {error ? <div className="key-task-alert" role="alert">{error}<button type="button" onClick={() => setError("")}><X size={15} /></button></div> : null}
      {notice ? <div className="key-task-toast" role="status"><CheckCircle size={17} weight="fill" /> {notice}</div> : null}

      <div className="key-task-matrix-scroll">
        <div className="key-task-matrix" style={{ gridTemplateColumns: `150px repeat(${data.meta.projects.length}, minmax(0, 1fr))` }}>
          <div className="key-task-matrix-head">部门</div>
          {data.meta.projects.map((project) => <div className="key-task-matrix-head" key={project.id}>{project.label}</div>)}

          {visibleDepartments.map((department) => {
            const departmentTasks = visibleTasks.filter((task) => task.department === department);
            return (
              <div className="key-task-matrix-row" key={department}>
                <div className="key-task-department-cell">
                  <b>{department}</b>
                  <span>负责人：{data.meta.departmentOwners[department] || "待设置"}</span>
                  <span>{departmentTasks.length} 项任务</span>
                </div>
                {data.meta.projects.map((project) => {
                  const tasks = departmentTasks
                    .filter((task) => task.project === project.id)
                    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
                  const canEdit = data.meta.scope.canEditAll || data.meta.scope.department === department;
                  return (
                    <div className={`key-task-cell${project.id === "other" ? " is-other" : ""}`} key={`${department}-${project.id}`}>
                      {tasks.length ? (
                        <div className="key-task-card-stack">
                          {tasks.slice(0, 2).map((task) => {
                            const status = statusMap.get(task.status);
                            return (
                              <button className="key-task-card" type="button" key={task.id} onClick={() => openEdit(task)}>
                                <span className={`key-task-status status-${status?.tone || "neutral"}`}><i />{status?.label || task.status}</span>
                                <strong>{task.task}</strong>
                                {task.output ? <p>{task.output}</p> : null}
                                <small>{task.nextCheckpoint ? `下一步：${task.nextCheckpoint}` : task.risk ? `风险：${task.risk}` : "点击补充任务进展"}</small>
                              </button>
                            );
                          })}
                          {tasks.length > 2 ? <span className="key-task-more">另有 {tasks.length - 2} 项，点击卡片逐项维护</span> : null}
                        </div>
                      ) : project.id === "other" && canEdit ? (
                        <button className="key-task-add-cell" type="button" onClick={() => openNew(department, project.id)}>
                          <Plus size={25} /><b>新增任务</b><span>本期临时关键事项</span>
                        </button>
                      ) : (
                        <button className="key-task-empty" type="button" disabled={!canEdit} onClick={() => openNew(department, project.id)}>
                          <span>待填报</span><small>本月尚无内容</small>
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <div className="key-task-board-foot">
        <span>数据文件：JSON · {data.updatedAt ? `更新于 ${new Date(data.updatedAt).toLocaleString("zh-CN", { hour12: false })}` : "尚未录入任务"}</span>
        <button type="button" disabled={loading} onClick={() => void load()}><ArrowClockwise className={loading ? "spin" : ""} size={16} /> 刷新任务</button>
      </div>

      {drawerMode ? (
        <KeyTaskDrawer
          data={data}
          mode={drawerMode}
          draft={draft}
          editing={editing}
          batchText={batchText}
          busy={busy}
          onModeChange={setDrawerMode}
          onDraftChange={setDraft}
          onBatchTextChange={setBatchText}
          onClose={closeDrawer}
          onSave={(continueAdding) => void saveSingle(continueAdding)}
          onDelete={() => void remove()}
          onBatchSave={() => void saveBatch()}
        />
      ) : null}
    </>
  );
}
