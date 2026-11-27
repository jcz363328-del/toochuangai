from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from flask import Flask, abort, jsonify, render_template, request, send_file, url_for

from lunch_push import GROUPS, LunchPush, TZ, is_due, next_trigger


def entries():
    return [{'scope': scope, 'meal': meal, 'count': 2, 'recipient': GROUPS[scope][1], 'card': {}}
            for scope in GROUPS for meal in ('堂食', '盒饭')]


class LunchPushTests(unittest.TestCase):
    def test_schedule_uses_beijing_time_and_retries_only_in_morning(self):
        self.assertFalse(is_due(datetime(2026, 11, 25, 1, 24, tzinfo=timezone.utc)))
        self.assertTrue(is_due(datetime(2026, 11, 25, 1, 25, tzinfo=timezone.utc)))
        self.assertFalse(is_due(datetime(2026, 11, 25, 2, 0, tzinfo=timezone.utc)))
        friday = datetime(2026, 11, 27, 10, tzinfo=TZ)
        self.assertEqual(next_trigger(friday), datetime(2026, 11, 28, 9, 25, tzinfo=TZ))

    def test_receipts_survive_restart_and_route_to_two_groups(self):
        with TemporaryDirectory() as folder, patch.object(LunchPush, 'preview', return_value=entries()), \
             patch.object(LunchPush, 'token', return_value='test'), \
             patch.object(LunchPush, 'send_card', return_value='om_test') as send:
            first = LunchPush(folder).run_once()
            second = LunchPush(folder).run_once()
            self.assertEqual([r['status'] for r in first], ['sent'] * 4)
            self.assertEqual([r['status'] for r in second], ['skipped'] * 4)
            self.assertEqual(send.call_count, 4)
            self.assertEqual([call.args[1] for call in send.call_args_list],
                             [GROUPS['all'][1]] * 2 + [GROUPS['tk'][1]] * 2)

    def test_retry_sends_only_failed_card_with_same_idempotency_key(self):
        with TemporaryDirectory() as folder, patch.object(LunchPush, 'preview', return_value=entries()), \
             patch.object(LunchPush, 'token', return_value='test'), \
             patch.object(LunchPush, 'send_card', side_effect=[RuntimeError('network'), 'm2', 'm3', 'm4', 'm1']) as send:
            service = LunchPush(folder)
            with self.assertLogs(LunchPush.__module__, level='ERROR'):
                self.assertEqual(service.run_once()[0]['status'], 'failed')
            second = service.run_once()
            self.assertEqual([r['status'] for r in second], ['sent', 'skipped', 'skipped', 'skipped'])
            self.assertEqual(send.call_args_list[0].args[3], send.call_args_list[4].args[3])
            self.assertEqual(len(service.records()), 4)

    def test_two_instances_do_not_send_duplicates(self):
        with TemporaryDirectory() as folder, patch.object(LunchPush, 'preview', return_value=entries()), \
             patch.object(LunchPush, 'token', return_value='test'), \
             patch.object(LunchPush, 'send_card', return_value='om_test') as send:
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda service: service.run_once(), [LunchPush(folder), LunchPush(folder)]))
            self.assertEqual(send.call_count, 4)
            self.assertEqual(sum(r['status'] == 'sent' for result in results for r in result), 4)

    def test_preview_queries_selected_date_and_excludes_non_tk_from_tk_cards(self):
        with TemporaryDirectory() as folder, patch('lunch_push.pytds.connect') as database:
            cursor = database.return_value.__enter__.return_value.cursor.return_value
            cursor.fetchall.return_value = [
                ('技术', '甲', '堂食', '技术'),
                ('内容生产工厂', '乙', '堂食', '内容生产工厂')]
            day = datetime(2026, 11, 25, tzinfo=TZ).date()
            cards = LunchPush(folder).preview(day)
            self.assertEqual(cursor.execute.call_args.args[1], (day, day))
            self.assertEqual([entry['count'] for entry in cards], [2, 0, 1, 0])
            self.assertNotIn('测试', cards[0]['card']['header']['title']['content'])
            image = cards[0]['card']['body']['elements'][1]['img_key']
            self.assertTrue(Path(image).is_file())

    def test_retry_limit_does_not_resend_successful_cards(self):
        with TemporaryDirectory() as folder, patch.object(LunchPush, 'preview', return_value=entries()), \
             patch.object(LunchPush, 'token', return_value='test'), \
             patch.object(LunchPush, 'send_card', side_effect=RuntimeError('network')) as send:
            with self.assertLogs(LunchPush.__module__, level='ERROR'):
                for _ in range(6):
                    LunchPush(folder).run_once()
            self.assertEqual(send.call_count, 20)


class LunchPushPageTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'))
        self.app.add_url_rule('/ai_modules', endpoint='ai_modules', view_func=lambda: '')
        self.allowed = True
        self.service = Mock()
        self.service.last_error = ''
        self.service.preview.return_value = []
        self.service.records.return_value = []
        self.service.run_once.return_value = [{'status': 'sent'}]
        namespace = dict(app=self.app, _can_access_ai_workspace=lambda: self.allowed,
                         lunch_push=self.service, env=lambda k, d: d,
                         jsonify=jsonify, render_template=render_template, request=request,
                         url_for=url_for, send_file=send_file, abort=abort)
        from functools import partial
        from inspect import Parameter, signature
        from Department.人力资源与行政部 import lunch_push_routes

        routes = (
            ('/ai/lunch-push', lunch_push_routes.lunch_push_page, ['GET']),
            ('/api/ai/lunch-push', lunch_push_routes.lunch_push_api, ['GET', 'POST']),
            ('/api/ai/lunch-push/image/<filename>', lunch_push_routes.lunch_push_image, ['GET']),
        )
        for path, handler, methods in routes:
            dependencies = {
                key: namespace[key] for key, parameter in signature(handler).parameters.items()
                if parameter.kind == Parameter.KEYWORD_ONLY
            }
            self.app.add_url_rule(path, handler.__name__, partial(handler, **dependencies), methods=methods)
        self.client = self.app.test_client()

    def test_ai_only_guard_covers_page_api_and_images(self):
        self.allowed = False
        for path in ('/ai/lunch-push', '/api/ai/lunch-push', '/api/ai/lunch-push/image/file.png'):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post('/api/ai/lunch-push', json={'action': 'send'}).status_code, 403)
        self.service.run_once.assert_not_called()

    def test_preview_is_read_only_and_page_renders(self):
        self.assertEqual(self.client.get('/ai/lunch-push').status_code, 200)
        self.assertTrue(self.client.get('/api/ai/lunch-push').json['success'])
        self.service.run_once.assert_not_called()
        self.assertEqual(self.client.post('/api/ai/lunch-push', json={'action': 'bad'}).status_code, 400)
        self.assertEqual(self.client.post('/api/ai/lunch-push', json={'action': 'test'}).status_code, 200)
        self.service.run_once.assert_called_once_with(test=True)


if __name__ == '__main__':
    unittest.main()
