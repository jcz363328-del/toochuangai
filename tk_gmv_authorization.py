# -*- coding: utf-8 -*-
"""TK GMV 未授权视频 Excel 导入与飞书提醒。"""

from collections import OrderedDict, defaultdict
from decimal import Decimal, InvalidOperation
from io import BytesIO
import os
import re
import zipfile

import pandas as pd
import pytds
from flask import Blueprint, jsonify, render_template, request, session

from department_permissions import require_permission
from innovation.message_service import MessageService
from secret_settings import sql_server_config


tk_gmv_authorization_bp = Blueprint("tk_gmv_authorization", __name__)

_ALLOWED_EXTENSIONS = {".xlsx"}
_MAX_FILES = 20
_MAX_FILE_BYTES = 25 * 1024 * 1024
_MAX_TOTAL_FILE_BYTES = 100 * 1024 * 1024
_MAX_UNCOMPRESSED_XLSX_BYTES = 250 * 1024 * 1024
_MAX_TOTAL_ROWS = 200000
_MAX_REVENUE_ROWS = 5000
_DB_BATCH_SIZE = 500
_MESSAGE_MAX_CHARS = 12000


def _normalize_header(value):
    text = str(value or "").replace("\ufeff", "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _display_filename(value):
    return os.path.basename(str(value or "").replace("\\", "/")).strip() or "未命名文件.xlsx"


def _parse_revenue(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-", "--"}:
        return Decimal("0")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "").replace("\u00a0", "")
    text = re.sub(r"^[^0-9+\-.]+", "", text)
    text = re.sub(r"[^0-9eE+\-.]+$", "", text)
    if not text:
        return None
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return -amount if negative else amount


def _decimal_text(value):
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _normalize_video_id(value):
    if value is None:
        return ""
    text = str(value).strip().replace("\u00a0", "")
    if text.startswith("'"):
        text = text[1:].strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text


def _validate_xlsx_archive(payload):
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            total_size = sum(int(item.file_size or 0) for item in archive.infolist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("文件不是有效的 xlsx 工作簿") from exc
    if total_size > _MAX_UNCOMPRESSED_XLSX_BYTES:
        raise ValueError("工作簿解压后过大，请拆分文件后重试")


def _read_workbook(payload, filename):
    """返回工作簿中的记录、总行数和警告；不修改源文件。"""
    _validate_xlsx_archive(payload)
    records = []
    warnings = []
    total_rows = 0
    eligible_sheets = 0
    try:
        workbook = pd.ExcelFile(BytesIO(payload), engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"无法读取工作簿：{exc}") from exc

    for sheet_name in workbook.sheet_names:
        try:
            frame = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                dtype=str,
                keep_default_na=False,
            )
        except Exception as exc:
            warnings.append(f"{filename} / {sheet_name}：读取失败（{exc}）")
            continue

        total_rows += len(frame.index)
        lookup = {}
        for column in frame.columns:
            lookup.setdefault(_normalize_header(column), column)
        video_column = lookup.get("video id")
        revenue_column = lookup.get("gross revenue")
        if video_column is None or revenue_column is None:
            missing = []
            if video_column is None:
                missing.append("Video ID")
            if revenue_column is None:
                missing.append("Gross revenue")
            warnings.append(f"{filename} / {sheet_name}：缺少字段 {', '.join(missing)}，已跳过")
            continue

        eligible_sheets += 1
        for offset, (_, row) in enumerate(frame.iterrows(), start=2):
            amount = _parse_revenue(row.get(revenue_column))
            if amount is None:
                raw_amount = str(row.get(revenue_column) or "").strip()
                if raw_amount:
                    warnings.append(f"{filename} / {sheet_name} / 第{offset}行：Gross revenue 无法识别，已跳过")
                continue
            if amount == 0:
                continue
            video_id = _normalize_video_id(row.get(video_column))
            records.append({
                "filename": filename,
                "sheet": str(sheet_name),
                "row_number": offset,
                "video_id": video_id,
                "gross_revenue_decimal": amount,
                "gross_revenue": _decimal_text(amount),
            })

    if eligible_sheets == 0:
        raise ValueError("未找到同时包含 Video ID 和 Gross revenue 的工作表")
    return records, total_rows, warnings


def _query_video_mappings(video_ids):
    """批量查询视频、店铺、负责人及其个人飞书 open_id。"""
    result = defaultdict(list)
    ids = [str(one or "").strip() for one in video_ids if str(one or "").strip()]
    if not ids:
        return result

    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        for start in range(0, len(ids), _DB_BATCH_SIZE):
            batch = ids[start:start + _DB_BATCH_SIZE]
            placeholders = ",".join(["%s"] * len(batch))
            sql_text = f"""
                SELECT
                    LTRIM(RTRIM(CONVERT(NVARCHAR(100), v.ShiPinID))) AS shipinid,
                    LTRIM(RTRIM(CONVERT(NVARCHAR(255), v.Dian))) AS dian,
                    LTRIM(RTRIM(CONVERT(NVARCHAR(255), v.FuZeRen))) AS fuzeren,
                    LTRIM(RTRIM(CONVERT(NVARCHAR(255), f.FeiShu_ID))) AS feishu_id
                FROM v_TK_HeZuoShiPin v
                LEFT JOIN FeiShu_ID f
                  ON LTRIM(RTRIM(CONVERT(NVARCHAR(255), f.YongHu))) =
                     LTRIM(RTRIM(CONVERT(NVARCHAR(255), v.FuZeRen)))
                 AND f.FeiShu_ID LIKE 'ou[_]%%'
                WHERE LTRIM(RTRIM(CONVERT(NVARCHAR(100), v.ShiPinID))) IN ({placeholders})
            """
            cursor.execute(sql_text, tuple(batch))
            for row in cursor.fetchall() or []:
                video_id = str(row[0] or "").strip()
                mapping = {
                    "video_id": video_id,
                    "dian": str(row[1] or "").strip(),
                    "fuzeren": str(row[2] or "").strip(),
                    "feishu_id": str(row[3] or "").strip(),
                }
                key = (mapping["dian"], mapping["fuzeren"], mapping["feishu_id"])
                if video_id and not any(
                    (item["dian"], item["fuzeren"], item["feishu_id"]) == key
                    for item in result[video_id]
                ):
                    result[video_id].append(mapping)
    finally:
        connection.close()
    return result


def _notification_item_text(item):
    return (
        f"店铺：{item['dian']}\n"
        f"视频ID：{item['video_id']}\n"
        "该视频有GMV但是未授权，请在对应店铺广告后台绑定授权码"
    )


def _split_notification_items(items, max_chars=_MESSAGE_MAX_CHARS):
    chunks = []
    current = []
    current_length = len("GMV未授权视频提醒\n\n")
    for item in items:
        item_length = len(_notification_item_text(item)) + 2
        if current and current_length + item_length > max_chars:
            chunks.append(current)
            current = []
            current_length = len("GMV未授权视频提醒\n\n")
        current.append(item)
        current_length += item_length
    if current:
        chunks.append(current)
    return chunks


def _build_message(items):
    body = "\n\n".join(_notification_item_text(item) for item in items)
    return f"GMV未授权视频提醒\n\n{body}"


def _aggregate_records(records):
    grouped = OrderedDict()
    for record in records:
        video_id = record["video_id"]
        if not video_id:
            continue
        item = grouped.setdefault(video_id, {
            "video_id": video_id,
            "gross_revenue_values": [],
            "sources": [],
        })
        if record["gross_revenue"] not in item["gross_revenue_values"]:
            item["gross_revenue_values"].append(record["gross_revenue"])
        item["sources"].append({
            "filename": record["filename"],
            "sheet": record["sheet"],
            "row_number": record["row_number"],
            "gross_revenue": record["gross_revenue"],
        })
    for item in grouped.values():
        item["gross_revenue"] = "、".join(item["gross_revenue_values"])
    return grouped


def process_uploaded_workbooks(files, mapping_loader=None, message_service_factory=None):
    mapping_loader = mapping_loader or _query_video_mappings
    message_service_factory = message_service_factory or MessageService
    files = list(files or [])
    if not files:
        raise ValueError("请选择至少一个 xlsx 文件")
    if len(files) > _MAX_FILES:
        raise ValueError(f"一次最多上传 {_MAX_FILES} 个文件")

    all_records = []
    warnings = []
    file_results = []
    total_rows = 0
    total_bytes = 0
    processed_files = 0

    for uploaded in files:
        filename = _display_filename(getattr(uploaded, "filename", ""))
        extension = os.path.splitext(filename)[1].lower()
        if extension not in _ALLOWED_EXTENSIONS:
            file_results.append({"filename": filename, "success": False, "message": "仅支持 .xlsx 文件"})
            warnings.append(f"{filename}：仅支持 .xlsx 文件，已跳过")
            continue
        payload = uploaded.read()
        file_size = len(payload)
        total_bytes += file_size
        if total_bytes > _MAX_TOTAL_FILE_BYTES:
            raise ValueError("本次上传文件总大小不能超过 100 MB")
        if file_size <= 0:
            file_results.append({"filename": filename, "success": False, "message": "文件为空"})
            warnings.append(f"{filename}：文件为空，已跳过")
            continue
        if file_size > _MAX_FILE_BYTES:
            file_results.append({"filename": filename, "success": False, "message": "单个文件不能超过 25 MB"})
            warnings.append(f"{filename}：超过 25 MB，已跳过")
            continue
        try:
            records, row_count, one_warnings = _read_workbook(payload, filename)
        except ValueError as exc:
            file_results.append({"filename": filename, "success": False, "message": str(exc)})
            warnings.append(f"{filename}：{exc}")
            continue
        processed_files += 1
        total_rows += row_count
        if total_rows > _MAX_TOTAL_ROWS:
            raise ValueError("工作表总数据行数过多，请拆分后分批上传")
        all_records.extend(records)
        warnings.extend(one_warnings)
        file_results.append({
            "filename": filename,
            "success": True,
            "rows": row_count,
            "revenue_rows": len(records),
            "message": f"读取 {row_count} 行，发现 {len(records)} 行非零 GMV",
        })

    if processed_files == 0:
        first_error = next((one["message"] for one in file_results if not one["success"]), "没有可处理的文件")
        raise ValueError(first_error)
    if len(all_records) > _MAX_REVENUE_ROWS:
        raise ValueError(f"非零 GMV 行超过 {_MAX_REVENUE_ROWS} 行，请拆分后分批上传")

    missing_video_rows = [one for one in all_records if not one["video_id"]]
    grouped = _aggregate_records(all_records)
    mappings = mapping_loader(list(grouped.keys()))
    items = []
    notify_groups = defaultdict(list)
    matched_video_ids = set()

    for record in missing_video_rows:
        items.append({
            "filename": record["filename"],
            "sheet": record["sheet"],
            "row_number": record["row_number"],
            "video_id": "",
            "gross_revenue": record["gross_revenue"],
            "dian": "",
            "fuzeren": "",
            "status": "skipped",
            "status_text": "Video ID 为空，未推送",
        })

    for video_id, grouped_record in grouped.items():
        video_mappings = list(mappings.get(video_id) or [])
        source = grouped_record["sources"][0]
        if not video_mappings:
            items.append({
                "filename": source["filename"],
                "sheet": source["sheet"],
                "row_number": source["row_number"],
                "video_id": video_id,
                "gross_revenue": grouped_record["gross_revenue"],
                "source_count": len(grouped_record["sources"]),
                "sources": grouped_record["sources"],
                "dian": "",
                "fuzeren": "",
                "status": "not_found",
                "status_text": "数据库未找到该视频",
            })
            continue
        matched_video_ids.add(video_id)
        for mapping in video_mappings:
            result_item = {
                "filename": source["filename"],
                "sheet": source["sheet"],
                "row_number": source["row_number"],
                "video_id": video_id,
                "gross_revenue": grouped_record["gross_revenue"],
                "source_count": len(grouped_record["sources"]),
                "sources": grouped_record["sources"],
                "dian": str(mapping.get("dian") or "").strip(),
                "fuzeren": str(mapping.get("fuzeren") or "").strip(),
                "status": "pending",
                "status_text": "等待推送",
            }
            feishu_id = str(mapping.get("feishu_id") or "").strip()
            if not result_item["dian"]:
                result_item.update(status="skipped", status_text="店铺信息为空，未推送")
            elif not result_item["fuzeren"]:
                result_item.update(status="skipped", status_text="负责人为空，未推送")
            elif not feishu_id.startswith("ou_"):
                result_item.update(status="no_feishu", status_text="feishu_id 未找到负责人个人飞书ID")
            else:
                result_item["_feishu_id"] = feishu_id
                result_item["_notify_key"] = (feishu_id, result_item["dian"], video_id)
                notify_groups[feishu_id].append(result_item)
            items.append(result_item)

    message_service = message_service_factory()
    message_attempts = 0
    message_successes = 0
    message_results = []
    seen_notify_keys = set()
    for feishu_id, group_items in notify_groups.items():
        unique_items = []
        for item in group_items:
            notify_key = item["_notify_key"]
            if notify_key in seen_notify_keys:
                item.update(status="duplicate", status_text="重复记录，已合并推送")
                continue
            seen_notify_keys.add(notify_key)
            unique_items.append(item)
        for chunk in _split_notification_items(unique_items):
            message_attempts += 1
            message_content = _build_message(chunk)
            try:
                sent = bool(message_service.send_message(feishu_id, message_content))
            except Exception as exc:
                sent = False
                warnings.append(f"向 {chunk[0]['fuzeren']} 推送时发生异常：{exc}")
            if sent:
                message_successes += 1
            message_results.append({
                "batch_number": message_attempts,
                "fuzeren": chunk[0]["fuzeren"],
                "video_count": len(chunk),
                "video_ids": [item["video_id"] for item in chunk],
                "content": message_content,
                "status": "sent" if sent else "send_failed",
                "status_text": "飞书推送成功" if sent else "飞书推送失败",
            })
            for item in chunk:
                item["message_batch"] = message_attempts
                if sent:
                    item.update(status="sent", status_text="飞书推送成功")
                else:
                    item.update(status="send_failed", status_text="飞书推送失败")

    for item in items:
        item.pop("_feishu_id", None)
        item.pop("_notify_key", None)

    sent_count = sum(1 for item in items if item["status"] == "sent")
    failed_count = sum(1 for item in items if item["status"] in {"send_failed", "no_feishu", "not_found", "skipped"})
    summary = {
        "files_received": len(files),
        "files_processed": processed_files,
        "total_rows": total_rows,
        "revenue_rows": len(all_records),
        "unique_videos": len(grouped),
        "database_matched_videos": len(matched_video_ids),
        "notifications_sent": sent_count,
        "unresolved_items": failed_count,
        "messages_attempted": message_attempts,
        "messages_succeeded": message_successes,
    }
    if not all_records:
        message = "文件读取完成，未发现 Gross revenue 不为 0 的行，未发送消息"
    else:
        message = (
            f"处理完成：发现 {len(all_records)} 行非零 GMV，"
            f"成功推送 {sent_count} 条视频提醒，待处理 {failed_count} 条"
        )
    return {
        "success": True,
        "message": message,
        "summary": summary,
        "files": file_results,
        "items": items,
        "messages": message_results,
        "warnings": warnings[:200],
    }


@tk_gmv_authorization_bp.route("/tk_gmv_authorization_notify")
@require_permission("tk_project_group")
def page():
    return render_template(
        "tk_gmv_authorization_notify.html",
        user_name=session.get("feishu_user_name", "用户"),
        max_files=_MAX_FILES,
    )


@tk_gmv_authorization_bp.route("/api/tk_gmv_authorization_notify/process", methods=["POST"])
@require_permission("tk_project_group")
def process_files():
    files = request.files.getlist("files") or request.files.getlist("files[]")
    try:
        result = process_uploaded_workbooks(files)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "message": f"处理失败：{exc}"}), 500
