"""360 价值评价网页功能。

业务规则迁移自“评价人使用-全员”工作簿。身份只取当前飞书会话中的用户名，
不读取服务器或访问者的计算机名。
"""

from __future__ import annotations

from typing import Any

import pytds
from flask import Blueprint, jsonify, render_template, request, session

from bjc import sf_db
from department_permissions import require_permission
from secret_settings import sql_server_config


value_evaluation_bp = Blueprint("value_evaluation", __name__)
PERMISSION_KEY = "ai_dept"


def _feishu_user_name() -> str:
    return str(session.get("feishu_user_name") or "").strip()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[tuple]:
    if not value:
        return []
    return [tuple(row) if isinstance(row, (tuple, list)) else (row,) for row in value]


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
        if code.startswith("2-"):
            if not remark:
                raise ValueError(f"请填写“{criterion.get('description') or criterion.get('item')}”")
            normalized.append({"code": code, "score": 5, "remark": remark})
            continue
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
            raise ValueError(f"{criterion.get('item')}打 {score} 分时，备注不能少于 20 个字")
        scores.append(score)
        normalized.append({"code": code, "score": score, "remark": remark})
    if scores and len(set(scores)) == 1:
        raise ValueError("6 项评分不能全部相同")
    return normalized


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
            "(DanHao,BeiPingJiaRen,PingJiaRen,DaiHao,DeFen,BeiZhu,RiQi) "
            "VALUES (%s,%s,%s,%s,%s,%s,GETDATE())",
            [(batch_no, person, user_name, a["code"], a["score"], a["remark"]) for a in answers],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@value_evaluation_bp.get("/ai/value-evaluation")
@require_permission(PERMISSION_KEY)
def page():
    if not _feishu_user_name():
        return "未获取到当前飞书用户名，请重新登录", 401
    return render_template("value_evaluation.html", user_name=_feishu_user_name())


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
