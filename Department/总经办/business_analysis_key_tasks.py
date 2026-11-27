import json
import os
import tempfile
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from business_analysis_access import normalize_person_name


KEY_TASK_DEPARTMENTS = (
    "运营一部",
    "运营二部",
    "运营三部",
    "运营六部",
    "运营七部",
)

KEY_TASK_DEPARTMENT_OWNERS = {
    "运营一部": "周雪",
    "运营二部": "王钰媛",
    "运营三部": "大张雯",
    "运营六部": "郭鑫",
    "运营七部": "侯瑞昕",
}

KEY_TASK_PROJECTS = (
    {"id": "product-pilot", "label": "产品部门试点"},
    {"id": "amazon-sop", "label": "亚马逊SOP"},
    {"id": "tk-joint", "label": "TK联营"},
    {"id": "standard-line", "label": "普通产品线"},
    {"id": "low-price-line", "label": "低价产品线"},
    {"id": "new-site", "label": "新站点"},
    {"id": "other", "label": "其他"},
)

KEY_TASK_STATUSES = (
    {"id": "not_started", "label": "未启动", "tone": "neutral"},
    {"id": "started", "label": "已启动", "tone": "info"},
    {"id": "verifying", "label": "待验证", "tone": "warning"},
    {"id": "phased_output", "label": "已有阶段产出", "tone": "positive"},
    {"id": "completed", "label": "已完成", "tone": "success"},
    {"id": "blocked", "label": "阻塞", "tone": "danger"},
)

_DEPARTMENT_SET = set(KEY_TASK_DEPARTMENTS)
_PROJECT_SET = {item["id"] for item in KEY_TASK_PROJECTS}
_STATUS_SET = {item["id"] for item in KEY_TASK_STATUSES}
_ALLOWED_FIELDS = (
    "department",
    "project",
    "task",
    "owner",
    "output",
    "nextCheckpoint",
    "risk",
    "status",
)


class KeyTaskStoreError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = int(status)
        self.code = str(code)
        self.message = str(message)


def _problem(status, code, message):
    raise KeyTaskStoreError(status, code, message)


def _text(value, field, maximum, required=False):
    normalized = value.strip() if isinstance(value, str) else ""
    if required and not normalized:
        _problem(400, "INVALID_TASK", f"{field}不能为空")
    if len(normalized) > maximum:
        _problem(400, "INVALID_TASK", f"{field}内容过长")
    if "\x00" in normalized:
        _problem(400, "INVALID_TASK", f"{field}包含无效字符")
    return normalized


def _normalize_scope(raw):
    raw = raw if isinstance(raw, dict) else {}
    role = str(raw.get("role") or "ratio_viewer")
    if role not in {"business_owner", "department_leader", "member", "ratio_viewer"}:
        role = "ratio_viewer"
    department = str(raw.get("department") or "")
    if department not in _DEPARTMENT_SET:
        department = ""
    return {
        "role": role,
        "department": department,
        "userName": _text(raw.get("userName"), "userName", 80) or "本地用户",
        "canViewAll": role in {"business_owner", "ratio_viewer"},
        "canEditAll": role == "business_owner",
    }


def _assert_department_access(scope, department):
    if scope["canEditAll"]:
        return
    if scope["role"] == "ratio_viewer" or department != scope["department"]:
        _problem(403, "TASK_DEPARTMENT_FORBIDDEN", "当前账号无权维护该部门的关键任务")


def _task_is_visible(task, scope):
    if scope["canViewAll"]:
        return True
    if not isinstance(task, dict) or task.get("department") != scope["department"]:
        return False
    if scope["role"] == "department_leader":
        return True
    if scope["role"] != "member":
        return False
    user_name = normalize_person_name(scope["userName"])
    return user_name in {
        normalize_person_name(task.get("owner")),
        normalize_person_name(task.get("createdBy")),
    }


def _assert_task_access(scope, task):
    if not _task_is_visible(task, scope):
        _problem(403, "TASK_OWNER_FORBIDDEN", "当前账号只能维护本人负责的关键任务")


def _normalize_task_input(raw, scope):
    if not isinstance(raw, dict):
        _problem(400, "INVALID_TASK", "任务内容格式不正确")
    department = _text(raw.get("department"), "所属部门", 40, required=True)
    project = _text(raw.get("project"), "关键专项", 60, required=True)
    if department not in _DEPARTMENT_SET:
        _problem(400, "INVALID_TASK", "所属部门不在经营分析范围内")
    if project not in _PROJECT_SET:
        _problem(400, "INVALID_TASK", "关键专项不存在")
    _assert_department_access(scope, department)
    normalized = {
        "department": department,
        "project": project,
        "task": _text(raw.get("task"), "具体任务", 300, required=True),
        "owner": _text(raw.get("owner"), "负责人", 80),
        "output": _text(raw.get("output"), "最新具体产出", 500),
        "nextCheckpoint": _text(raw.get("nextCheckpoint"), "下一检查点", 500),
        "risk": _text(raw.get("risk"), "风险或阻塞", 500),
        "status": _text(raw.get("status"), "任务状态", 40) or "not_started",
    }
    if scope["role"] == "member":
        requested_owner = normalize_person_name(normalized["owner"])
        current_user = normalize_person_name(scope["userName"])
        if requested_owner and requested_owner != current_user:
            _problem(403, "TASK_OWNER_FORBIDDEN", "普通成员只能为本人创建关键任务")
        normalized["owner"] = scope["userName"]
    if normalized["status"] not in _STATUS_SET:
        _problem(400, "INVALID_TASK", "任务状态不存在")
    return normalized


def _empty_document():
    return {"version": 1, "updatedAt": None, "tasks": []}


def _normalize_document(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list):
        return _empty_document()
    return {
        "version": 1,
        "updatedAt": raw.get("updatedAt") if isinstance(raw.get("updatedAt"), str) else None,
        "tasks": [item for item in raw["tasks"] if isinstance(item, dict)],
    }


class KeyTaskStore:
    def __init__(self, file_path):
        self.file_path = os.path.abspath(file_path)
        self._lock = RLock()

    def _read(self):
        try:
            with open(self.file_path, "r", encoding="utf-8") as handle:
                return _normalize_document(json.load(handle))
        except FileNotFoundError:
            return _empty_document()
        except json.JSONDecodeError:
            _problem(500, "TASK_FILE_INVALID", "关键任务 JSON 文件格式无效")

    def _write(self, document):
        directory = os.path.dirname(self.file_path)
        os.makedirs(directory, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix="key-tasks-",
                suffix=".tmp",
                dir=directory,
                delete=False,
            ) as handle:
                temporary_path = handle.name
                json.dump(document, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.file_path)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _envelope(document, scope):
        tasks = [item for item in document["tasks"] if _task_is_visible(item, scope)]
        return {
            "version": document["version"],
            "updatedAt": document["updatedAt"],
            "tasks": tasks,
            "meta": {
                "departments": list(KEY_TASK_DEPARTMENTS),
                "departmentOwners": dict(KEY_TASK_DEPARTMENT_OWNERS),
                "projects": [dict(item) for item in KEY_TASK_PROJECTS],
                "statuses": [dict(item) for item in KEY_TASK_STATUSES],
                "scope": scope,
            },
        }

    def list(self, raw_scope):
        scope = _normalize_scope(raw_scope)
        with self._lock:
            return self._envelope(self._read(), scope)

    def create(self, raw_input, raw_scope):
        scope = _normalize_scope(raw_scope)
        inputs = raw_input.get("tasks") if isinstance(raw_input, dict) and isinstance(raw_input.get("tasks"), list) else [raw_input]
        if not inputs or len(inputs) > 200:
            _problem(400, "INVALID_TASK_BATCH", "每次需提交 1 至 200 条任务")
        normalized = [_normalize_task_input(item, scope) for item in inputs]
        with self._lock:
            document = self._read()
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            created = [
                {
                    "id": str(uuid4()),
                    **item,
                    "createdAt": now,
                    "updatedAt": now,
                    "createdBy": scope["userName"],
                    "updatedBy": scope["userName"],
                }
                for item in normalized
            ]
            document["tasks"].extend(created)
            document["updatedAt"] = now
            self._write(document)
        return {"created": created, "count": len(created)}

    def update(self, task_id, raw_input, raw_scope):
        scope = _normalize_scope(raw_scope)
        normalized = _normalize_task_input(raw_input, scope)
        with self._lock:
            document = self._read()
            index = next((idx for idx, item in enumerate(document["tasks"]) if item.get("id") == task_id), -1)
            if index < 0:
                _problem(404, "TASK_NOT_FOUND", "关键任务不存在或已被删除")
            current = document["tasks"][index]
            _assert_task_access(scope, current)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            updated = dict(current)
            updated.update({field: normalized[field] for field in _ALLOWED_FIELDS})
            updated.update({"updatedAt": now, "updatedBy": scope["userName"]})
            document["tasks"][index] = updated
            document["updatedAt"] = now
            self._write(document)
        return {"task": updated}

    def remove(self, task_id, raw_scope):
        scope = _normalize_scope(raw_scope)
        with self._lock:
            document = self._read()
            index = next((idx for idx, item in enumerate(document["tasks"]) if item.get("id") == task_id), -1)
            if index < 0:
                _problem(404, "TASK_NOT_FOUND", "关键任务不存在或已被删除")
            _assert_task_access(scope, document["tasks"][index])
            removed = document["tasks"].pop(index)
            document["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._write(document)
        return {"removed": removed}
