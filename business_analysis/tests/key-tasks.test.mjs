import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { createKeyTaskStore } from "../server/key-tasks.mjs";

const managerScope = { role: "business_owner", department: "", userName: "周俊成" };
const memberScope = { role: "member", department: "运营一部", userName: "成员甲" };

async function withStore(callback) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "business-key-tasks-"));
  try {
    await callback(createKeyTaskStore({ filePath: path.join(directory, "key-tasks.json") }), directory);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
}

const sample = {
  department: "运营一部",
  project: "amazon-sop",
  task: "完成 SOP v1.0 草案",
  owner: "张三",
  output: "",
  nextCheckpoint: "选择 2 家店试运行",
  risk: "",
  status: "verifying",
};

test("关键任务直接写入 JSON，且不包含节点日期", async () => {
  await withStore(async (store, directory) => {
    const result = await store.create(sample, managerScope);
    assert.equal(result.count, 1);
    const persisted = JSON.parse(await fs.readFile(path.join(directory, "key-tasks.json"), "utf8"));
    assert.equal(persisted.tasks[0].task, sample.task);
    assert.equal(persisted.tasks[0].risk, "");
    assert.equal("nodeDate" in persisted.tasks[0], false);
    assert.equal("date" in persisted.tasks[0], false);
  });
});

test("普通成员只能维护所属部门，总负责人可批量追加", async () => {
  await withStore(async (store) => {
    await assert.rejects(
      () => store.create({ ...sample, department: "运营二部" }, memberScope),
      (error) => error.status === 403,
    );
    const batch = await store.create({ tasks: [
      { ...sample, owner: "成员甲" },
      { ...sample, owner: "同事乙", project: "other", task: "同事关键事项" },
    ] }, managerScope);
    assert.equal(batch.count, 2);
    const memberView = await store.list(memberScope);
    assert.equal(memberView.tasks.length, 1);
    assert.equal(memberView.tasks[0].owner, "成员甲");
    assert.equal(memberView.meta.scope.canViewAll, false);
    await assert.rejects(
      () => store.create({ ...sample, owner: "同事乙" }, memberScope),
      (error) => error.status === 403,
    );
  });
});

test("比例查看者可查看全部任务但不能修改", async () => {
  await withStore(async (store) => {
    await store.create(sample, managerScope);
    const readOnlyScope = { role: "ratio_viewer", department: "", userName: "只读用户" };
    const view = await store.list(readOnlyScope);
    assert.equal(view.tasks.length, 1);
    assert.equal(view.meta.scope.canEditAll, false);
    await assert.rejects(
      () => store.create(sample, readOnlyScope),
      (error) => error.status === 403,
    );
  });
});

test("任务支持更新与删除，风险字段为可选", async () => {
  await withStore(async (store) => {
    const created = await store.create(sample, managerScope);
    const id = created.created[0].id;
    const updated = await store.update(id, { ...sample, status: "blocked", risk: "供应商交期未确认" }, managerScope);
    assert.equal(updated.status, "blocked");
    assert.equal(updated.risk, "供应商交期未确认");
    await store.remove(id, managerScope);
    assert.equal((await store.list(managerScope)).tasks.length, 0);
  });
});
