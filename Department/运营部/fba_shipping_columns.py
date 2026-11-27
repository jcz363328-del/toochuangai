"""Resolve FBA shipping field names, formats and display columns."""

from __future__ import annotations


def _fba_shipping_sql_ident(name):
    return '[' + str(name or '').replace(']', ']]') + ']'


def _fba_shipping_sql_text(value):
    return str(value or '').replace("'", "''")


def _fba_shipping_col_norm(
    name,
    *,
    re,
):
    text = str(name or '').strip().lower()
    text = re.sub(r'[\s_\-./\\()\[\]（）【】]+', '', text)
    return text


def _fba_shipping_label(
    name,
    *,
    _fba_shipping_col_norm,
):
    raw = str(name or '').strip()
    norm = _fba_shipping_col_norm(raw)
    labels = {
        'id': '序号',
        'xh': '序号',
        'xuhao': '序号',
        'xvhao': '序号',
        '序号': '序号',
        'dian': '店铺',
        '店': '店铺',
        '店铺': '店铺',
        'danhao': '单号',
        'yunshufangshi': '运输方式',
        '运输方式': '运输方式',
        'xiaobaoguo': '小包裹',
        'wuliudanhao': '物流单号',
        'huojiandanhao': '亚马逊追踪码',
        '货件单号': '亚马逊追踪码',
        'daorushijian': '导入时间',
        '导入时间': '导入时间',
        'daoruren': '导入人',
        '导入人': '导入人',
        'ien': 'IEN',
        'huojiandanhaogeshu': '亚马逊追踪码个数',
        'sku': 'SKU',
        'beizhu': '备注',
        '备注': '备注',
    }
    return labels.get(norm) or raw


def _fba_shipping_pick_col(
    columns,
    candidates,
    *,
    _fba_shipping_col_norm,
):
    norm_map = {_fba_shipping_col_norm(col): col for col in (columns or [])}
    for candidate in candidates:
        col = norm_map.get(_fba_shipping_col_norm(candidate))
        if col:
            return col
    return ''


def _fba_shipping_get_columns(
    *,
    _FBA_SHIPPING_TABLE,
    sf_db,
):
    sql = f"""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = N'{_FBA_SHIPPING_TABLE}'
        ORDER BY ORDINAL_POSITION
    """
    rows = sf_db(sql) or []
    columns = []
    for row in rows:
        if isinstance(row, str):
            col = row
        elif isinstance(row, dict):
            col = row.get('COLUMN_NAME') or row.get('column_name') or row.get('Column_Name')
        elif isinstance(row, (list, tuple)) and row:
            col = row[0]
        else:
            col = ''
        col = str(col or '').strip()
        if col:
            columns.append(col)
    return columns


def _fba_shipping_row_to_item(row, columns):
    if isinstance(row, dict):
        return {col: row.get(col) if col in row else row.get(col.lower()) for col in columns}
    if isinstance(row, (list, tuple)):
        return {col: (row[idx] if idx < len(row) else None) for idx, col in enumerate(columns)}
    return {col: None for col in columns}


def _fba_shipping_format_value(
    value,
    *,
    date,
    datetime,
):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return str(value)


def _fba_shipping_is_scientific(
    value,
    *,
    re,
):
    text = str(value or '').strip()
    if not text:
        return False
    return bool(re.fullmatch(r'[+-]?\d+(?:\.\d+)?[eE][+-]?\d+', text))


def _fba_shipping_sql_empty_expr(
    column_name,
    *,
    _fba_shipping_sql_ident,
):
    return f"NULLIF(LTRIM(RTRIM(ISNULL(CAST({_fba_shipping_sql_ident(column_name)} AS NVARCHAR(200)), N''))), N'') IS NULL"


def _fba_shipping_sql_scientific_expr(
    column_name,
    *,
    _fba_shipping_sql_ident,
):
    text_expr = f"UPPER(LTRIM(RTRIM(ISNULL(CAST({_fba_shipping_sql_ident(column_name)} AS NVARCHAR(200)), N''))))"
    return (
        f"({text_expr} LIKE '[0-9]%%E[+-][0-9]%%' "
        f"OR {text_expr} LIKE '+[0-9]%%E[+-][0-9]%%' "
        f"OR {text_expr} LIKE '-[0-9]%%E[+-][0-9]%%')"
    )


def _fba_shipping_issue_clause(
    shipping_col,
    cargo_col,
    *,
    _fba_shipping_sql_empty_expr,
    _fba_shipping_sql_ident,
    _fba_shipping_sql_scientific_expr,
):
    if not cargo_col:
        return ''
    clauses = []
    if shipping_col:
        clauses.append(
            f"(CHARINDEX(N'海运', ISNULL(CAST({_fba_shipping_sql_ident(shipping_col)} AS NVARCHAR(200)), N'')) > 0 "
            f"AND {_fba_shipping_sql_empty_expr(cargo_col)})"
        )
    clauses.append(_fba_shipping_sql_scientific_expr(cargo_col))
    return '(' + ' OR '.join(clauses) + ')'


def _fba_shipping_prepare_payload_item(
    row_item,
    columns,
    sea_col,
    cargo_col,
    *,
    _fba_shipping_format_value,
    _fba_shipping_is_scientific,
    re,
):
    values = {}
    for col in columns:
        values[col] = _fba_shipping_format_value(row_item.get(col))

    warning_fields = {}
    shipping_text = values.get(sea_col, '') if sea_col else ''
    cargo_text = values.get(cargo_col, '') if cargo_col else ''
    cargo_count = len([
        part for part in re.split(r'[;,，；\s]+', cargo_text)
        if part.strip()
    ]) if cargo_text.strip() else 0
    if sea_col and cargo_col and '海运' in shipping_text and not cargo_text.strip():
        warning_fields[sea_col] = '运输方式包含“海运”，但亚马逊追踪码为空'
        warning_fields[cargo_col] = '海运亚马逊追踪码为空'
    if cargo_col and _fba_shipping_is_scientific(cargo_text):
        warning_fields[cargo_col] = '亚马逊追踪码为科学计数法'
    return {
        'values': values,
        'cargo_count': cargo_count,
        'warning': bool(warning_fields),
        'warning_fields': warning_fields,
    }


def _fba_shipping_response_columns(
    columns,
    *,
    _fba_shipping_label,
    _fba_shipping_pick_col,
):
    """Arrange the FBA query columns with tracking fields together and import time last."""
    result = []
    inserted = False
    ien_col = _fba_shipping_pick_col(columns, ['ien', 'IEN'])
    import_col = _fba_shipping_pick_col(columns, ['导入时间', 'DaoRuShiJian', 'daorushijian', 'import_time', 'shijian'])
    for col in columns:
        if import_col and col == import_col:
            continue
        result.append({'key': col, 'label': _fba_shipping_label(col)})
        if ien_col and col == ien_col:
            result.append({'key': '__cargo_count__', 'label': '亚马逊追踪码个数'})
            inserted = True
    if import_col:
        result.append({'key': import_col, 'label': _fba_shipping_label(import_col)})
    return result


def _fba_shipping_sort_columns(
    columns,
    *,
    _fba_shipping_pick_col,
):
    seq_col = _fba_shipping_pick_col(columns, ['序号', 'ID', 'id', 'xh', 'xuhao'])
    import_col = _fba_shipping_pick_col(columns, ['导入时间', 'DaoRuShiJian', 'daorushijian', 'import_time', 'shijian'])
    return seq_col, import_col
