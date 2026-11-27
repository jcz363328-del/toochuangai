"""人力行政入口和创新数据查询导出。"""
from datetime import date, datetime
from flask import jsonify, render_template, request, send_file
from bjc import sf_db


def register_hr_routes(app, require_permission):
    @app.route('/hr_admin_modules')
    @require_permission('hr_admin_dept')
    def hr_admin_modules():
        return render_template('人力资源与行政部/hr_admin_modules.html')


    @app.route('/hr_admin/innovation_data')
    @require_permission('hr_admin_dept')
    def hr_admin_innovation_data():
        return render_template('人力资源与行政部/hr_innovation_data.html')


    def _hr_innovation_json_value(value):
        if value is None:
            return ""
        if isinstance(value, (int, float, str, bool)):
            return value
        try:
            import decimal
            if isinstance(value, decimal.Decimal):
                return float(value)
        except Exception:
            pass
        if isinstance(value, (datetime, date)):
            return value.strftime('%Y-%m-%d')
        return str(value)


    def _hr_innovation_normalize_rows(rows, columns):
        out = []
        for row in rows or []:
            if isinstance(row, dict):
                item = {}
                for col in columns:
                    item[col] = _hr_innovation_json_value(row.get(col) if col in row else row.get(str(col).lower()))
                out.append(item)
                continue
            values = list(row) if isinstance(row, (list, tuple)) else []
            out.append({
                col: _hr_innovation_json_value(values[idx] if idx < len(values) else "")
                for idx, col in enumerate(columns)
            })
        return out


    @app.route('/api/hr/innovation_data')
    @require_permission('hr_admin_dept')
    def api_hr_innovation_data():
        try:
            return jsonify({
                'success': True,
                'data': _load_hr_innovation_data(),
            })
        except Exception as e:
            return jsonify({'success': False, 'message': f'读取创新数据失败: {str(e)}'}), 500


    def _load_hr_innovation_data():
        monthly_total = sf_db("""
            SELECT
                CONVERT(VARCHAR(7), 发起时间, 120) AS 月份,
                COUNT(*) AS 数量
            FROM v_QuanYuanChuangXin
            GROUP BY CONVERT(VARCHAR(7), 发起时间, 120)
            ORDER BY 月份
        """) or []
        monthly_department_total = sf_db("""
            SELECT
                CONVERT(VARCHAR(7), 发起时间, 120) AS 月份,
                COUNT(*) AS 数量,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            GROUP BY CONVERT(VARCHAR(7), 发起时间, 120), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END
            ORDER BY 月份, 部门
        """) or []
        valid_department_total = sf_db("""
            SELECT
                CONVERT(VARCHAR(7), 发起时间, 120) AS 月份,
                COUNT(*) AS 有效提案数量,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            WHERE 最高分 > 0
            GROUP BY CONVERT(VARCHAR(7), 发起时间, 120), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END
            ORDER BY 月份, 部门
        """) or []
        monthly_people = sf_db("""
            SELECT DISTINCT
                CONVERT(char(7), 发起时间, 120) AS 月份,
                发起人,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            ORDER BY 月份, 部门, 发起人
        """) or []
        score_distribution = sf_db("""
            SELECT
                CONVERT(VARCHAR(7), 发起时间, 120) AS 月份,
                COUNT(*) AS 数量,
                最高分 AS 分数,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            GROUP BY CONVERT(VARCHAR(7), 发起时间, 120), CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END, 最高分
            ORDER BY 月份, 部门, 分数
        """) or []
        category_distribution = sf_db("""
            SELECT
                CONVERT(VARCHAR(7), 发起时间, 120) AS 月份,
                COUNT(*) AS 数量,
                创新类别,
                CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END AS 部门
            FROM v_QuanYuanChuangXin
            GROUP BY CONVERT(VARCHAR(7), 发起时间, 120), 创新类别, CASE WHEN 部门 IN ('TK_离职','TK项目') THEN '内容生产工厂' ELSE 部门 END
            ORDER BY 月份, 创新类别, 部门
        """) or []
        return {
            'monthly_total': _hr_innovation_normalize_rows(monthly_total, ['月份', '数量']),
            'monthly_department_total': _hr_innovation_normalize_rows(monthly_department_total, ['月份', '数量', '部门']),
            'valid_department_total': _hr_innovation_normalize_rows(valid_department_total, ['月份', '有效提案数量', '部门']),
            'monthly_people': _hr_innovation_normalize_rows(monthly_people, ['月份', '发起人', '部门']),
            'score_distribution': _hr_innovation_normalize_rows(score_distribution, ['月份', '数量', '分数', '部门']),
            'category_distribution': _hr_innovation_normalize_rows(category_distribution, ['月份', '数量', '创新类别', '部门']),
        }


    def _filter_hr_innovation_data(data, months=None, department='', keyword=''):
        month_values = None if months is None else {str(value).strip() for value in months if str(value).strip()}
        department = str(department or '').strip()
        keyword = str(keyword or '').strip().casefold()
        filtered = {}
        for key, rows in (data or {}).items():
            matched_rows = []
            for row in rows or []:
                if month_values is not None and str(row.get('月份', '')).strip() not in month_values:
                    continue
                if department and '部门' in row and str(row.get('部门', '')).strip() != department:
                    continue
                if keyword:
                    haystack = ' '.join(str(value or '') for value in row.values()).casefold()
                    if keyword not in haystack:
                        continue
                matched_rows.append(row)
            filtered[key] = matched_rows

        if department:
            month_totals = {}
            for row in filtered.get('monthly_department_total', []):
                month = str(row.get('月份', '')).strip()
                month_totals[month] = month_totals.get(month, 0) + float(row.get('数量') or 0)
            filtered['monthly_total'] = [
                {'月份': month, '数量': int(value) if value.is_integer() else value}
                for month, value in sorted(month_totals.items())
            ]
        return filtered


    def _hr_innovation_excel_value(value):
        if value is None:
            return ''
        if isinstance(value, (int, float)):
            return value
        text_value = str(value)
        if text_value.startswith(('=', '+', '-', '@')):
            return "'" + text_value
        return text_value


    def _build_hr_innovation_workbook(data, selected_month_label, department='', keyword=''):
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        workbook = Workbook()
        overview = workbook.active
        overview.title = '数据概览'
        total_count = sum(float(row.get('数量') or 0) for row in data.get('monthly_total', []))
        valid_count = sum(float(row.get('有效提案数量') or 0) for row in data.get('valid_department_total', []))
        people_count = len({
            (row.get('月份'), row.get('部门'), row.get('发起人'))
            for row in data.get('monthly_people', [])
        })
        department_count = len({
            row.get('部门')
            for key in ('monthly_department_total', 'valid_department_total', 'monthly_people')
            for row in data.get(key, [])
            if row.get('部门')
        })
        overview_rows = [
            ('创新数据导出概览', ''),
            ('导出时间', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            ('月份范围', selected_month_label),
            ('部门', department or '全部部门'),
            ('关键词', keyword or '无'),
            ('提案总数', total_count),
            ('有效提案数', valid_count),
            ('参与人数', people_count),
            ('覆盖部门', department_count),
        ]
        for row in overview_rows:
            overview.append(row)

        sheet_specs = [
            ('月度提案总量', 'monthly_total', ['月份', '数量']),
            ('部门提案数量', 'monthly_department_total', ['月份', '部门', '数量']),
            ('部门有效提案', 'valid_department_total', ['月份', '部门', '有效提案数量']),
            ('月度发起人', 'monthly_people', ['月份', '部门', '发起人']),
            ('分数分布', 'score_distribution', ['月份', '部门', '分数', '数量']),
            ('创新类别', 'category_distribution', ['月份', '部门', '创新类别', '数量']),
        ]
        for title, data_key, columns in sheet_specs:
            worksheet = workbook.create_sheet(title=title)
            worksheet.append(columns)
            for item in data.get(data_key, []):
                worksheet.append([_hr_innovation_excel_value(item.get(column)) for column in columns])
            worksheet.freeze_panes = 'A2'
            worksheet.auto_filter.ref = worksheet.dimensions

        header_fill = PatternFill('solid', fgColor='2563EB')
        header_font = Font(color='FFFFFF', bold=True)
        thin_border = Border(bottom=Side(style='thin', color='DCE3EF'))
        for worksheet in workbook.worksheets:
            worksheet.sheet_view.showGridLines = False
            worksheet.freeze_panes = worksheet.freeze_panes or 'A2'
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
            worksheet.row_dimensions[1].height = 24
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical='center')
            for column_cells in worksheet.columns:
                max_length = max(
                    len(str(cell.value or '').replace('\n', ' '))
                    for cell in column_cells
                )
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 3, 12), 42)

        overview['A1'].fill = PatternFill('solid', fgColor='0F172A')
        overview['B1'].fill = PatternFill('solid', fgColor='0F172A')
        overview['A1'].font = Font(color='FFFFFF', bold=True, size=14)
        overview.column_dimensions['A'].width = 18
        overview.column_dimensions['B'].width = 44

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output


    @app.route('/api/hr/innovation_data/export')
    @require_permission('hr_admin_dept')
    def export_hr_innovation_data():
        try:
            month_mode = str(request.args.get('month_mode') or '').strip()
            selected_months = request.args.getlist('month')
            months = [] if month_mode == 'empty' else (selected_months or None)
            department = str(request.args.get('department') or '').strip()
            keyword = str(request.args.get('keyword') or '').strip()
            data = _filter_hr_innovation_data(
                _load_hr_innovation_data(),
                months=months,
                department=department,
                keyword=keyword,
            )
            selected_month_label = '全部月份' if months is None else ('、'.join(months) if months else '未选择月份')
            output = _build_hr_innovation_workbook(
                data,
                selected_month_label=selected_month_label,
                department=department,
                keyword=keyword,
            )
            filename = f"创新数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename,
            )
        except Exception as e:
            return jsonify({'success': False, 'message': f'导出创新数据失败: {str(e)}'}), 500

