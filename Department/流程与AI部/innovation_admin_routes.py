"""Provide the innovation administration tools exposed in the AI workspace."""

from __future__ import annotations


def api_ai_delete_innovation_project(
    *,
    dui_db,
    jsonify,
    request,
):
    try:
        data = request.get_json(silent=True) or {}
        project_id_raw = data.get('project_id')
        project_id = str(project_id_raw or '').strip()
        if not project_id:
            return jsonify({'success': False, 'message': '项目编号不能为空'}), 400
        if not project_id.isdigit():
            return jsonify({'success': False, 'message': '项目编号必须为数字'}), 400
        sql_flow = f"DELETE FROM chuangxin_liuzhuan1 WHERE 项目编号 = {project_id}"
        sql_main = f"DELETE FROM chuangxin_tibao1 WHERE 编号 = {project_id}"
        dui_db(sql_flow)
        dui_db(sql_main)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500


def api_ai_innovation_project_preview(
    *,
    jsonify,
    request,
    sf_db,
):
    try:
        project_id = str(request.args.get('project_id') or '').strip()
        if not project_id:
            return jsonify({'success': False, 'message': '项目编号不能为空'}), 400
        if not project_id.isdigit():
            return jsonify({'success': False, 'message': '项目编号必须为数字'}), 400

        rows = sf_db(f"""
            SELECT TOP 1
                ISNULL(CAST(标题 AS NVARCHAR(MAX)), ''),
                ISNULL(CAST(内容 AS NVARCHAR(MAX)), '')
            FROM chuangxin_tibao1
            WHERE 编号 = {project_id}
        """) or []
        if not rows:
            return jsonify({'success': False, 'message': f'未找到编号为 {project_id} 的创新项目'}), 404

        project = rows[0]
        return jsonify({
            'success': True,
            'data': {
                'project_id': project_id,
                'title': str(project[0] or '').strip(),
                'content': str(project[1] or '').strip()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'读取项目内容失败: {str(e)}'}), 500


def api_ai_innovation_pending_reminder_test_send(
    *,
    datetime,
    innovation_pending_reminder,
    jsonify,
    sf_db,
):
    try:
        result = innovation_pending_reminder.run_once(
            now_dt=datetime.now(),
            send_messages=True,
            include_message_details=True,
        )

        recipient_ids = []
        for assignee_result in (result.get('assignees') or {}).values():
            for recipient in assignee_result.get('recipients') or []:
                recipient_id = str(recipient.get('id') or '').strip()
                if recipient_id and recipient_id not in recipient_ids:
                    recipient_ids.append(recipient_id)

        recipient_name_map = {}
        if recipient_ids:
            id_sql = ",".join(
                f"N'{recipient_id.replace("'", "''")}'"
                for recipient_id in recipient_ids
            )
            rows = sf_db(f"""
                SELECT FeiShu_ID, YongHu
                FROM feishu_id
                WHERE FeiShu_ID IN ({id_sql})
            """) or []
            for row in rows:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                recipient_id = str(row[0] or '').strip()
                recipient_name = str(row[1] or '').strip()
                if recipient_id and recipient_name and recipient_id not in recipient_name_map:
                    recipient_name_map[recipient_id] = recipient_name

        for assignee, assignee_result in (result.get('assignees') or {}).items():
            for recipient in assignee_result.get('recipients') or []:
                recipient_id = str(recipient.get('id') or '').strip()
                recipient['name'] = str(recipient.get('name') or '').strip() or recipient_name_map.get(recipient_id) or (
                    assignee if recipient_id == assignee else recipient_id
                )

        return jsonify({
            'success': True,
            'message': '查询与发送已完成',
            'data': result,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'测试发送失败: {str(e)}'}), 500


def innovation_pending_reminder_test_page(*, render_template):
    return render_template('流程与AI部/innovation_pending_reminder_test.html')
