"""360 价值评价网页功能。

业务规则迁移自“评价人使用-全员”工作簿。身份只取当前飞书会话中的用户名，
不读取服务器或访问者的计算机名。
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import pytds
from flask import Blueprint, jsonify, render_template, request, session, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from bjc import sf_db
from department_permissions import permission_manager, require_permission
from secret_settings import sql_server_config


value_evaluation_bp = Blueprint("value_evaluation", __name__)
PERMISSION_KEY = "value_evaluation"
ADMIN_PERMISSION_KEY = "value_evaluation_admin"
EVALUATION_PUBLIC_URL = "http://223.78.73.100:8000/ai/value-evaluation"

RELATIONSHIP_GROUPS = ("上级", "平级", "下级", "自评")
DIMENSION_RELATIONSHIP_WEIGHTS = {
    "1-01": {"上级": 45, "平级": 20, "下级": 35, "自评": 0},
    "1-02": {"上级": 40, "平级": 25, "下级": 35, "自评": 0},
    "1-03": {"上级": 45, "平级": 30, "下级": 25, "自评": 0},
    "1-04": {"上级": 25, "平级": 25, "下级": 50, "自评": 0},
    "1-05": {"上级": 35, "平级": 30, "下级": 35, "自评": 0},
    "1-06": {"上级": 55, "平级": 25, "下级": 20, "自评": 0},
    "1-07": {"上级": 35, "平级": 40, "下级": 25, "自评": 0},
    "1-08": {"上级": 25, "平级": 25, "下级": 50, "自评": 0},
    "1-09": {"上级": 25, "平级": 50, "下级": 25, "自评": 0},
    "1-10": {"上级": 45, "平级": 20, "下级": 35, "自评": 0},
    "1-11": {"上级": 30, "平级": 20, "下级": 50, "自评": 0},
    "1-12": {"上级": 35, "平级": 15, "下级": 50, "自评": 0},
    "1-13": {"上级": 40, "平级": 15, "下级": 45, "自评": 0},
    "1-14": {"上级": 55, "平级": 20, "下级": 25, "自评": 0},
    "1-15": {"上级": 40, "平级": 35, "下级": 25, "自评": 0},
}
DIMENSION_MODULES = {
    "品德素养": tuple(f"1-{index:02d}" for index in range(1, 6)),
    "作风行为": tuple(f"1-{index:02d}" for index in range(6, 11)),
    "使命担当": tuple(f"1-{index:02d}" for index in range(11, 14)),
    "责任履行": tuple(f"1-{index:02d}" for index in range(14, 16)),
}


def normalize_relationship_group(value: Any) -> str:
    relationship = _text(value)
    if "自评" in relationship or relationship in {"本人", "自己"}:
        return "自评"
    if "下级" in relationship or "直属下属" in relationship:
        return "下级"
    if "上级" in relationship or "直属领导" in relationship:
        return "上级"
    if "平级" in relationship or "同级" in relationship or "同事" in relationship:
        return "平级"
    return relationship


def _feishu_user_name() -> str:
    return str(session.get("feishu_user_name") or "").strip()


def _is_value_admin() -> bool:
    user_id = str(session.get("feishu_user_id") or "").strip()
    if not user_id:
        return False
    try:
        return bool(permission_manager.check_user_permission(user_id, ADMIN_PERMISSION_KEY)[0])
    except Exception:
        return False


def _admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _is_value_admin():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "当前账号没有360价值评价管理权限"}), 403
            return "当前账号没有360价值评价管理权限", 403
        return view(*args, **kwargs)

    return wrapped


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[tuple]:
    if not value:
        return []
    return [tuple(row) if isinstance(row, (tuple, list)) else (row,) for row in value]


_SCORE_DESCRIPTION_PATTERN = re.compile(r"(?m)^\s*([1-5])\s*分\s*[：:]\s*")


def split_criterion_description(description: str) -> tuple[str, dict[str, str]]:
    """将数据库中的整段评分说明拆成总体描述与1-5分说明。"""
    text = str(description or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    matches = list(_SCORE_DESCRIPTION_PATTERN.finditer(text))
    if not matches:
        return text, {}
    base = text[:matches[0].start()].strip()
    scores: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        scores[match.group(1)] = text[match.end():end].strip()
    return base, scores


def compose_criterion_description(base: str, scores: dict[str, Any]) -> str:
    base = _text(base)
    normalized = {str(score): _text((scores or {}).get(str(score))) for score in range(1, 6)}
    if not base:
        raise ValueError("总体描述不能为空")
    missing = [f"{score}分" for score in range(5, 0, -1) if not normalized[str(score)]]
    if missing:
        raise ValueError("请填写完整评分说明：" + "、".join(missing))
    return "\n".join([base] + [f"{score} 分：{normalized[str(score)]}" for score in range(5, 0, -1)])


def load_evaluation_state(user_name: str, query_fn=sf_db) -> dict[str, Any]:
    """读取当前飞书用户的未结束评价任务和评价项。"""
    if not _text(user_name):
        raise PermissionError("未获取到当前飞书用户名，请重新登录")

    batch_rows = _rows(query_fn(
        "SELECT MAX(DanHao) FROM JiaZhiGuan_AnPai WHERE JieShu='N'"
    ))
    batch_no = batch_rows[0][0] if batch_rows else None
    if batch_no in (None, ""):
        return {"batch_no": None, "user_name": user_name, "people": [], "criteria": []}

    assignments = _rows(query_fn(
        "SELECT BeiPingJiaRen,GuanXi FROM JiaZhiGuan_AnPai "
        f"WHERE PingJiaRen=N'{user_name.replace("'", "''")}' "
        f"AND DanHao=N'{str(batch_no).replace("'", "''")}' AND JieShu='N' "
        "ORDER BY BeiPingJiaRen"
    ))
    scored = set(_text(v) for v in (query_fn(
        "SELECT DISTINCT BeiPingJiaRen FROM JiaZhiGuan_DeFen "
        f"WHERE PingJiaRen=N'{user_name.replace("'", "''")}' "
        f"AND DanHao=N'{str(batch_no).replace("'", "''")}'"
    ) or []))
    criteria = _rows(query_fn(
        "SELECT DaiHao,DaXiang,XiaoXiang,NeiRong FROM JiaZhiGuan_NeiRong ORDER BY DaiHao"
    ))
    return {
        "batch_no": batch_no,
        "user_name": user_name,
        "people": [
            {"name": _text(row[0]), "relationship": _text(row[1]), "submitted": _text(row[0]) in scored}
            for row in assignments
        ],
        "criteria": [
            {"code": _text(row[0]), "category": _text(row[1]), "item": _text(row[2]), "description": _text(row[3])}
            for row in criteria
        ],
    }


def validate_submission(payload: dict[str, Any], criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    answers = payload.get("answers") if isinstance(payload, dict) else None
    if not isinstance(answers, list):
        raise ValueError("评价内容格式无效")
    answer_by_code = {_text(item.get("code")): item for item in answers if isinstance(item, dict)}
    normalized: list[dict[str, Any]] = []
    scores: list[int] = []
    for criterion in criteria:
        code = _text(criterion.get("code"))
        answer = answer_by_code.get(code, {})
        remark = _text(answer.get("remark"))
        raw_score = answer.get("score")
        if isinstance(raw_score, bool):
            raise ValueError(f"{criterion.get('item')}的得分必须是 1–5 的整数")
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            raise ValueError(f"{criterion.get('item')}的得分必须是 1–5 的整数")
        if score not in range(1, 6) or str(raw_score).strip() not in {"1", "2", "3", "4", "5"}:
            raise ValueError(f"{criterion.get('item')}的得分必须是 1–5 的整数")
        if score in (1, 5) and len(remark) < 20:
            raise ValueError(f"{criterion.get('item')}打 {score} 分时，原因不能少于 20 个字")
        scores.append(score)
        normalized.append({"code": code, "score": score, "remark": remark})
    if scores and len(set(scores)) == 1:
        raise ValueError(f"{len(scores)} 项评分不能全部相同")
    return normalized


_ASSIGNMENT_HEADER_ALIASES = {
    "单号": "batch_no", "批次": "batch_no", "批次号": "batch_no", "DanHao": "batch_no",
    "被评价人": "person", "被评人": "person", "BeiPingJiaRen": "person",
    "评价人": "evaluator", "PingJiaRen": "evaluator",
    "关系": "relationship", "GuanXi": "relationship",
    "匿名": "anonymous", "是否匿名": "anonymous", "NiMing": "anonymous",
}


def _read_assignment_table(file_storage) -> list[list[Any]]:
    filename = _text(getattr(file_storage, "filename", ""))
    raw = file_storage.read()
    if not raw:
        raise ValueError("上传文件为空")
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("明细文件不能超过5MB")
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix in {"xlsx", "xlsm"}:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = workbook.active
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    if suffix == "csv":
        text = None
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码无法识别，请另存为 UTF-8 CSV")
        return [list(row) for row in csv.reader(io.StringIO(text))]
    raise ValueError("仅支持 .xlsx、.xlsm 或 .csv 文件")


def parse_assignment_upload(file_storage, default_batch_no="") -> dict[str, Any]:
    rows = _read_assignment_table(file_storage)
    while rows and not any(_text(value) for value in rows[0]):
        rows.pop(0)
    if not rows:
        raise ValueError("文件中没有可导入数据")
    headers = [_text(value) for value in rows[0]]
    mapped = {}
    for index, header in enumerate(headers):
        key = _ASSIGNMENT_HEADER_ALIASES.get(header)
        if key and key not in mapped:
            mapped[key] = index
    missing = [label for key, label in (("person", "被评价人"), ("evaluator", "评价人"), ("relationship", "关系")) if key not in mapped]
    if missing:
        raise ValueError("缺少必需表头：" + "、".join(missing))

    result, seen, errors = [], set(), []
    default_batch_no = _text(default_batch_no)
    for row_number, row in enumerate(rows[1:], start=2):
        if not any(_text(value) for value in row):
            continue
        def value(key):
            idx = mapped.get(key)
            return _text(row[idx]) if idx is not None and idx < len(row) else ""
        item = {
            "batch_no": value("batch_no") or default_batch_no,
            "person": value("person"),
            "evaluator": value("evaluator"),
            "relationship": value("relationship"),
            "anonymous": (value("anonymous") or "N").upper(),
        }
        row_errors = []
        if not item["batch_no"] or len(item["batch_no"]) > 8:
            row_errors.append("单号为空或超过8个字符")
        if not item["person"] or len(item["person"]) > 5:
            row_errors.append("被评价人为空或超过5个字符")
        if not item["evaluator"] or len(item["evaluator"]) > 5:
            row_errors.append("评价人为空或超过5个字符")
        if not item["relationship"] or len(item["relationship"]) > 10:
            row_errors.append("关系为空或超过10个字符")
        if item["anonymous"] not in {"Y", "N"}:
            row_errors.append("匿名只能填写Y或N")
        key = (item["batch_no"], item["person"], item["evaluator"])
        if key in seen:
            row_errors.append("同一批次的被评价人和评价人重复")
        seen.add(key)
        if row_errors:
            errors.append({"row": row_number, "message": "；".join(row_errors)})
        else:
            result.append(item)
    if len(result) > 5000:
        raise ValueError("单次最多导入5000条安排")
    if not result and not errors:
        raise ValueError("文件中没有可导入数据")
    batches = sorted({row["batch_no"] for row in result})
    return {"rows": result, "errors": errors, "batches": batches, "count": len(result)}


def save_assignment_rows(rows: list[dict[str, Any]], close_other_batches=False) -> int:
    if not rows:
        raise ValueError("没有可导入的有效明细")
    batches = sorted({_text(row.get("batch_no")) for row in rows})
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        if close_other_batches:
            placeholders = ",".join(["%s"] * len(batches))
            cursor.execute(f"UPDATE JiaZhiGuan_AnPai SET JieShu='Y' WHERE JieShu='N' AND DanHao NOT IN ({placeholders})", tuple(batches))
        for batch in batches:
            cursor.execute("DELETE FROM JiaZhiGuan_AnPai WHERE DanHao=%s", (batch,))
        cursor.executemany(
            "INSERT INTO JiaZhiGuan_AnPai "
            "(DanHao,BeiPingJiaRen,PingJiaRen,GuanXi,NiMing,TianJiaShiJian,PingJiaShiJian,JieShu) "
            "VALUES (%s,%s,%s,%s,%s,GETDATE(),CONVERT(datetime,'1900-01-01'),'N')",
            [(row["batch_no"], row["person"], row["evaluator"], row["relationship"], row["anonymous"]) for row in rows],
        )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_criteria(query_fn=sf_db) -> list[dict[str, Any]]:
    items = []
    for row in _rows(query_fn("SELECT DaiHao,DaXiang,XiaoXiang,NeiRong FROM JiaZhiGuan_NeiRong ORDER BY DaiHao")):
        description = _text(row[3])
        base, score_descriptions = split_criterion_description(description)
        items.append({
            "code": _text(row[0]),
            "category": _text(row[1]),
            "item": _text(row[2]),
            "description": description,
            "base_description": base,
            "score_descriptions": score_descriptions,
        })
    return items


def save_criteria(items: list[dict[str, Any]]) -> int:
    existing_codes = {item["code"] for item in load_criteria()}
    submitted_codes = {_text(item.get("code")) for item in items if isinstance(item, dict)}
    if submitted_codes != existing_codes:
        raise ValueError("评价项代号不可新增、删除或修改")
    normalized = []
    for item in items:
        code, category, name, description = (_text(item.get(key)) for key in ("code", "category", "item", "description"))
        if not category or len(category) > 10:
            raise ValueError(f"{code} 的大项为空或超过10个字符")
        if not name or len(name) > 50:
            raise ValueError(f"{code} 的小项为空或超过50个字符")
        if not description or len(description) > 2000:
            raise ValueError(f"{code} 的内容为空或超过2000个字符")
        normalized.append((category, name, description, code))
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.executemany(
            "UPDATE JiaZhiGuan_NeiRong SET DaXiang=%s,XiaoXiang=%s,NeiRong=%s WHERE DaiHao=%s",
            normalized,
        )
        conn.commit()
        return len(normalized)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_one_criterion(item: dict[str, Any]) -> str:
    code, category, name = (_text(item.get(key)) for key in ("code", "category", "item"))
    if code.startswith("1-") and isinstance(item.get("score_descriptions"), dict):
        description = compose_criterion_description(
            item.get("base_description"),
            item.get("score_descriptions"),
        )
    else:
        description = _text(item.get("description") or item.get("base_description"))
    existing_codes = {row["code"] for row in load_criteria()}
    if code not in existing_codes:
        raise ValueError("评价项不存在，代号不可新增或修改")
    if not category or len(category) > 10:
        raise ValueError(f"{code} 的大项为空或超过10个字符")
    if not name or len(name) > 50:
        raise ValueError(f"{code} 的小项为空或超过50个字符")
    if not description or len(description) > 2000:
        raise ValueError(f"{code} 的内容为空或超过2000个字符")
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE JiaZhiGuan_NeiRong SET DaXiang=%s,XiaoXiang=%s,NeiRong=%s WHERE DaiHao=%s",
            (category, name, description, code),
        )
        conn.commit()
        return code
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _weight_number(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label}的权重必须是数字")
    if number < 0 or number > 10000:
        raise ValueError(f"{label}的权重必须在 0–10000 之间")
    return number


def load_evaluation_weights() -> dict[str, Any]:
    criteria = [item for item in load_criteria() if item["code"].startswith("1-")]
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT LeiXing,Jian,QuanZhong FROM JiaZhiGuan_QuanZhong"
        )
        saved = {(str(row[0]), str(row[1])): float(row[2]) for row in cursor.fetchall()}
        cursor.execute(
            "SELECT DISTINCT GuanXi FROM JiaZhiGuan_AnPai "
            "WHERE LTRIM(RTRIM(ISNULL(GuanXi,N'')))<>N'' ORDER BY GuanXi"
        )
        relationships = [_text(row[0]) for row in cursor.fetchall()]
    finally:
        conn.close()
    return {
        "criteria": [
            {**item, "weight": saved.get(("criterion", item["code"]), 1.0)}
            for item in criteria
        ],
        "relationships": [
            {"name": name, "weight": saved.get(("relationship", name), 1.0)}
            for name in relationships
        ],
    }


def save_evaluation_weights(payload: dict[str, Any]) -> None:
    current = load_evaluation_weights()
    valid_codes = {item["code"] for item in current["criteria"]}
    valid_relationships = {item["name"] for item in current["relationships"]}
    criteria = payload.get("criteria")
    relationships = payload.get("relationships")
    if not isinstance(criteria, list) or not isinstance(relationships, list):
        raise ValueError("权重数据格式无效")
    criterion_rows = []
    for item in criteria:
        code = _text(item.get("code")) if isinstance(item, dict) else ""
        if code not in valid_codes:
            raise ValueError(f"评价项 {code or '未知'} 不存在")
        criterion_rows.append(("criterion", code, _weight_number(item.get("weight"), code)))
    relationship_rows = []
    for item in relationships:
        name = _text(item.get("name")) if isinstance(item, dict) else ""
        if name not in valid_relationships:
            raise ValueError(f"关系 {name or '未知'} 不存在")
        relationship_rows.append(("relationship", name, _weight_number(item.get("weight"), name)))
    if {row[1] for row in criterion_rows} != valid_codes:
        raise ValueError("请完整提交所有评价项权重")
    if {row[1] for row in relationship_rows} != valid_relationships:
        raise ValueError("请完整提交所有关系权重")
    if not any(row[2] > 0 for row in criterion_rows):
        raise ValueError("至少一个评价项权重必须大于 0")
    if relationship_rows and not any(row[2] > 0 for row in relationship_rows):
        raise ValueError("至少一个关系权重必须大于 0")
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        for kind, key, weight in criterion_rows + relationship_rows:
            cursor.execute(
                "UPDATE JiaZhiGuan_QuanZhong SET QuanZhong=%s,GengXinShiJian=GETDATE() "
                "WHERE LeiXing=%s AND Jian=%s; "
                "IF @@ROWCOUNT=0 INSERT INTO JiaZhiGuan_QuanZhong "
                "(LeiXing,Jian,QuanZhong,GengXinShiJian) VALUES (%s,%s,%s,GETDATE())",
                (weight, kind, key, kind, key, weight),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def calculate_comprehensive_scores() -> dict[str, Any]:
    weights = load_evaluation_weights()
    criterion_items = [
        {"code": item["code"], "item": _text(item.get("item")) or item["code"]}
        for item in weights["criteria"]
    ]
    criterion_weights = {item["code"]: Decimal(str(item["weight"])) for item in weights["criteria"]}
    relationship_weights = {item["name"]: Decimal(str(item["weight"])) for item in weights["relationships"]}
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(DanHao) FROM JiaZhiGuan_AnPai WHERE JieShu='N'")
        row = cursor.fetchone()
        batch_no = row[0] if row else None
        if batch_no in (None, ""):
            return {"batch_no": None, "scores": [], "detail_criteria": criterion_items}
        cursor.execute(
            "SELECT BeiPingJiaRen,PingJiaRen,GuanXi FROM JiaZhiGuan_AnPai "
            "WHERE DanHao=%s AND JieShu='N'",
            (batch_no,),
        )
        assignments = [tuple(row) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT BeiPingJiaRen,PingJiaRen,DaiHao,DeFen FROM JiaZhiGuan_DeFen "
            "WHERE DanHao=%s AND DaiHao LIKE '1-%%'",
            (batch_no,),
        )
        score_rows = [tuple(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    assigned = defaultdict(int)
    evaluators_by_person = defaultdict(set)
    relation_by_evaluator = {}
    for person, evaluator, relationship in assignments:
        person, evaluator, relationship = _text(person), _text(evaluator), _text(relationship)
        assigned[person] += 1
        relation_by_evaluator[(person, evaluator)] = relationship
    answers = defaultdict(dict)
    for person, evaluator, code, score in score_rows:
        code = _text(code)
        if code in criterion_weights and score is not None:
            answers[(_text(person), _text(evaluator))][code] = Decimal(str(score))

    person_evaluations = defaultdict(list)
    for key, item_scores in answers.items():
        numerator = sum(item_scores[code] * criterion_weights[code] for code in item_scores)
        denominator = sum(criterion_weights[code] for code in item_scores)
        if denominator <= 0:
            continue
        relationship = relation_by_evaluator.get(key, "")
        relation_weight = relationship_weights.get(relationship, Decimal("1"))
        if relation_weight > 0:
            person_evaluations[key[0]].append((numerator / denominator, relation_weight))

    results = []
    for person in sorted(assigned):
        evaluations = person_evaluations.get(person, [])
        denominator = sum((weight for _, weight in evaluations), Decimal("0"))
        score = (sum((value * weight for value, weight in evaluations), Decimal("0")) / denominator) if denominator else None
        results.append({
            "person": person,
            "score": round(float(score), 2) if score is not None else None,
            "submitted_count": len(evaluations),
            "assigned_count": assigned[person],
        })
    results.sort(key=lambda item: (item["score"] is None, -(item["score"] or 0), item["person"]))
    return {"batch_no": batch_no, "scores": results}


def send_evaluation_notifications(evaluation_url: str, sender=None) -> dict[str, Any]:
    """Notify each evaluator who still has unfinished people in the active batch."""
    from innovation.message_service import MessageService

    valid_codes = {
        item["code"] for item in load_criteria()
        if item["code"] in DIMENSION_RELATIONSHIP_WEIGHTS
    }
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(DanHao) FROM JiaZhiGuan_AnPai WHERE JieShu='N'")
        row = cursor.fetchone()
        batch_no = row[0] if row else None
        if batch_no in (None, ""):
            return {"batch_no": None, "notified": 0, "failed": [], "skipped": 0}
        cursor.execute(
            "SELECT BeiPingJiaRen,PingJiaRen FROM JiaZhiGuan_AnPai "
            "WHERE DanHao=%s AND JieShu='N'",
            (batch_no,),
        )
        assignments = {(_text(person), _text(evaluator)) for person, evaluator in cursor.fetchall()}
        cursor.execute(
            "SELECT DISTINCT BeiPingJiaRen,PingJiaRen,DaiHao FROM JiaZhiGuan_DeFen WHERE DanHao=%s",
            (batch_no,),
        )
        submitted = {
            (_text(person), _text(evaluator))
            for person, evaluator, code in cursor.fetchall()
            if _text(code) in valid_codes
        }
    finally:
        conn.close()

    pending_by_evaluator = defaultdict(set)
    for person, evaluator in assignments - submitted:
        if evaluator:
            pending_by_evaluator[evaluator].add(person)
    send = sender or MessageService("company1").send_message
    notified = []
    failed = []
    for evaluator in sorted(pending_by_evaluator):
        people = sorted(pending_by_evaluator[evaluator])
        message = (
            "【360评价提醒】\n"
            f"当前批次：{batch_no}\n"
            f"您还有 {len(people)} 人待评价：{'、'.join(people)}\n"
            "本次评价共15个维度，请基于实际工作表现客观打分。\n"
            f"评价入口：{evaluation_url}"
        )
        try:
            success = bool(send(evaluator, message))
            error = "" if success else "飞书消息发送失败"
        except Exception as exc:
            success = False
            error = str(exc)
        if success:
            notified.append(evaluator)
        else:
            failed.append({"name": evaluator, "error": error})
    completed_evaluators = {
        evaluator for _, evaluator in assignments
        if evaluator and evaluator not in pending_by_evaluator
    }
    return {
        "batch_no": batch_no,
        "notified": len(notified),
        "notified_names": notified,
        "failed": failed,
        "skipped": len(completed_evaluators),
    }


def _save_submission(batch_no: Any, person: str, user_name: str, answers: list[dict[str, Any]]) -> None:
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM JiaZhiGuan_AnPai WHERE DanHao=%s AND BeiPingJiaRen=%s "
            "AND PingJiaRen=%s AND JieShu='N'",
            (batch_no, person, user_name),
        )
        if int(cursor.fetchone()[0] or 0) == 0:
            raise PermissionError("当前评价任务不存在或已被关闭")
        cursor.execute(
            "DELETE FROM JiaZhiGuan_DeFen WHERE DanHao=%s AND BeiPingJiaRen=%s AND PingJiaRen=%s",
            (batch_no, person, user_name),
        )
        cursor.executemany(
            "INSERT INTO JiaZhiGuan_DeFen "
            "(DanHao,BeiPingJiaRen,PingJiaRen,DaiHao,DeFen,BeiZhu,PingJiaShiJian) "
            "VALUES (%s,%s,%s,%s,%s,%s,GETDATE())",
            [(batch_no, person, user_name, a["code"], a["score"], a["remark"]) for a in answers],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_evaluation_weights() -> dict[str, Any]:
    """Load item weights and the per-dimension relationship matrix."""
    criteria = [item for item in load_criteria() if item["code"].startswith("1-")]
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT LeiXing,Jian,QuanZhong FROM JiaZhiGuan_QuanZhong")
        saved = {(str(row[0]), str(row[1])): float(row[2]) for row in cursor.fetchall()}
    finally:
        conn.close()
    return {
        "criteria": [
            {
                **item,
                "weight": saved.get(("criterion", item["code"]), 1.0),
                "relationship_weights": {
                    group: saved.get(
                        ("criterion_relationship", f"{item['code']}|{group}"),
                        DIMENSION_RELATIONSHIP_WEIGHTS.get(item["code"], {}).get(group, 0),
                    )
                    for group in RELATIONSHIP_GROUPS
                },
            }
            for item in criteria
        ],
        "relationships": [{"name": group} for group in RELATIONSHIP_GROUPS],
    }


def save_evaluation_weights(payload: dict[str, Any]) -> None:
    current = load_evaluation_weights()
    valid_codes = {item["code"] for item in current["criteria"]}
    criteria = payload.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError("权重数据格式无效")
    criterion_rows = []
    matrix_rows = []
    for item in criteria:
        code = _text(item.get("code")) if isinstance(item, dict) else ""
        if code not in valid_codes:
            raise ValueError(f"评价项 {code or '未知'} 不存在")
        criterion_rows.append(("criterion", code, _weight_number(item.get("weight", 1), code)))
        relation_weights = item.get("relationship_weights") if isinstance(item, dict) else None
        if not isinstance(relation_weights, dict):
            raise ValueError(f"请完整提交 {code} 的关系权重")
        normalized = {
            group: _weight_number(relation_weights.get(group), f"{code}·{group}")
            for group in RELATIONSHIP_GROUPS
        }
        if normalized["自评"] != 0:
            raise ValueError("自评权重必须为 0")
        if not any(normalized[group] > 0 for group in ("上级", "平级", "下级")):
            raise ValueError(f"{code} 至少一个他评关系权重必须大于 0")
        matrix_rows.extend(
            ("criterion_relationship", f"{code}|{group}", weight)
            for group, weight in normalized.items()
        )
    if {row[1] for row in criterion_rows} != valid_codes:
        raise ValueError("请完整提交所有评价项权重")
    if not any(row[2] > 0 for row in criterion_rows):
        raise ValueError("至少一个评价项权重必须大于 0")
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        for kind, key, weight in criterion_rows + matrix_rows:
            cursor.execute(
                "UPDATE JiaZhiGuan_QuanZhong SET QuanZhong=%s,GengXinShiJian=GETDATE() "
                "WHERE LeiXing=%s AND Jian=%s; "
                "IF @@ROWCOUNT=0 INSERT INTO JiaZhiGuan_QuanZhong "
                "(LeiXing,Jian,QuanZhong,GengXinShiJian) VALUES (%s,%s,%s,GETDATE())",
                (weight, kind, key, kind, key, weight),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def calculate_comprehensive_scores() -> dict[str, Any]:
    """Calculate role means, dimension scores, module scores, and the final score."""
    weights = load_evaluation_weights()
    criterion_items = [
        {"code": item["code"], "item": _text(item.get("item")) or item["code"]}
        for item in weights["criteria"]
    ]
    criterion_weights = {item["code"]: Decimal(str(item["weight"])) for item in weights["criteria"]}
    relationship_weights = {
        item["code"]: {
            group: Decimal(str(item["relationship_weights"].get(group, 0)))
            for group in RELATIONSHIP_GROUPS
        }
        for item in weights["criteria"]
    }
    conn = pytds.connect(**sql_server_config())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(DanHao) FROM JiaZhiGuan_AnPai WHERE JieShu='N'")
        row = cursor.fetchone()
        batch_no = row[0] if row else None
        if batch_no in (None, ""):
            return {"batch_no": None, "scores": [], "detail_criteria": criterion_items}
        cursor.execute(
            "SELECT BeiPingJiaRen,PingJiaRen,GuanXi FROM JiaZhiGuan_AnPai "
            "WHERE DanHao=%s AND JieShu='N'",
            (batch_no,),
        )
        assignments = [tuple(row) for row in cursor.fetchall()]
        cursor.execute(
            "SELECT BeiPingJiaRen,PingJiaRen,DaiHao,DeFen FROM JiaZhiGuan_DeFen "
            "WHERE DanHao=%s AND DaiHao LIKE '1-%%'",
            (batch_no,),
        )
        score_rows = [tuple(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    assigned = defaultdict(int)
    evaluators_by_person = defaultdict(set)
    relation_by_evaluator = {}
    for person, evaluator, relationship in assignments:
        person, evaluator = _text(person), _text(evaluator)
        assigned[person] += 1
        evaluators_by_person[person].add(evaluator)
        relation_by_evaluator[(person, evaluator)] = normalize_relationship_group(relationship)

    grouped_scores = defaultdict(list)
    evaluator_scores = defaultdict(dict)
    submitted_evaluators = defaultdict(set)
    for person, evaluator, code, score in score_rows:
        person, evaluator, code = _text(person), _text(evaluator), _text(code)
        if code not in criterion_weights or score is None:
            continue
        group = relation_by_evaluator.get((person, evaluator), "")
        submitted_evaluators[person].add(evaluator)
        grouped_scores[(person, code, group)].append(Decimal(str(score)))
        evaluator_scores[(person, evaluator)][code] = Decimal(str(score))

    results = []
    for person in sorted(assigned):
        dimension_scores = {}
        self_scores = {}
        for code in criterion_weights:
            group_means = {}
            for group in RELATIONSHIP_GROUPS:
                values = grouped_scores.get((person, code, group), [])
                if values:
                    group_means[group] = sum(values, Decimal("0")) / Decimal(len(values))
            if "自评" in group_means:
                self_scores[code] = round(float(group_means["自评"]), 2)
            numerator = Decimal("0")
            denominator = Decimal("0")
            for group in ("上级", "平级", "下级"):
                if group in group_means:
                    weight = relationship_weights.get(code, {}).get(group, Decimal("0"))
                    numerator += group_means[group] * weight
                    denominator += weight
            if denominator > 0:
                dimension_scores[code] = numerator / denominator

        weighted_dimensions = [
            (value, criterion_weights[code])
            for code, value in dimension_scores.items()
            if criterion_weights.get(code, Decimal("0")) > 0
        ]
        total_weight = sum((weight for _, weight in weighted_dimensions), Decimal("0"))
        score = (
            sum((value * weight for value, weight in weighted_dimensions), Decimal("0")) / total_weight
            if total_weight else None
        )
        module_scores = {}
        for module_name, codes in DIMENSION_MODULES.items():
            values = [dimension_scores[code] for code in codes if code in dimension_scores]
            module_scores[module_name] = (
                round(float(sum(values, Decimal("0")) / Decimal(len(values))), 2)
                if values else None
            )
        evaluator_details = []
        for index, evaluator in enumerate(sorted(evaluators_by_person[person])):
            raw_scores = evaluator_scores.get((person, evaluator), {})
            weighted = [
                (value, criterion_weights[code])
                for code, value in raw_scores.items()
                if criterion_weights.get(code, Decimal("0")) > 0
            ]
            detail_weight = sum((weight for _, weight in weighted), Decimal("0"))
            detail_score = (
                sum((value * weight for value, weight in weighted), Decimal("0")) / detail_weight
                if detail_weight else None
            )
            alias_number = index
            alias = ""
            while True:
                alias = chr(ord("a") + alias_number % 26) + alias
                alias_number = alias_number // 26 - 1
                if alias_number < 0:
                    break
            evaluator_details.append({
                "evaluator_alias": alias,
                "scores": {code: round(float(value), 2) for code, value in raw_scores.items()},
                "score": round(float(detail_score), 2) if detail_score is not None else None,
                "submitted": bool(raw_scores),
            })
        results.append({
            "person": person,
            "score": round(float(score), 2) if score is not None else None,
            "module_scores": module_scores,
            "dimension_scores": {code: round(float(value), 2) for code, value in dimension_scores.items()},
            "self_scores": self_scores,
            "submitted_count": len(submitted_evaluators.get(person, set())),
            "assigned_count": assigned[person],
            "evaluator_details": evaluator_details,
        })
    results.sort(key=lambda item: (item["score"] is None, -(item["score"] or 0), item["person"]))
    return {"batch_no": batch_no, "scores": results, "detail_criteria": criterion_items}


def build_comprehensive_scores_workbook(data: dict[str, Any]) -> io.BytesIO:
    """Build the admin score export without exposing evaluator identities."""
    workbook = Workbook()
    summary = workbook.active
    summary.title = "综合得分"
    detail = workbook.create_sheet("评价人明细")
    header_fill = PatternFill("solid", fgColor="334155")
    header_font = Font(color="FFFFFF", bold=True)
    thin_gray = Side(style="thin", color="D7DEE8")
    border = Border(bottom=thin_gray)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    summary_headers = [
        "排名", "被评价人", "综合得分", "品德素养", "作风行为",
        "使命担当", "责任履行", "已提交", "应提交", "提交进度",
    ]
    summary.append(summary_headers)
    for rank, item in enumerate(data.get("scores") or [], start=1):
        score = item.get("score")
        modules = item.get("module_scores") or {}
        submitted = int(item.get("submitted_count") or 0)
        assigned = int(item.get("assigned_count") or 0)
        summary.append([
            rank if score is not None else None,
            item.get("person") or "",
            score,
            modules.get("品德素养"),
            modules.get("作风行为"),
            modules.get("使命担当"),
            modules.get("责任履行"),
            submitted,
            assigned,
            f"{submitted} / {assigned}",
        ])

    criteria = data.get("detail_criteria") or []
    detail_headers = ["被评价人", "评价人", "综合得分"] + [
        f"{item.get('code', '')} {item.get('item', '')}".strip() for item in criteria
    ] + ["状态"]
    detail.append(detail_headers)
    for item in data.get("scores") or []:
        for evaluator in item.get("evaluator_details") or []:
            raw_scores = evaluator.get("scores") or {}
            detail.append([
                item.get("person") or "",
                evaluator.get("evaluator_alias") or "",
                evaluator.get("score"),
                *[raw_scores.get(criterion.get("code")) for criterion in criteria],
                "已提交" if evaluator.get("submitted") else "待提交",
            ])

    for sheet in (summary, detail):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 34
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
                cell.alignment = center
                if isinstance(cell.value, float):
                    cell.number_format = "0.00"
        sheet.column_dimensions["A"].width = 12
        sheet.column_dimensions["B"].width = 16
        for column in range(3, sheet.max_column + 1):
            sheet.column_dimensions[chr(64 + column) if column <= 26 else "A" + chr(64 + column - 26)].width = 15
    summary.column_dimensions["B"].width = 18
    detail.column_dimensions["A"].width = 18
    detail.column_dimensions["B"].width = 12
    for row in summary.iter_rows(min_row=2):
        row[1].alignment = left
    for row in detail.iter_rows(min_row=2):
        row[0].alignment = left

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


@value_evaluation_bp.get("/ai/value-evaluation")
@require_permission(PERMISSION_KEY)
def page():
    if not _feishu_user_name():
        return "未获取到当前飞书用户名，请重新登录", 401
    return render_template("value_evaluation.html", user_name=_feishu_user_name(), is_value_admin=_is_value_admin())


@value_evaluation_bp.get("/api/ai/value-evaluation")
@require_permission(PERMISSION_KEY)
def state():
    try:
        return jsonify({"success": True, **load_evaluation_state(_feishu_user_name())})
    except PermissionError as exc:
        return jsonify({"success": False, "message": str(exc)}), 401
    except Exception:
        return jsonify({"success": False, "message": "评价任务加载失败，请稍后重试"}), 503


@value_evaluation_bp.get("/api/ai/value-evaluation/existing")
@require_permission(PERMISSION_KEY)
def existing():
    user_name, person = _feishu_user_name(), _text(request.args.get("person"))
    try:
        state_data = load_evaluation_state(user_name)
        allowed = {item["name"] for item in state_data["people"]}
        if person not in allowed:
            return jsonify({"success": False, "message": "无权评价该人员"}), 403
        rows = _rows(sf_db(
            "SELECT DaiHao,DeFen,BeiZhu FROM JiaZhiGuan_DeFen "
            f"WHERE DanHao=N'{str(state_data['batch_no']).replace("'", "''")}' "
            f"AND BeiPingJiaRen=N'{person.replace("'", "''")}' "
            f"AND PingJiaRen=N'{user_name.replace("'", "''")}'"
        ))
        return jsonify({"success": True, "answers": [
            {"code": _text(row[0]), "score": row[1], "remark": _text(row[2])} for row in rows
        ]})
    except Exception:
        return jsonify({"success": False, "message": "历史评价加载失败"}), 503


@value_evaluation_bp.post("/api/ai/value-evaluation/submit")
@require_permission(PERMISSION_KEY)
def submit():
    user_name = _feishu_user_name()
    if not user_name:
        return jsonify({"success": False, "message": "未获取到当前飞书用户名，请重新登录"}), 401
    payload = request.get_json(silent=True) or {}
    person = _text(payload.get("person"))
    try:
        state_data = load_evaluation_state(user_name)
        if person not in {item["name"] for item in state_data["people"]}:
            return jsonify({"success": False, "message": "无权评价该人员"}), 403
        answers = validate_submission(payload, state_data["criteria"])
        _save_submission(state_data["batch_no"], person, user_name, answers)
        return jsonify({"success": True, "message": "评价提交成功"})
    except (ValueError, PermissionError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "提交失败，请稍后重试"}), 503


@value_evaluation_bp.get("/ai/value-evaluation/admin")
@require_permission(PERMISSION_KEY)
@_admin_required
def admin_page():
    return render_template("value_evaluation_admin.html", user_name=_feishu_user_name())


@value_evaluation_bp.post("/api/ai/value-evaluation/admin/assignments/preview")
@require_permission(PERMISSION_KEY)
@_admin_required
def preview_assignments():
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"success": False, "message": "请选择要上传的明细文件"}), 400
    try:
        result = parse_assignment_upload(upload, request.form.get("batch_no", ""))
        return jsonify({"success": True, **result})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "文件解析失败，请检查格式"}), 400


@value_evaluation_bp.post("/api/ai/value-evaluation/admin/assignments/import")
@require_permission(PERMISSION_KEY)
@_admin_required
def import_assignments():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return jsonify({"success": False, "message": "导入明细格式无效"}), 400
    try:
        # 确认阶段再次执行与预检相同的字段约束，不能信任浏览器回传内容。
        checked = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("导入明细格式无效")
            item = {key: _text(row.get(key)) for key in ("batch_no", "person", "evaluator", "relationship", "anonymous")}
            item["anonymous"] = (item["anonymous"] or "N").upper()
            if not item["batch_no"] or len(item["batch_no"]) > 8:
                raise ValueError("存在无效单号")
            if not item["person"] or len(item["person"]) > 5 or not item["evaluator"] or len(item["evaluator"]) > 5:
                raise ValueError("存在无效人员姓名")
            if not item["relationship"] or len(item["relationship"]) > 10:
                raise ValueError("存在无效关系")
            if item["anonymous"] not in {"Y", "N"}:
                raise ValueError("匿名只能填写Y或N")
            key = (item["batch_no"], item["person"], item["evaluator"])
            if key in seen:
                raise ValueError("导入明细存在重复安排")
            seen.add(key)
            checked.append(item)
        count = save_assignment_rows(checked, bool(payload.get("close_other_batches")))
        return jsonify({"success": True, "message": f"已导入 {count} 条评价安排"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "导入失败，数据库未完成更新"}), 503


@value_evaluation_bp.get("/api/ai/value-evaluation/admin/criteria")
@require_permission(PERMISSION_KEY)
@_admin_required
def admin_criteria():
    try:
        return jsonify({"success": True, "items": load_criteria()})
    except Exception:
        return jsonify({"success": False, "message": "评价内容加载失败"}), 503


@value_evaluation_bp.put("/api/ai/value-evaluation/admin/criteria")
@require_permission(PERMISSION_KEY)
@_admin_required
def update_admin_criteria():
    payload = request.get_json(silent=True) or {}
    try:
        count = save_criteria(payload.get("items") if isinstance(payload.get("items"), list) else [])
        return jsonify({"success": True, "message": f"已更新 {count} 个评价项"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "评价内容保存失败"}), 503


@value_evaluation_bp.patch("/api/ai/value-evaluation/admin/criteria/<code>")
@require_permission(PERMISSION_KEY)
@_admin_required
def update_one_admin_criterion(code):
    payload = request.get_json(silent=True) or {}
    item = dict(payload) if isinstance(payload, dict) else {}
    item["code"] = _text(code)
    try:
        saved_code = save_one_criterion(item)
        return jsonify({"success": True, "message": f"{saved_code} 已单独保存"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": f"{_text(code)} 保存失败"}), 503


@value_evaluation_bp.get("/api/ai/value-evaluation/admin/weights")
@require_permission(PERMISSION_KEY)
@_admin_required
def admin_weights():
    try:
        return jsonify({"success": True, **load_evaluation_weights()})
    except Exception:
        return jsonify({"success": False, "message": "权重加载失败，请稍后重试"}), 503


@value_evaluation_bp.put("/api/ai/value-evaluation/admin/weights")
@require_permission(PERMISSION_KEY)
@_admin_required
def update_admin_weights():
    try:
        save_evaluation_weights(request.get_json(silent=True) or {})
        return jsonify({"success": True, "message": "权重保存成功"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        return jsonify({"success": False, "message": "权重保存失败，数据库未完成更新"}), 503


@value_evaluation_bp.get("/api/ai/value-evaluation/admin/comprehensive-scores")
@require_permission(PERMISSION_KEY)
@_admin_required
def admin_comprehensive_scores():
    try:
        return jsonify({"success": True, **calculate_comprehensive_scores()})
    except Exception:
        return jsonify({"success": False, "message": "综合得分计算失败，请稍后重试"}), 503


@value_evaluation_bp.get("/api/ai/value-evaluation/admin/comprehensive-scores/export")
@require_permission(PERMISSION_KEY)
@_admin_required
def export_admin_comprehensive_scores():
    try:
        data = calculate_comprehensive_scores()
        if data.get("batch_no") in (None, ""):
            return jsonify({"success": False, "message": "当前没有进行中的评价批次"}), 400
        output = build_comprehensive_scores_workbook(data)
        batch_no = re.sub(r"[^0-9A-Za-z_-]+", "_", str(data.get("batch_no") or "当前批次"))
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"360价值评价_{batch_no}.xlsx",
        )
    except Exception:
        return jsonify({"success": False, "message": "综合得分导出失败，请稍后重试"}), 503


@value_evaluation_bp.post("/api/ai/value-evaluation/admin/notify")
@require_permission(PERMISSION_KEY)
@_admin_required
def admin_notify_evaluators():
    try:
        result = send_evaluation_notifications(EVALUATION_PUBLIC_URL)
        if result["batch_no"] is None:
            return jsonify({"success": False, "message": "当前没有进行中的评价批次"}), 400
        message = f"通知完成：成功 {result['notified']} 人"
        if result["skipped"]:
            message += f"，已完成跳过 {result['skipped']} 人"
        if result["failed"]:
            message += f"，失败 {len(result['failed'])} 人"
        return jsonify({"success": not result["failed"], "message": message, **result}), (207 if result["failed"] else 200)
    except Exception:
        return jsonify({"success": False, "message": "飞书通知发送失败，请稍后重试"}), 503
