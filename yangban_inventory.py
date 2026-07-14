from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import json
import os
import re
import uuid

import pandas as pd
import pytds as sql
from flask import Blueprint, jsonify, render_template, request, send_file, send_from_directory, session

from department_permissions import require_permission
from secret_settings import sql_server_config


yangban_inventory_bp = Blueprint("yangban_inventory", __name__)

_DB_CONFIG = sql_server_config()

_SAMPLE_TABLE = "YangBan"
_FLOW_TABLE = "YangBan_LiuShui"
_TAG_TABLE = "YangBan_BiaoQian"
_LOCATION_TABLE = "YangBan_KuWei"
_VALID_FLOW_TYPES = {"RuKu", "ChuKu", "GuiHuan", "PanDian"}
_SAMPLE_STATUSES = {"ZhengChang", "TingYong"}
_TAG_STATUSES = {"ZhengChang", "TingYong"}
_LOCATION_TYPES = {"Gui", "Ceng", "Ge"}
_LOCATION_STATUSES = {"ZhengChang", "TingYong"}
_SAMPLE_IMAGE_DIR = r"D:\样板图"
_SAMPLE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _db_connect():
    return sql.connect(**_DB_CONFIG)


def _json_value(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return value.strftime("%Y-%m-%d")
    return value


def _rows_to_dicts(cursor, rows):
    columns = [col[0] for col in (cursor.description or [])]
    out = []
    for row in rows or []:
        item = {}
        for idx, col in enumerate(columns):
            item[col] = _json_value(row[idx] if idx < len(row) else None)
        out.append(item)
    return out


def _select(sql_text, params=None):
    conn = _db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_text, tuple(params or ()))
        rows = cursor.fetchall()
        return _rows_to_dicts(cursor, rows)
    finally:
        conn.close()


def _scalar(sql_text, params=None, default=0):
    conn = _db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_text, tuple(params or ()))
        row = cursor.fetchone()
        if not row:
            return default
        return _json_value(row[0])
    finally:
        conn.close()


def _execute(sql_text, params=None):
    conn = _db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_text, tuple(params or ()))
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _decimal(value, field_name="数量"):
    try:
        text = str(value if value is not None else "").strip()
        if not text:
            raise InvalidOperation()
        return Decimal(text)
    except Exception:
        raise ValueError(f"{field_name}格式不正确")


def _parse_positive_page(value, default=1, max_value=100000):
    try:
        number = int(value)
    except Exception:
        number = default
    number = max(number, 1)
    return min(number, max_value)


def _clean_text(value, limit=200):
    text = str(value or "").strip()
    if limit and len(text) > limit:
        text = text[:limit]
    return text


def _clean_color(value):
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.upper()
    return "#1677FF"


def _request_data():
    if request.files or request.form:
        return dict(request.form)
    return request.get_json(silent=True) or {}


def _sample_image_file():
    for key in ("TuPian", "tupian", "photo", "image"):
        file = request.files.get(key)
        if file and file.filename:
            return file
    return None


def _save_sample_image(file_storage):
    if not file_storage or not file_storage.filename:
        return ""
    ext = os.path.splitext(str(file_storage.filename or ""))[1].lower()
    if ext not in _SAMPLE_IMAGE_EXTENSIONS:
        raise ValueError("样板照片仅支持 jpg、jpeg、png、gif、webp、bmp 格式")
    os.makedirs(_SAMPLE_IMAGE_DIR, exist_ok=True)
    filename = f"yangban_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:10]}{ext}"
    full_path = os.path.join(_SAMPLE_IMAGE_DIR, filename)
    file_storage.save(full_path)
    return full_path


def _sample_image_filename(path_value):
    text = str(path_value or "").strip()
    if not text:
        return ""
    normalized_root = os.path.abspath(_SAMPLE_IMAGE_DIR)
    if os.path.isabs(text):
        normalized_path = os.path.abspath(text)
    else:
        normalized_path = os.path.abspath(os.path.join(_SAMPLE_IMAGE_DIR, text))
    try:
        common = os.path.commonpath([normalized_root, normalized_path])
    except ValueError:
        return ""
    if common != normalized_root:
        return ""
    return os.path.basename(normalized_path)


def _parse_tag_names(raw_value):
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [_clean_text(v, 80) for v in raw_value if _clean_text(v, 80)]
    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [_clean_text(v, 80) for v in data if _clean_text(v, 80)]
    except Exception:
        pass
    parts = re.split(r"[,，;；\s]+", text)
    return [_clean_text(v, 80) for v in parts if _clean_text(v, 80)]


def _unique_names(names):
    seen = set()
    out = []
    for name in names or []:
        text = _clean_text(name, 80)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _tag_rows(include_disabled=True):
    where_sql = "" if include_disabled else "WHERE ZhuangTai = N'ZhengChang'"
    return _select(
        f"""
        SELECT Id, BiaoQianMingCheng, YanSe, ZhuangTai, BeiZhu, ChuangJianShiJian, GengXinShiJian
        FROM {_TAG_TABLE}
        {where_sql}
        ORDER BY CASE WHEN ZhuangTai = N'ZhengChang' THEN 0 ELSE 1 END, BiaoQianMingCheng
        """
    )


def _tag_map():
    return {str(row.get("BiaoQianMingCheng") or ""): row for row in _tag_rows(True)}


def _decorate_tags(tag_names, tag_lookup=None):
    lookup = tag_lookup if tag_lookup is not None else _tag_map()
    out = []
    for name in _unique_names(tag_names):
        row = lookup.get(name) or {}
        out.append(
            {
                "name": name,
                "color": row.get("YanSe") or "#64748B",
                "status": row.get("ZhuangTai") or "",
            }
        )
    return out


def _sample_to_payload(row, tag_lookup=None):
    item = dict(row or {})
    tag_names = _parse_tag_names(item.get("BiaoQian"))
    item["BiaoQianList"] = tag_names
    item["BiaoQianItems"] = _decorate_tags(tag_names, tag_lookup)
    current_stock = Decimal(str(item.get("DangQianKuCun") or 0))
    warning_stock = Decimal(str(item.get("YuJingKuCun") or 0))
    item["IsLowStock"] = current_stock <= warning_stock
    image_name = _sample_image_filename(item.get("TuPian") or item.get("tupian"))
    item["TuPianUrl"] = f"/procurement/yangban/image/{image_name}" if image_name else ""
    return item


def _where_for_samples(args):
    clauses = []
    params = []
    keyword = _clean_text(args.get("q") or args.get("keyword"), 120)
    bianhao = _clean_text(args.get("bianhao"), 80)
    mingcheng = _clean_text(args.get("mingcheng"), 120)
    fenlei = _clean_text(args.get("fenlei"), 80)
    biaoqian = _clean_text(args.get("biaoqian"), 80)
    kuwei = _clean_text(args.get("kuwei"), 80)
    zhuangtai = _clean_text(args.get("zhuangtai"), 40)
    updated_start = _clean_text(args.get("updated_start") or args.get("start"), 20)
    updated_end = _clean_text(args.get("updated_end") or args.get("end"), 20)

    if keyword:
        clauses.append(
            "("
            "CHARINDEX(%s, ISNULL(YangBanBianHao, N'')) > 0 OR "
            "CHARINDEX(%s, ISNULL(YangBanMingCheng, N'')) > 0 OR "
            "CHARINDEX(%s, ISNULL(FenLei, N'')) > 0 OR "
            "CHARINDEX(%s, ISNULL(GuiGe, N'')) > 0 OR "
            "CHARINDEX(%s, ISNULL(KuWei, N'')) > 0 OR "
            "CHARINDEX(%s, ISNULL(BiaoQian, N'')) > 0"
            ")"
        )
        params.extend([keyword, keyword, keyword, keyword, keyword, keyword])
    if bianhao:
        clauses.append("CHARINDEX(%s, ISNULL(YangBanBianHao, N'')) > 0")
        params.append(bianhao)
    if mingcheng:
        clauses.append("CHARINDEX(%s, ISNULL(YangBanMingCheng, N'')) > 0")
        params.append(mingcheng)
    if fenlei:
        clauses.append("ISNULL(FenLei, N'') = %s")
        params.append(fenlei)
    if biaoqian:
        clauses.append("CHARINDEX(%s, ISNULL(BiaoQian, N'')) > 0")
        params.append(f'"{biaoqian}"')
    if kuwei:
        clauses.append("ISNULL(KuWei, N'') = %s")
        params.append(kuwei)
    if zhuangtai:
        clauses.append("ISNULL(ZhuangTai, N'') = %s")
        params.append(zhuangtai)
    if updated_start:
        clauses.append("ISNULL(GengXinShiJian, ChuangJianShiJian) >= CONVERT(datetime, %s)")
        params.append(updated_start)
    if updated_end:
        clauses.append("ISNULL(GengXinShiJian, ChuangJianShiJian) < DATEADD(day, 1, CONVERT(date, %s))")
        params.append(updated_end)

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


def _flow_type_label(flow_type):
    return {
        "RuKu": "入库",
        "ChuKu": "出库",
        "GuiHuan": "归还",
        "PanDian": "盘点",
    }.get(str(flow_type or ""), str(flow_type or ""))


def _status_label(status):
    return {
        "ZhengChang": "正常",
        "TingYong": "停用",
    }.get(str(status or ""), str(status or ""))


def _location_type_label(location_type):
    return {
        "Gui": "柜",
        "Ceng": "层",
        "Ge": "格",
    }.get(str(location_type or ""), str(location_type or ""))


def _location_status_label(status):
    return _status_label(status)


def _location_rows():
    return _select(
        f"""
        SELECT Id, KuWeiBianHao, KuWeiMingCheng, QuYu, ZhuangTai, BeiZhu,
               ChuangJianShiJian, GengXinShiJian, FuJiId, WeiZhiLeiXing,
               PaiXuHao, ZuiDaRongLiang
        FROM {_LOCATION_TABLE}
        ORDER BY ISNULL(PaiXuHao, 999999), Id
        """
    )


def _location_by_id(location_id):
    rows = _select(
        f"""
        SELECT Id, KuWeiBianHao, KuWeiMingCheng, QuYu, ZhuangTai, BeiZhu,
               ChuangJianShiJian, GengXinShiJian, FuJiId, WeiZhiLeiXing,
               PaiXuHao, ZuiDaRongLiang
        FROM {_LOCATION_TABLE}
        WHERE Id = %s
        """,
        [location_id],
    )
    return rows[0] if rows else None


def _location_code_exists(code, exclude_id=None):
    text = _clean_text(code, 80)
    if not text:
        return False
    params = [text]
    where_extra = ""
    if exclude_id:
        where_extra = " AND Id <> %s"
        params.append(int(exclude_id))
    count = _scalar(
        f"SELECT COUNT(1) FROM {_LOCATION_TABLE} WHERE KuWeiBianHao = %s{where_extra}",
        params,
    )
    return int(count or 0) > 0


def _active_ge_location_exists(code):
    text = _clean_text(code, 80)
    if not text:
        return False
    count = _scalar(
        f"""
        SELECT COUNT(1)
        FROM {_LOCATION_TABLE}
        WHERE KuWeiBianHao = %s
          AND WeiZhiLeiXing = N'Ge'
          AND ZhuangTai = N'ZhengChang'
        """,
        [text],
    )
    return int(count or 0) > 0


def _validate_sample_kuwei(kuwei, existing=None):
    text = _clean_text(kuwei, 80)
    if not text:
        return ""
    old_text = _clean_text((existing or {}).get("KuWei"), 80) if existing else ""
    if old_text and text == old_text:
        return text
    if not _active_ge_location_exists(text):
        raise ValueError("库位只能选择正常状态的格位")
    return text


def _occupied_location_counts():
    rows = _select(
        f"""
        SELECT KuWei, COUNT(1) AS SampleCount
        FROM {_SAMPLE_TABLE}
        WHERE ISNULL(KuWei, N'') <> N''
          AND ISNULL(DangQianKuCun, 0) > 0
          AND ZhuangTai = N'ZhengChang'
        GROUP BY KuWei
        """
    )
    return {
        str(row.get("KuWei") or "").strip(): int(row.get("SampleCount") or 0)
        for row in rows
        if str(row.get("KuWei") or "").strip()
    }


def _location_rate(occupied, total):
    total_int = int(total or 0)
    if total_int <= 0:
        return 0
    return round((int(occupied or 0) / total_int) * 100, 1)


def _decorate_location_node(node, occupied_counts):
    children = node.get("children") or []
    location_type = str(node.get("WeiZhiLeiXing") or "")
    if location_type == "Ge":
        code = str(node.get("KuWeiBianHao") or "").strip()
        sample_count = int(occupied_counts.get(code, 0) or 0)
        max_capacity = int(Decimal(str(node.get("ZuiDaRongLiang") or 1)) or 1)
        max_capacity = max(max_capacity, 1)
        occupied = 1 if sample_count > 0 else 0
        node["occupancy"] = {
            "total_ge": 1,
            "occupied_ge": occupied,
            "free_ge": 0 if occupied else 1,
            "rate": 100 if occupied else 0,
            "sample_count": sample_count,
            "max_capacity": max_capacity,
            "is_occupied": bool(occupied),
            "is_full": sample_count >= max_capacity if sample_count > 0 else False,
        }
        return node["occupancy"]

    total = 0
    occupied = 0
    full = 0
    for child in children:
        child_occ = _decorate_location_node(child, occupied_counts)
        total += int(child_occ.get("total_ge") or 0)
        occupied += int(child_occ.get("occupied_ge") or 0)
        full += 1 if child_occ.get("is_full") else 0
    free = max(total - occupied, 0)
    node["occupancy"] = {
        "total_ge": total,
        "occupied_ge": occupied,
        "free_ge": free,
        "rate": _location_rate(occupied, total),
        "sample_count": 0,
        "max_capacity": int(node.get("ZuiDaRongLiang") or 0),
        "is_occupied": occupied > 0,
        "is_full": bool(total and occupied >= total),
        "full_child_count": full,
    }
    return node["occupancy"]


def _build_location_tree(rows=None):
    raw_rows = rows if rows is not None else _location_rows()
    nodes = []
    node_map = {}
    for row in raw_rows or []:
        node = dict(row)
        node["children"] = []
        node["WeiZhiLeiXingText"] = _location_type_label(node.get("WeiZhiLeiXing"))
        node["ZhuangTaiText"] = _location_status_label(node.get("ZhuangTai"))
        node_map[int(node.get("Id"))] = node
        nodes.append(node)

    roots = []
    for node in nodes:
        parent_id = node.get("FuJiId")
        parent = node_map.get(int(parent_id)) if parent_id not in ("", None) else None
        if parent:
            parent["children"].append(node)
        else:
            roots.append(node)

    def sort_children(item):
        item["children"].sort(key=lambda x: (int(x.get("PaiXuHao") or 999999), int(x.get("Id") or 0)))
        for child in item["children"]:
            sort_children(child)

    roots.sort(key=lambda x: (int(x.get("PaiXuHao") or 999999), int(x.get("Id") or 0)))
    for root in roots:
        sort_children(root)

    occupied_counts = _occupied_location_counts()
    for root in roots:
        _decorate_location_node(root, occupied_counts)
    return roots, nodes


def _location_counts(nodes):
    return {
        "gui": sum(1 for n in nodes if n.get("WeiZhiLeiXing") == "Gui"),
        "ceng": sum(1 for n in nodes if n.get("WeiZhiLeiXing") == "Ceng"),
        "ge": sum(1 for n in nodes if n.get("WeiZhiLeiXing") == "Ge"),
    }


def _board_stats(roots):
    total = sum(int((root.get("occupancy") or {}).get("total_ge") or 0) for root in roots)
    occupied = sum(int((root.get("occupancy") or {}).get("occupied_ge") or 0) for root in roots)
    free = max(total - occupied, 0)
    return {
        "total_ge": total,
        "occupied_ge": occupied,
        "free_ge": free,
        "rate": _location_rate(occupied, total),
    }


def _location_node_matches_occupancy(node, occupancy_filter):
    occ = node.get("occupancy") or {}
    total = int(occ.get("total_ge") or 0)
    occupied = int(occ.get("occupied_ge") or 0)
    if not occupancy_filter:
        return True
    if occupancy_filter == "occupied":
        return occupied > 0
    if occupancy_filter == "free":
        return total > occupied
    if occupancy_filter == "full":
        return bool(total and occupied >= total)
    return True


def _filter_board_roots(roots, args):
    quyu = _clean_text(args.get("quyu"), 80)
    gui_name = _clean_text(args.get("gui"), 120)
    zhuangtai = _clean_text(args.get("zhuangtai"), 40)
    occupancy = _clean_text(args.get("occupancy"), 40)
    out = []
    for root in roots:
        if quyu and str(root.get("QuYu") or "") != quyu:
            continue
        if gui_name and gui_name not in str(root.get("KuWeiMingCheng") or "") and gui_name not in str(root.get("KuWeiBianHao") or ""):
            continue
        if zhuangtai and str(root.get("ZhuangTai") or "") != zhuangtai:
            continue
        if not _location_node_matches_occupancy(root, occupancy):
            continue
        out.append(root)
    return out


def _location_payload_from_request(data, location_type=None, parent_id=None, existing=None):
    payload = data if isinstance(data, dict) else {}
    loc_type = _clean_text(location_type or payload.get("WeiZhiLeiXing") or (existing or {}).get("WeiZhiLeiXing"), 20)
    if loc_type not in _LOCATION_TYPES:
        raise ValueError("位置类型不正确")

    code = _clean_text(payload.get("KuWeiBianHao"), 80)
    name = _clean_text(payload.get("KuWeiMingCheng"), 120)
    if not code:
        raise ValueError("请填写库位编号")
    if not name:
        raise ValueError("请填写库位名称")

    existing_id = int((existing or {}).get("Id") or 0)
    if _location_code_exists(code, existing_id or None):
        raise ValueError("库位编号不能重复")

    status = _clean_text(payload.get("ZhuangTai") or "ZhengChang", 40)
    if status not in _LOCATION_STATUSES:
        raise ValueError("位置状态不正确")

    try:
        sort_no = int(str(payload.get("PaiXuHao") or 0).strip() or 0)
    except Exception:
        raise ValueError("排序号必须是数字")

    parent = None
    if loc_type == "Gui":
        final_parent_id = None
    else:
        final_parent_id = int(parent_id or payload.get("FuJiId") or (existing or {}).get("FuJiId") or 0)
        parent = _location_by_id(final_parent_id)
        if not parent:
            raise ValueError("请选择父级位置")
        expected_parent_type = "Gui" if loc_type == "Ceng" else "Ceng"
        if parent.get("WeiZhiLeiXing") != expected_parent_type:
            raise ValueError("父级位置类型不符合层级规则")

    if loc_type == "Ge":
        capacity_raw = payload.get("ZuiDaRongLiang")
        capacity = int(str(capacity_raw if capacity_raw not in (None, "") else 1).strip() or 1)
        if capacity <= 0:
            raise ValueError("最大容量必须大于0")
    else:
        capacity = int(str(payload.get("ZuiDaRongLiang") or 0).strip() or 0)

    area = _clean_text(payload.get("QuYu"), 80)
    if loc_type != "Gui" and not area and parent:
        area = _clean_text(parent.get("QuYu"), 80)

    return {
        "KuWeiBianHao": code,
        "KuWeiMingCheng": name,
        "QuYu": area,
        "ZhuangTai": status,
        "BeiZhu": _clean_text(payload.get("BeiZhu"), 500),
        "FuJiId": final_parent_id,
        "WeiZhiLeiXing": loc_type,
        "PaiXuHao": sort_no,
        "ZuiDaRongLiang": capacity,
    }


def _build_flow_query(args, export=False):
    clauses = []
    params = []
    start = _clean_text(args.get("start"), 20)
    end = _clean_text(args.get("end"), 20)
    yangban_id = _clean_text(args.get("yangban_id"), 20)
    flow_type = _clean_text(args.get("type"), 20)
    operator = _clean_text(args.get("operator"), 80)

    if start:
        clauses.append("l.ChuangJianShiJian >= CONVERT(datetime, %s)")
        params.append(start)
    if end:
        clauses.append("l.ChuangJianShiJian < DATEADD(day, 1, CONVERT(date, %s))")
        params.append(end)
    if yangban_id:
        try:
            params.append(int(yangban_id))
            clauses.append("l.YangBanId = %s")
        except Exception:
            clauses.append("1 = 0")
    if flow_type:
        clauses.append("l.BianDongLeiXing = %s")
        params.append(flow_type)
    if operator:
        clauses.append("CHARINDEX(%s, ISNULL(l.CaoZuoRen, N'')) > 0")
        params.append(operator)

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    page = _parse_positive_page(args.get("page"), 1)
    page_size = _parse_positive_page(args.get("page_size"), 20, 500)
    offset = (page - 1) * page_size

    select_sql = f"""
        SELECT
            l.Id, l.YangBanId, y.YangBanBianHao, y.YangBanMingCheng,
            l.BianDongLeiXing, l.BianDongShuLiang, l.CaoZuoRen,
            l.GuanLianDanHao, l.BeiZhu, l.ChuangJianShiJian
        FROM {_FLOW_TABLE} l
        LEFT JOIN {_SAMPLE_TABLE} y ON y.Id = l.YangBanId
        {where_sql}
        ORDER BY l.ChuangJianShiJian DESC, l.Id DESC
    """
    if not export:
        select_sql += f" OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
    count_sql = f"SELECT COUNT(1) AS total FROM {_FLOW_TABLE} l LEFT JOIN {_SAMPLE_TABLE} y ON y.Id = l.YangBanId {where_sql}"
    return select_sql, count_sql, params, page, page_size


def _sample_payload_from_request(data, existing=None):
    payload = data if isinstance(data, dict) else {}
    bianhao = _clean_text(payload.get("YangBanBianHao"), 80)
    mingcheng = _clean_text(payload.get("YangBanMingCheng"), 120)
    if not bianhao:
        raise ValueError("请填写样板编号")
    if not mingcheng:
        raise ValueError("请填写样板名称")

    status = _clean_text(payload.get("ZhuangTai") or "ZhengChang", 40)
    if status not in _SAMPLE_STATUSES:
        raise ValueError("样板状态不正确")

    warning_stock = _decimal(payload.get("YuJingKuCun") or 0, "预警库存")
    if warning_stock < 0:
        raise ValueError("预警库存不能小于0")

    tag_names = _unique_names(_parse_tag_names(payload.get("BiaoQianList") or payload.get("BiaoQian") or []))
    active_names = {str(row.get("BiaoQianMingCheng") or "") for row in _tag_rows(False)}
    if any(name not in active_names for name in tag_names):
        if existing:
            old_inactive = [name for name in _parse_tag_names(existing.get("BiaoQian")) if name not in active_names]
            tag_names = _unique_names([name for name in tag_names if name in active_names] + old_inactive)
        else:
            raise ValueError("只能选择正常状态的标签")

    return {
        "YangBanBianHao": bianhao,
        "YangBanMingCheng": mingcheng,
        "FenLei": _clean_text(payload.get("FenLei"), 80),
        "BiaoQian": json.dumps(tag_names, ensure_ascii=False),
        "GuiGe": _clean_text(payload.get("GuiGe"), 120),
        "DanWei": _clean_text(payload.get("DanWei"), 40),
        "YuJingKuCun": warning_stock,
        "KuWei": _validate_sample_kuwei(payload.get("KuWei"), existing),
        "ZhuangTai": status,
        "BeiZhu": _clean_text(payload.get("BeiZhu"), 500),
    }


def _get_sample(sample_id):
    rows = _select(
        f"""
        SELECT Id, YangBanBianHao, YangBanMingCheng, FenLei, BiaoQian, GuiGe, DanWei,
               [tupian] AS TuPian,
               DangQianKuCun, YuJingKuCun, KuWei, ZhuangTai, BeiZhu,
               ChuangJianShiJian, GengXinShiJian
        FROM {_SAMPLE_TABLE}
        WHERE Id = %s
        """,
        [sample_id],
    )
    if not rows:
        return None
    return _sample_to_payload(rows[0], _tag_map())


@yangban_inventory_bp.route("/procurement/yangban_inventory")
@require_permission("procurement_dept")
def page():
    return render_template(
        "yangban_inventory.html",
        user_name=session.get("feishu_user_name", "用户"),
    )


@yangban_inventory_bp.route("/procurement/yangban_locations")
@require_permission("procurement_dept")
def locations_page():
    return render_template(
        "yangban_location.html",
        user_name=session.get("feishu_user_name", "用户"),
    )


@yangban_inventory_bp.route("/procurement/yangban/image/<path:filename>")
@require_permission("procurement_dept")
def sample_image(filename):
    safe_name = os.path.basename(str(filename or ""))
    if not safe_name:
        return jsonify({"success": False, "message": "图片不存在"}), 404
    full_path = os.path.abspath(os.path.join(_SAMPLE_IMAGE_DIR, safe_name))
    root_path = os.path.abspath(_SAMPLE_IMAGE_DIR)
    try:
        if os.path.commonpath([root_path, full_path]) != root_path:
            return jsonify({"success": False, "message": "图片路径无效"}), 400
    except ValueError:
        return jsonify({"success": False, "message": "图片路径无效"}), 400
    if not os.path.exists(full_path):
        return jsonify({"success": False, "message": "图片不存在"}), 404
    return send_from_directory(_SAMPLE_IMAGE_DIR, safe_name)


@yangban_inventory_bp.route("/api/procurement/yangban/locations/tree")
@require_permission("procurement_dept")
def api_location_tree():
    try:
        roots, nodes = _build_location_tree()
        filtered_roots = _filter_board_roots(roots, request.args)
        areas = sorted({str(node.get("QuYu") or "").strip() for node in nodes if str(node.get("QuYu") or "").strip()})
        cabinets = [
            {
                "Id": node.get("Id"),
                "KuWeiBianHao": node.get("KuWeiBianHao"),
                "KuWeiMingCheng": node.get("KuWeiMingCheng"),
                "QuYu": node.get("QuYu"),
                "ZhuangTai": node.get("ZhuangTai"),
            }
            for node in nodes
            if node.get("WeiZhiLeiXing") == "Gui"
        ]
        return jsonify(
            {
                "success": True,
                "data": {
                    "tree": roots,
                    "board_tree": filtered_roots,
                    "counts": _location_counts(nodes),
                    "stats": _board_stats(filtered_roots),
                    "areas": areas,
                    "cabinets": cabinets,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载位置结构失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/locations", methods=["POST"])
@require_permission("procurement_dept")
def api_create_location():
    try:
        data = request.get_json(silent=True) or {}
        payload = _location_payload_from_request(data)
        _execute(
            f"""
            INSERT INTO {_LOCATION_TABLE}
                (KuWeiBianHao, KuWeiMingCheng, QuYu, ZhuangTai, BeiZhu,
                 ChuangJianShiJian, GengXinShiJian, FuJiId, WeiZhiLeiXing,
                 PaiXuHao, ZuiDaRongLiang)
            VALUES
                (%s, %s, %s, %s, %s,
                 GETDATE(), GETDATE(), %s, %s,
                 %s, %s)
            """,
            [
                payload["KuWeiBianHao"],
                payload["KuWeiMingCheng"],
                payload["QuYu"],
                payload["ZhuangTai"],
                payload["BeiZhu"],
                payload["FuJiId"],
                payload["WeiZhiLeiXing"],
                payload["PaiXuHao"],
                payload["ZuiDaRongLiang"],
            ],
        )
        return jsonify({"success": True, "message": "位置已新增"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "message": f"新增位置失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/locations/<int:location_id>", methods=["PUT"])
@require_permission("procurement_dept")
def api_update_location(location_id):
    try:
        existing = _location_by_id(location_id)
        if not existing:
            return jsonify({"success": False, "message": "位置不存在"}), 404
        data = request.get_json(silent=True) or {}
        payload = _location_payload_from_request(data, existing=existing)
        _execute(
            f"""
            UPDATE {_LOCATION_TABLE}
               SET KuWeiBianHao = %s,
                   KuWeiMingCheng = %s,
                   QuYu = %s,
                   ZhuangTai = %s,
                   BeiZhu = %s,
                   FuJiId = %s,
                   WeiZhiLeiXing = %s,
                   PaiXuHao = %s,
                   ZuiDaRongLiang = %s,
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            [
                payload["KuWeiBianHao"],
                payload["KuWeiMingCheng"],
                payload["QuYu"],
                payload["ZhuangTai"],
                payload["BeiZhu"],
                payload["FuJiId"],
                payload["WeiZhiLeiXing"],
                payload["PaiXuHao"],
                payload["ZuiDaRongLiang"],
                location_id,
            ],
        )
        return jsonify({"success": True, "message": "位置已保存"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "message": f"保存位置失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/locations/<int:location_id>/disable", methods=["POST"])
@require_permission("procurement_dept")
def api_disable_location(location_id):
    try:
        existing = _location_by_id(location_id)
        if not existing:
            return jsonify({"success": False, "message": "位置不存在"}), 404
        _execute(
            f"""
            UPDATE {_LOCATION_TABLE}
               SET ZhuangTai = N'TingYong',
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            [location_id],
        )
        return jsonify({"success": True, "message": "位置已停用"})
    except Exception as exc:
        return jsonify({"success": False, "message": f"停用位置失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/locations/<int:location_id>", methods=["DELETE"])
@require_permission("procurement_dept")
def api_delete_location(location_id):
    try:
        existing = _location_by_id(location_id)
        if not existing:
            return jsonify({"success": False, "message": "位置不存在"}), 404
        children_count = _scalar(f"SELECT COUNT(1) FROM {_LOCATION_TABLE} WHERE FuJiId = %s", [location_id])
        if int(children_count or 0) > 0:
            return jsonify({"success": False, "message": "该位置存在下级节点，不能删除"}), 400
        if existing.get("WeiZhiLeiXing") == "Ge":
            used_count = _scalar(
                f"SELECT COUNT(1) FROM {_SAMPLE_TABLE} WHERE KuWei = %s",
                [existing.get("KuWeiBianHao")],
            )
            if int(used_count or 0) > 0:
                return jsonify({"success": False, "message": "该格位已被样板使用，不能删除，只能停用"}), 400
        _execute(f"DELETE FROM {_LOCATION_TABLE} WHERE Id = %s", [location_id])
        return jsonify({"success": True, "message": "位置已删除"})
    except Exception as exc:
        return jsonify({"success": False, "message": f"删除位置失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/dashboard")
@require_permission("procurement_dept")
def api_dashboard():
    try:
        total_samples = _scalar(f"SELECT COUNT(1) FROM {_SAMPLE_TABLE}")
        total_stock = _scalar(f"SELECT ISNULL(SUM(ISNULL(DangQianKuCun, 0)), 0) FROM {_SAMPLE_TABLE}")
        low_stock = _scalar(
            f"""
            SELECT COUNT(1)
            FROM {_SAMPLE_TABLE}
            WHERE ISNULL(DangQianKuCun, 0) <= ISNULL(YuJingKuCun, 0)
            """
        )
        today_in = _scalar(
            f"""
            SELECT ISNULL(SUM(BianDongShuLiang), 0)
            FROM {_FLOW_TABLE}
            WHERE BianDongLeiXing IN (N'RuKu', N'GuiHuan')
              AND CONVERT(date, ChuangJianShiJian) = CONVERT(date, GETDATE())
            """
        )
        today_out = _scalar(
            f"""
            SELECT ISNULL(SUM(ABS(BianDongShuLiang)), 0)
            FROM {_FLOW_TABLE}
            WHERE BianDongLeiXing = N'ChuKu'
              AND CONVERT(date, ChuangJianShiJian) = CONVERT(date, GETDATE())
            """
        )
        recent = _select(
            f"""
            SELECT TOP 12
                l.Id, l.YangBanId, y.YangBanBianHao, y.YangBanMingCheng,
                y.[tupian] AS TuPian,
                l.BianDongLeiXing, l.BianDongShuLiang, l.CaoZuoRen,
                l.GuanLianDanHao, l.BeiZhu, l.ChuangJianShiJian
            FROM {_FLOW_TABLE} l
            LEFT JOIN {_SAMPLE_TABLE} y ON y.Id = l.YangBanId
            ORDER BY l.ChuangJianShiJian DESC, l.Id DESC
            """
        )
        for row in recent:
            row["BianDongLeiXingText"] = _flow_type_label(row.get("BianDongLeiXing"))
            image_name = _sample_image_filename(row.get("TuPian") or row.get("tupian"))
            row["TuPianUrl"] = f"/procurement/yangban/image/{image_name}" if image_name else ""
        return jsonify(
            {
                "success": True,
                "data": {
                    "total_samples": total_samples,
                    "total_stock": total_stock,
                    "low_stock": low_stock,
                    "today_in": today_in,
                    "today_out": today_out,
                    "recent_flows": recent,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载看板失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/options")
@require_permission("procurement_dept")
def api_options():
    try:
        categories = _select(
            f"""
            SELECT DISTINCT FenLei AS value
            FROM {_SAMPLE_TABLE}
            WHERE ISNULL(FenLei, N'') <> N''
            ORDER BY FenLei
            """
        )
        locations = _select(
            f"""
            SELECT DISTINCT KuWei AS value
            FROM {_SAMPLE_TABLE}
            WHERE ISNULL(KuWei, N'') <> N''
            ORDER BY KuWei
            """
        )
        statuses = _select(
            f"""
            SELECT DISTINCT ZhuangTai AS value
            FROM {_SAMPLE_TABLE}
            WHERE ISNULL(ZhuangTai, N'') <> N''
            ORDER BY ZhuangTai
            """
        )
        ge_locations = _select(
            f"""
            SELECT Id, KuWeiBianHao, KuWeiMingCheng, QuYu, ZhuangTai, BeiZhu,
                   FuJiId, WeiZhiLeiXing, PaiXuHao, ZuiDaRongLiang
            FROM {_LOCATION_TABLE}
            WHERE WeiZhiLeiXing = N'Ge'
            ORDER BY ISNULL(PaiXuHao, 999999), KuWeiBianHao
            """
        )
        active_ge_locations = [row for row in ge_locations if row.get("ZhuangTai") == "ZhengChang"]
        return jsonify(
            {
                "success": True,
                "data": {
                    "categories": [row.get("value") for row in categories if row.get("value")],
                    "locations": [row.get("value") for row in locations if row.get("value")],
                    "statuses": [row.get("value") for row in statuses if row.get("value")],
                    "tags": _tag_rows(True),
                    "active_tags": _tag_rows(False),
                    "ge_locations": ge_locations,
                    "active_ge_locations": active_ge_locations,
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载筛选项失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/samples", methods=["GET", "POST"])
@require_permission("procurement_dept")
def api_samples():
    if request.method == "POST":
        try:
            payload = _sample_payload_from_request(_request_data())
            image_path = _save_sample_image(_sample_image_file())
            _execute(
                f"""
                INSERT INTO {_SAMPLE_TABLE}
                    (YangBanBianHao, YangBanMingCheng, FenLei, BiaoQian, GuiGe, DanWei,
                     [tupian], DangQianKuCun, YuJingKuCun, KuWei, ZhuangTai, BeiZhu,
                     ChuangJianShiJian, GengXinShiJian)
                VALUES
                    (%s, %s, %s, %s, %s, %s,
                     %s, 0, %s, %s, %s, %s,
                     GETDATE(), GETDATE())
                """,
                [
                    payload["YangBanBianHao"],
                    payload["YangBanMingCheng"],
                    payload["FenLei"],
                    payload["BiaoQian"],
                    payload["GuiGe"],
                    payload["DanWei"],
                    image_path,
                    payload["YuJingKuCun"],
                    payload["KuWei"],
                    payload["ZhuangTai"],
                    payload["BeiZhu"],
                ],
            )
            return jsonify({"success": True, "message": "样板已新增"})
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "message": f"新增样板失败：{exc}"}), 500

    try:
        page = _parse_positive_page(request.args.get("page"), 1)
        page_size = _parse_positive_page(request.args.get("page_size"), 20, 500)
        offset = (page - 1) * page_size
        where_sql, params = _where_for_samples(request.args)
        total = _scalar(f"SELECT COUNT(1) FROM {_SAMPLE_TABLE} {where_sql}", params)
        rows = _select(
            f"""
            SELECT Id, YangBanBianHao, YangBanMingCheng, FenLei, BiaoQian, GuiGe, DanWei,
                   [tupian] AS TuPian,
                   DangQianKuCun, YuJingKuCun, KuWei, ZhuangTai, BeiZhu,
                   ChuangJianShiJian, GengXinShiJian
            FROM {_SAMPLE_TABLE}
            {where_sql}
            ORDER BY ISNULL(GengXinShiJian, ChuangJianShiJian) DESC, Id DESC
            OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY
            """,
            params,
        )
        lookup = _tag_map()
        items = [_sample_to_payload(row, lookup) for row in rows]
        return jsonify(
            {
                "success": True,
                "data": {
                    "items": items,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": max((int(total or 0) + page_size - 1) // page_size, 1),
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载样板列表失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/samples/<int:sample_id>", methods=["GET", "PUT"])
@require_permission("procurement_dept")
def api_sample_detail(sample_id):
    if request.method == "PUT":
        try:
            existing = _get_sample(sample_id)
            if not existing:
                return jsonify({"success": False, "message": "样板不存在"}), 404
            payload = _sample_payload_from_request(_request_data(), existing)
            image_path = _save_sample_image(_sample_image_file()) or existing.get("TuPian") or existing.get("tupian") or ""
            _execute(
                f"""
                UPDATE {_SAMPLE_TABLE}
                   SET YangBanBianHao = %s,
                       YangBanMingCheng = %s,
                       FenLei = %s,
                       BiaoQian = %s,
                       GuiGe = %s,
                       DanWei = %s,
                       [tupian] = %s,
                       YuJingKuCun = %s,
                       KuWei = %s,
                       ZhuangTai = %s,
                       BeiZhu = %s,
                       GengXinShiJian = GETDATE()
                 WHERE Id = %s
                """,
                [
                    payload["YangBanBianHao"],
                    payload["YangBanMingCheng"],
                    payload["FenLei"],
                    payload["BiaoQian"],
                    payload["GuiGe"],
                    payload["DanWei"],
                    image_path,
                    payload["YuJingKuCun"],
                    payload["KuWei"],
                    payload["ZhuangTai"],
                    payload["BeiZhu"],
                    sample_id,
                ],
            )
            return jsonify({"success": True, "message": "样板已保存"})
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "message": f"保存样板失败：{exc}"}), 500

    try:
        sample = _get_sample(sample_id)
        if not sample:
            return jsonify({"success": False, "message": "样板不存在"}), 404
        flows = _select(
            f"""
            SELECT TOP 200 Id, YangBanId, BianDongLeiXing, BianDongShuLiang,
                   CaoZuoRen, GuanLianDanHao, BeiZhu, ChuangJianShiJian
            FROM {_FLOW_TABLE}
            WHERE YangBanId = %s
            ORDER BY ChuangJianShiJian DESC, Id DESC
            """,
            [sample_id],
        )
        for row in flows:
            row["BianDongLeiXingText"] = _flow_type_label(row.get("BianDongLeiXing"))
        return jsonify({"success": True, "data": {"sample": sample, "flows": flows}})
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载样板详情失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/samples/<int:sample_id>/disable", methods=["POST"])
@require_permission("procurement_dept")
def api_disable_sample(sample_id):
    try:
        exists = _scalar(f"SELECT COUNT(1) FROM {_SAMPLE_TABLE} WHERE Id = %s", [sample_id])
        if int(exists or 0) <= 0:
            return jsonify({"success": False, "message": "样板不存在"}), 404
        _execute(
            f"""
            UPDATE {_SAMPLE_TABLE}
               SET ZhuangTai = N'TingYong',
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            [sample_id],
        )
        return jsonify({"success": True, "message": "样板已停用"})
    except Exception as exc:
        return jsonify({"success": False, "message": f"停用样板失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/operations", methods=["POST"])
@require_permission("procurement_dept")
def api_inventory_operation():
    payload = request.get_json(silent=True) or {}
    conn = None
    try:
        sample_id = int(payload.get("YangBanId") or 0)
        flow_type = _clean_text(payload.get("BianDongLeiXing"), 20)
        if flow_type not in _VALID_FLOW_TYPES:
            raise ValueError("库存操作类型不正确")
        quantity = _decimal(payload.get("BianDongShuLiang"), "变动数量")
        if quantity == 0:
            raise ValueError("变动数量不能为0")

        if flow_type in {"RuKu", "GuiHuan"}:
            delta = abs(quantity)
        elif flow_type == "ChuKu":
            delta = -abs(quantity)
        else:
            delta = quantity

        operator = _clean_text(payload.get("CaoZuoRen") or session.get("feishu_user_name"), 80)
        if not operator:
            raise ValueError("请填写操作人")
        related_no = _clean_text(payload.get("GuanLianDanHao"), 120)
        remark = _clean_text(payload.get("BeiZhu"), 500)

        conn = _db_connect()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT Id, YangBanMingCheng, DangQianKuCun, ZhuangTai
            FROM {_SAMPLE_TABLE} WITH (UPDLOCK, ROWLOCK)
            WHERE Id = %s
            """,
            (sample_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("样板不存在")
        current_stock = Decimal(str(row[2] or 0))
        status = str(row[3] or "")
        if status != "ZhengChang":
            raise ValueError("样板已停用，不能进行库存操作")
        new_stock = current_stock + delta
        if new_stock < 0:
            if flow_type == "ChuKu":
                raise ValueError("出库后库存不能小于0")
            raise ValueError("库存不能小于0")

        cursor.execute(
            f"""
            UPDATE {_SAMPLE_TABLE}
               SET DangQianKuCun = %s,
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            (new_stock, sample_id),
        )
        cursor.execute(
            f"""
            INSERT INTO {_FLOW_TABLE}
                (YangBanId, BianDongLeiXing, BianDongShuLiang,
                 CaoZuoRen, GuanLianDanHao, BeiZhu, ChuangJianShiJian)
            VALUES
                (%s, %s, %s, %s, %s, %s, GETDATE())
            """,
            (sample_id, flow_type, delta, operator, related_no, remark),
        )
        conn.commit()
        return jsonify(
            {
                "success": True,
                "message": "库存操作已完成",
                "data": {
                    "old_stock": _json_value(current_stock),
                    "delta": _json_value(delta),
                    "new_stock": _json_value(new_stock),
                },
            }
        )
    except ValueError as exc:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "message": f"库存操作失败：{exc}"}), 500
    finally:
        if conn:
            conn.close()


@yangban_inventory_bp.route("/api/procurement/yangban/flows")
@require_permission("procurement_dept")
def api_flows():
    try:
        select_sql, count_sql, params, page, page_size = _build_flow_query(request.args)
        total = _scalar(count_sql, params)
        rows = _select(select_sql, params)
        for row in rows:
            row["BianDongLeiXingText"] = _flow_type_label(row.get("BianDongLeiXing"))
        return jsonify(
            {
                "success": True,
                "data": {
                    "items": rows,
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": max((int(total or 0) + page_size - 1) // page_size, 1),
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载库存流水失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/flows/export")
@require_permission("procurement_dept")
def api_flows_export():
    try:
        select_sql, _, params, _, _ = _build_flow_query(request.args, export=True)
        rows = _select(select_sql, params)
        data = []
        for row in rows:
            data.append(
                {
                    "样板编号": row.get("YangBanBianHao"),
                    "样板名称": row.get("YangBanMingCheng"),
                    "操作类型": _flow_type_label(row.get("BianDongLeiXing")),
                    "变动数量": row.get("BianDongShuLiang"),
                    "操作人": row.get("CaoZuoRen"),
                    "关联单号": row.get("GuanLianDanHao"),
                    "备注": row.get("BeiZhu"),
                    "操作时间": row.get("ChuangJianShiJian"),
                }
            )
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(data).to_excel(writer, index=False, sheet_name="库存流水")
        output.seek(0)
        filename = f"样板库存流水_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        return jsonify({"success": False, "message": f"导出库存流水失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/tags", methods=["GET", "POST"])
@require_permission("procurement_dept")
def api_tags():
    if request.method == "POST":
        try:
            payload = request.get_json(silent=True) or {}
            name = _clean_text(payload.get("BiaoQianMingCheng"), 80)
            if not name:
                raise ValueError("请填写标签名称")
            exists = _scalar(
                f"SELECT COUNT(1) FROM {_TAG_TABLE} WHERE BiaoQianMingCheng = %s",
                [name],
            )
            if int(exists or 0) > 0:
                raise ValueError("标签名称不能重复")
            status = _clean_text(payload.get("ZhuangTai") or "ZhengChang", 40)
            if status not in _TAG_STATUSES:
                raise ValueError("标签状态不正确")
            _execute(
                f"""
                INSERT INTO {_TAG_TABLE}
                    (BiaoQianMingCheng, YanSe, ZhuangTai, BeiZhu, ChuangJianShiJian, GengXinShiJian)
                VALUES
                    (%s, %s, %s, %s, GETDATE(), GETDATE())
                """,
                [
                    name,
                    _clean_color(payload.get("YanSe")),
                    status,
                    _clean_text(payload.get("BeiZhu"), 500),
                ],
            )
            return jsonify({"success": True, "message": "标签已新增"})
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            return jsonify({"success": False, "message": f"新增标签失败：{exc}"}), 500

    try:
        return jsonify({"success": True, "data": {"items": _tag_rows(True)}})
    except Exception as exc:
        return jsonify({"success": False, "message": f"加载标签失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/tags/<int:tag_id>", methods=["PUT"])
@require_permission("procurement_dept")
def api_update_tag(tag_id):
    try:
        payload = request.get_json(silent=True) or {}
        name = _clean_text(payload.get("BiaoQianMingCheng"), 80)
        if not name:
            raise ValueError("请填写标签名称")
        tag_exists = _scalar(f"SELECT COUNT(1) FROM {_TAG_TABLE} WHERE Id = %s", [tag_id])
        if int(tag_exists or 0) <= 0:
            return jsonify({"success": False, "message": "标签不存在"}), 404
        exists = _scalar(
            f"SELECT COUNT(1) FROM {_TAG_TABLE} WHERE BiaoQianMingCheng = %s AND Id <> %s",
            [name, tag_id],
        )
        if int(exists or 0) > 0:
            raise ValueError("标签名称不能重复")
        status = _clean_text(payload.get("ZhuangTai") or "ZhengChang", 40)
        if status not in _TAG_STATUSES:
            raise ValueError("标签状态不正确")
        _execute(
            f"""
            UPDATE {_TAG_TABLE}
               SET BiaoQianMingCheng = %s,
                   YanSe = %s,
                   ZhuangTai = %s,
                   BeiZhu = %s,
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            [
                name,
                _clean_color(payload.get("YanSe")),
                status,
                _clean_text(payload.get("BeiZhu"), 500),
                tag_id,
            ],
        )
        return jsonify({"success": True, "message": "标签已保存"})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "message": f"保存标签失败：{exc}"}), 500


@yangban_inventory_bp.route("/api/procurement/yangban/tags/<int:tag_id>/disable", methods=["POST"])
@require_permission("procurement_dept")
def api_disable_tag(tag_id):
    try:
        exists = _scalar(f"SELECT COUNT(1) FROM {_TAG_TABLE} WHERE Id = %s", [tag_id])
        if int(exists or 0) <= 0:
            return jsonify({"success": False, "message": "标签不存在"}), 404
        _execute(
            f"""
            UPDATE {_TAG_TABLE}
               SET ZhuangTai = N'TingYong',
                   GengXinShiJian = GETDATE()
             WHERE Id = %s
            """,
            [tag_id],
        )
        return jsonify({"success": True, "message": "标签已停用"})
    except Exception as exc:
        return jsonify({"success": False, "message": f"停用标签失败：{exc}"}), 500


@yangban_inventory_bp.app_template_filter("yangban_status_label")
def yangban_status_label(value):
    return _status_label(value)
