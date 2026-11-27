"""Write Xiaoha usage and read permission-scoped image history."""

from __future__ import annotations

from typing import Any


def get_db_connection(*, DB_CONFIG) -> Any:
    import pytds as sql

    return sql.connect(**DB_CONFIG)


def execute_db_query(
    query,
    params,
    *,
    get_db_connection,
) -> list[tuple[Any, ...]]:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        rows = cursor.fetchall()
        return list(rows or [])
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def execute_db_non_query(
    query,
    params,
    *,
    get_db_connection,
) -> None:
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if params is None:
            cursor.execute(query)
        else:
            cursor.execute(query, params)
        if not conn.autocommit:
            conn.commit()
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def insert_history_db_record(
    account_name,
    feature_name,
    model,
    image_path,
    created_at_text,
    image_count,
    *,
    DB_HISTORY_TABLE,
    _xiaoha_history_storage,
    execute_db_non_query,
) -> None:
    return _xiaoha_history_storage.insert_history_db_record(
        account_name,
        feature_name,
        model,
        image_path,
        created_at_text,
        image_count,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        execute_db_non_query=execute_db_non_query,
    )


def record_infinite_canvas_usage(
    account_name,
    feature_name,
    model,
    image_count,
    *,
    DB_HISTORY_TABLE,
    datetime,
    insert_history_db_record,
    sys,
) -> bool:
    normalized_feature_name = str(feature_name or "图片生成").strip() or "图片生成"
    if not normalized_feature_name.startswith("无限画布-"):
        normalized_feature_name = f"无限画布-{normalized_feature_name}"
    try:
        insert_history_db_record(
            account_name=str(account_name or "访客").strip() or "访客",
            feature_name=normalized_feature_name,
            model=str(model or "").strip(),
            image_path="",
            created_at_text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            image_count=max(int(image_count), 0),
        )
        return True
    except Exception as exc:
        print(f"[infinite-canvas-usage] 写入 {DB_HISTORY_TABLE} 失败：{exc}", file=sys.stderr)
        return False


def _db_history_can_view_all(
    account_name,
    *,
    execute_db_query,
    re,
) -> bool:
    normalized_account = str(account_name or "").strip()
    if not normalized_account:
        return False
    try:
        rows = execute_db_query(
            """
            SELECT TOP 1 YongHu
            FROM dbo.quanxian
            WHERE LTRIM(RTRIM(GongNeng))=%s
              AND (QiYong=1 OR QiYong IS NULL)
            ORDER BY ID
            """,
            ("image_history_all",),
        )
    except Exception:
        return False
    raw_users = str(rows[0][0] or "") if rows and rows[0] else ""
    allowed_users = {
        value.strip()
        for value in re.split(r"[；;,，、\r\n]+", raw_users)
        if value.strip()
    }
    return normalized_account in allowed_users


def load_db_history_records(
    feature_key,
    account_name,
    limit,
    *,
    A_PLUS_REFERENCE_LAB_FEATURE_KEY,
    Any,
    DB_HISTORY_TABLE,
    Path,
    _db_history_can_view_all,
    _xiaoha_history,
    build_history_thumbnail_source,
    convert_history_path_to_public_url,
    ensure_history_thumbnail,
    execute_db_query,
    format_history_datetime,
    get_feature_name_by_key,
    resolve_db_history_image_path,
) -> list[dict[str, Any]]:
    return _xiaoha_history.load_db_history_records(
        feature_key,
        account_name,
        limit,
        A_PLUS_REFERENCE_LAB_FEATURE_KEY=A_PLUS_REFERENCE_LAB_FEATURE_KEY,
        Any=Any,
        DB_HISTORY_TABLE=DB_HISTORY_TABLE,
        Path=Path,
        _db_history_can_view_all=_db_history_can_view_all,
        build_history_thumbnail_source=build_history_thumbnail_source,
        convert_history_path_to_public_url=convert_history_path_to_public_url,
        ensure_history_thumbnail=ensure_history_thumbnail,
        execute_db_query=execute_db_query,
        format_history_datetime=format_history_datetime,
        get_feature_name_by_key=get_feature_name_by_key,
        resolve_db_history_image_path=resolve_db_history_image_path,
    )
