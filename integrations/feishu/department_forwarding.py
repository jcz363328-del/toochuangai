"""Forward Feishu responses to departments and send prepress reports."""

from __future__ import annotations


def _parse_forward_departments(prompt_text):
    t = str(prompt_text or "").strip()
    if not t:
        return []
    if any(x in t for x in ["不发给领导", "不要发给领导", "别发给领导", "无需发给领导"]):
        return []
    targets = []
    candidates = [
        "AI部", "财务部", "人力行政部",
        "运营一部", "运营二部", "运营三部", "运营六部",
        "研发部", "技术部", "采购部", "摄影部", "视觉设计部",
        "内容生产工厂", "TK部门", "深圳团队", "仓储部", "短视频部", "BD部", "客服", "产品&店铺运营"
    ]
    for dep in candidates:
        if (f"发给{dep}" in t) or (f"给{dep}" in t) or (f"发到{dep}" in t) or (f"同步{dep}" in t):
            targets.append(dep)
    uniq = []
    seen = set()
    for x in targets:
        x = str(x or "").strip()
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _forward_text_to_departments(
    department_names,
    text,
    *,
    MessageService,
    _split_text,
):
    deps = department_names or []
    if not deps:
        return {"success": 0, "failed": 0, "total": 0, "departments": []}
    ms = MessageService("company1")
    summary = {"success": 0, "failed": 0, "total": 0, "departments": []}
    for dep in deps:
        dep_name = str(dep or "").strip()
        if not dep_name:
            continue
        sent = {"department": dep_name, "success": 0, "failed": 0, "total": 0}
        chunks = _split_text(text, max_len=1500)
        last_stats = None
        for chunk in chunks:
            last_stats = ms.send_message_to_department_members(dep_name, chunk, at_all=False)
        if isinstance(last_stats, dict):
            sent["success"] = int(last_stats.get("success") or 0)
            sent["failed"] = int(last_stats.get("failed") or 0)
            sent["total"] = int(last_stats.get("total") or 0)
        summary["success"] += sent["success"]
        summary["failed"] += sent["failed"]
        summary["total"] += sent["total"]
        summary["departments"].append(sent)
    return summary


def _feishu_send_prepress_report(
    chat_id,
    report,
    *,
    _feishu_send_text_to_chat,
):
    text = str(report or "").strip()
    if not text:
        return _feishu_send_text_to_chat(chat_id, "检查完成，但没有生成有效报告。")
    # 飞书文本消息留出 JSON 编码余量，长报告按完整行分段发送。
    chunks = []
    current = []
    current_length = 0
    for line in text.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > 3500:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length
    if current:
        chunks.append("\n".join(current))
    ok = True
    for index, chunk in enumerate(chunks):
        prefix = f"印前检查报告（{index + 1}/{len(chunks)}）\n" if len(chunks) > 1 else ""
        ok = _feishu_send_text_to_chat(chat_id, prefix + chunk) and ok
    return ok
