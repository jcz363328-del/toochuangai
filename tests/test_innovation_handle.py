import importlib

import innovation_blueprint  # noqa: F401 - prepares the innovation module path


web_app = importlib.import_module('innovation.web_app')


class _MessageServiceStub:
    def send_handle_notification(self, **_kwargs):
        return True


def test_immediate_adoption_accepts_percent_in_notes_and_stores_score(monkeypatch):
    queries = []
    writes = []

    def fake_query(sql):
        queries.append(sql)
        if '标题, 发起人' in sql:
            return [('PC端查看手机端展示效果', '叶雨菲')]
        if '委员会打分 IS NOT NULL' in sql:
            return []
        if 'SELECT MAX' in sql:
            return [20]
        raise AssertionError(f'未预期的查询: {sql}')

    monkeypatch.setattr(web_app, 'sf_db', fake_query)
    monkeypatch.setattr(web_app, 'dui_db', writes.append)
    monkeypatch.setattr(web_app, 'get_message_service', lambda: _MessageServiceStub())

    payload = {
        'innovation_id': 2765,
        'flow_id': 5303,
        'status': '进行中',
        'handler': '郭鑫',
        'handler_notes': '手机端用户占比75%以上',
        'score': 'C',
        'operation_type': '采纳，立即执行',
    }

    with web_app.app.test_request_context(json=payload):
        response = web_app.handle_innovation()

    assert response.status_code == 200
    assert response.get_json()['success'] is True
    assert len(writes) == 2
    assert "分数 = '20'" in writes[0]
    assert "操作类型='采纳，立即执行'" in writes[0]
    assert '75%%以上' in writes[0]
    assert '75%以上' in (writes[0] % ())
    assert '得分 = 20' in writes[1]


def test_immediate_adoption_requires_a_score(monkeypatch):
    writes = []
    monkeypatch.setattr(web_app, 'dui_db', writes.append)

    payload = {
        'innovation_id': 2765,
        'flow_id': 5303,
        'status': '进行中',
        'handler': '郭鑫',
        'handler_notes': '同意立即执行',
        'score': '',
        'operation_type': '采纳，立即执行',
    }

    with web_app.app.test_request_context(json=payload):
        response, status_code = web_app.handle_innovation()

    assert status_code == 400
    assert response.get_json()['message'] == '请选择提案评分'
    assert writes == []
