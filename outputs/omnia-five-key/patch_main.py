"""Narrow patches applied independently to local, runtime and image baselines."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def patch(source: str) -> str:
    if "@managed_omnia_call(" in source:
        raise ValueError("Five-key integration is already present")
    source = _load("runtime_patch", ROOT / "patch_task_runtime.py").patch(source)
    source = _load("balance_route_patch", ROOT.parent / "balance-management" / "patch_main.py").patch(source)
    newline = "\r\n" if "\r\n" in source else "\n"

    def replace(old, new):
        nonlocal source
        old, new = old.replace("\n", newline), new.replace("\n", newline)
        if source.count(old) != 1:
            raise ValueError(f"Expected one integration anchor: {old[:100]!r}")
        source = source.replace(old, new, 1)

    anchor = "from 图片.request_limits import admitted_job, get_request_limiter, limited_request, request_wait_callback\n"
    replace(anchor, anchor +
            "from 图片.omnia_key_pool import current_omnia_credential\n"
            "from 图片.omnia_service import (\n"
            "    managed_omnia_call, record_omnia_task, record_omnia_provider_status,\n"
            "    current_omnia_call_metadata, record_omnia_model,\n"
            ")\n")
    replace("def load_omnia_api_key() -> str:\n", "def load_omnia_api_key() -> str:\n"
            "    credential = current_omnia_credential()\n"
            "    if credential is not None:\n"
            "        return credential.api_key\n")
    for name, old in [("REMOVE_EYELASHES_MAX_API_CONCURRENCY", 1), ("HD_BATCH_MAX_API_CONCURRENCY", 1),
                      ("MAX_BATCH_API_CONCURRENCY", 4), ("DEFAULT_BATCH_API_CONCURRENCY", 4)]:
        replace(f"{name} = {old}\n", f"{name} = 5\n")
    for name, kind, resume in [("call_omnia_sync_image_api", "image", False),
                                ("call_omnia_media_image_api", "image", False),
                                ("resume_omnia_image_task", "image", True),
                                ("call_omnia_chat_api", "text", False)]:
        replace(f"def {name}(", f'@managed_omnia_call(kind="{kind}", resume={resume})\ndef {name}(')
    replace('        "idempotency_key": headers["Idempotency-Key"],\n',
            '        "idempotency_key": headers["Idempotency-Key"],\n'
            '        **current_omnia_call_metadata(),\n')
    replace("    return collect_omnia_image_task(task_id, create_data, api_key, omnia_model, normalized_resolution)\n",
            "    try:\n"
            "        record_omnia_task(task_id)\n"
            "    except Exception as exc:\n"
            "        raise OmniaImageOutcomeUnknown(\n"
            '            f"OmniaKey 任务已提交（任务 {task_id}），通道回执关联失败，请继续查询原任务，未自动重新提交。"\n'
            "        ) from exc\n"
            "    return collect_omnia_image_task(task_id, create_data, api_key, omnia_model, normalized_resolution)\n")
    replace('        if status == "succeeded":\n            break\n        if status in {"failed", "canceled", "cancelled"}:\n',
            '        if status == "succeeded":\n            record_omnia_provider_status("success")\n            break\n'
            '        if status in {"failed", "canceled", "cancelled"}:\n            record_omnia_provider_status("failed")\n')
    replace('    images = []\n    for item in data.get("data") or []:\n',
            '    record_omnia_provider_status("success")\n    images = []\n    for item in data.get("data") or []:\n')
    replace("    for index, candidate_model in enumerate(candidate_models):\n        try:\n",
            "    for index, candidate_model in enumerate(candidate_models):\n"
            "        record_omnia_model(candidate_model)\n        try:\n")
    replace("    render_balance_management(SimpleNamespace(st=st), load_balance_snapshot)\n",
            "    render_balance_management(\n"
            "        SimpleNamespace(st=st),\n"
            "        lambda force=False: load_balance_snapshot(force=force, primary_loader=load_omnia_api_key),\n"
            "    )\n")
    # Local validation has not sent a paid request. Mark the transition to
    # uncertain immediately before sending; an explicit rejection can settle 0.
    def change_function(name, edits):
        nonlocal source
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
        lines = source.splitlines(keepends=True)
        block = "".join(lines[node.lineno - 1:node.end_lineno]).replace("\r\n", "\n")
        for old, new in edits:
            if block.count(old) != 1:
                raise ValueError(f"Unexpected billing hook anchor in {name}: {old[:80]!r}")
            block = block.replace(old, new, 1)
        source = "".join(lines[:node.lineno - 1]) + block.replace("\n", newline) + "".join(lines[node.end_lineno:])

    initial = ('    api_key = load_omnia_api_key()\n',
               '    record_omnia_provider_status("rejected")\n    api_key = load_omnia_api_key()\n')
    change_function("call_omnia_sync_image_api", [initial,
        ('    try:\n        response = requests.post(', '    record_omnia_provider_status("uncertain")\n    try:\n        response = requests.post('),
        ('    if response.status_code >= 400 or data.get("error"):\n',
         '    if response.status_code >= 400 or data.get("error"):\n'
         '        record_omnia_provider_status("rejected" if response.status_code >= 400 else "failed")\n'),
    ])
    change_function("call_omnia_media_image_api", [
        ('    omnia_model = resolve_omnia_image_model(model)\n',
         '    record_omnia_provider_status("rejected")\n    omnia_model = resolve_omnia_image_model(model)\n'),
        ('    for attempt_index in range(normalized_max_attempts):\n',
         '    record_omnia_provider_status("uncertain")\n    for attempt_index in range(normalized_max_attempts):\n'),
        ('    if response.status_code >= 400:\n',
         '    if response.status_code >= 400:\n        record_omnia_provider_status("rejected")\n'),
    ])
    change_function("call_omnia_chat_api", [initial,
        ('        record_omnia_model(candidate_model)\n        try:\n',
         '        record_omnia_model(candidate_model)\n        record_omnia_provider_status("uncertain")\n        try:\n'),
        ('            last_error = RuntimeError(f"OmniaKey 响应解析失败（HTTP {response.status_code}）。")\n',
         '            record_omnia_provider_status("rejected")\n'
         '            last_error = RuntimeError(f"OmniaKey 响应解析失败（HTTP {response.status_code}）。")\n'),
        ('            last_error = RuntimeError(\n',
         '            record_omnia_provider_status("rejected" if explicit_rejection or 400 <= response.status_code < 500 else "failed")\n'
         '            last_error = RuntimeError(\n'),
    ])
    ast.parse(source)
    compile(source, "<five-key-main>", "exec")
    return source


def patch_limits(source: str) -> str:
    replacements = [('"omnia_image": 1,', '"omnia_image": 5,'),
                    ('_env_number("XIAOHA_OMNIA_CONCURRENCY", 2, 1, 16)',
                     '_env_number("XIAOHA_OMNIA_CONCURRENCY", 5, 1, 5)'),
                    ('import threading\n', 'import threading\n'),
                    ('_logger = logging.getLogger(__name__)\n',
                     '_logger = logging.getLogger(__name__)\n_limiter_init_lock = threading.Lock()\n'),
                    ('            connection.execute("PRAGMA journal_mode=WAL")\n',
                     '            deadline = time.monotonic() + 10\n'
                     '            while True:\n'
                     '                try:\n'
                     '                    connection.execute("PRAGMA journal_mode=WAL")\n'
                     '                    break\n'
                     '                except sqlite3.OperationalError as exc:\n'
                     '                    if not any(word in str(exc).lower() for word in ("locked", "busy")) or time.monotonic() >= deadline:\n'
                     '                        raise\n'
                     '                    time.sleep(0.05)\n'),
                    ('    return _cached_limiter(path)\n',
                     '    with _limiter_init_lock:\n        return _cached_limiter(path)\n')]
    newline = "\r\n" if "\r\n" in source else "\n"
    for old, new in replacements:
        old, new = old.replace("\n", newline), new.replace("\n", newline)
        if source.count(old) != 1:
            raise ValueError("Unexpected request limiter baseline")
        source = source.replace(old, new, 1)
    compile(source, "<five-key-limits>", "exec")
    return source


if __name__ == "__main__":
    for baseline in ("local", "runtime", "image"):
        dest = ROOT / f"{baseline}-release"
        dest.mkdir(exist_ok=True)
        for name, operation in [("openrouter_image_site.py", patch), ("request_limits.py", patch_limits)]:
            with (ROOT / f"before-{baseline}" / name).open(encoding="utf-8-sig", newline="") as stream:
                result = operation(stream.read())
            with (dest / name).open("w", encoding="utf-8", newline="") as stream:
                stream.write(result)
        print(baseline + ": patched main and limiter")
