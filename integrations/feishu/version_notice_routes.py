"""Authorize and deliver Feishu update notices."""

from __future__ import annotations


def api_ai_version_update_notice(
    *,
    datetime,
    get_message_service,
    jsonify,
    request,
    sf_db,
):
    try:
        data = request.get_json(silent=True) or {}
        template_text = (data.get('template') or '').strip()
        content = (data.get('content') or '').strip()
        departments = data.get('departments')
        if isinstance(departments, str):
            departments = [departments]
        departments = [d.strip() for d in (departments or []) if str(d).strip()]
        at_all = bool(data.get('at_all'))
        if not template_text:
            return jsonify({'success': False, 'message': '话术模板不能为空'}), 400
        full_message = template_text
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        if '[更新日期]' in full_message or '【更新日期】' in full_message:
            full_message = full_message.replace('[更新日期]', now_str).replace('【更新日期】', now_str)
        if content:
            replaced = False
            for ph in ['[简要描述]', '【简要描述】', '【在这里填写本次更新的主要内容】']:
                if ph in full_message:
                    full_message = full_message.replace(ph, content)
                    replaced = True
                    break
            if not replaced:
                if full_message.endswith('\n'):
                    full_message = full_message + content
                else:
                    full_message = full_message + '\n\n' + content
        if not departments:
            return jsonify({'success': False, 'message': '推送部门不能为空'}), 400
        message_service = get_message_service()
        # 如果选择了“全部部门”，忽略其他部门，按原有全员逻辑发送
        if '__ALL__' in departments:
            rows = sf_db("SELECT DISTINCT YONGHU FROM feishu_id WHERE FeiShu_ID LIKE 'od_%' ORDER BY YONGHU")
            names = []
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and 'YONGHU' in r:
                        names.append(r['YONGHU'])
                    elif isinstance(r, str):
                        names.append(r)
            elif isinstance(rows, dict) and 'YONGHU' in rows:
                names.append(rows['YONGHU'])
            elif isinstance(rows, str):
                names.append(rows)
            uniq = []
            seen = set()
            for n in names:
                n = (n or '').strip()
                if n and n not in seen:
                    seen.add(n)
                    uniq.append(n)
            total_success = 0
            total_failed = 0
            total_count = 0
            for dept_name in uniq:
                try:
                    r = message_service.send_message_to_department_members(dept_name, full_message, at_all=at_all)
                    total_success += r.get('success', 0)
                    total_failed += r.get('failed', 0)
                    total_count += r.get('total', 0)
                except Exception:
                    total_failed += 1
            result = {
                'success': total_success,
                'failed': total_failed,
                'total': total_count,
                'department_count': len(uniq)
            }
        else:
            total_success = 0
            total_failed = 0
            total_count = 0
            for dept_name in departments:
                try:
                    r = message_service.send_message_to_department_members(dept_name, full_message, at_all=at_all)
                    total_success += r.get('success', 0)
                    total_failed += r.get('failed', 0)
                    total_count += r.get('total', 0)
                except Exception:
                    total_failed += 1
            result = {
                'success': total_success,
                'failed': total_failed,
                'total': total_count,
                'department_count': len(departments)
            }
        return jsonify({'success': True, 'message': '发送完成', 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def api_ai_version_update_departments(
    *,
    jsonify,
    sf_db,
):
    try:
        rows = sf_db("SELECT DISTINCT YONGHU FROM feishu_id WHERE FeiShu_ID LIKE 'od_%' ORDER BY YONGHU")
        names = []
        if isinstance(rows, list):
            for r in rows:
                if isinstance(r, dict) and 'YONGHU' in r:
                    names.append(r['YONGHU'])
                elif isinstance(r, str):
                    names.append(r)
        elif isinstance(rows, dict) and 'YONGHU' in rows:
            names.append(rows['YONGHU'])
        elif isinstance(rows, str):
            names.append(rows)
        uniq = []
        seen = set()
        for n in names:
            n = (n or '').strip()
            if n and n not in seen:
                seen.add(n)
                uniq.append({'name': n})
        return jsonify({'success': True, 'data': uniq})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'data': []}), 500
