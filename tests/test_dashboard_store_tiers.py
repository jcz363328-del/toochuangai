import unittest

from app import _build_dashboard_store_tier_index


class DashboardStoreTierTests(unittest.TestCase):
    def test_indexes_only_latest_day_and_sorts_stores(self):
        snapshot = {
            'maxDate': '2026-10-15',
            'rows': [
                {'date': '2026-10-14', 'store': 1, 'tier': '银1', 'operator': '张三'},
                {'date': '2026-10-15', 'store': 12, 'tier': '金2', 'operator': ' 张三 '},
                {'date': '2026-10-15', 'store': 3, 'tier': '钻1', 'operator': '张三'},
                {'date': '2026-10-15', 'store': 8, 'tier': '银3', 'operator': '李四'},
            ],
        }

        data_date, by_operator = _build_dashboard_store_tier_index(snapshot)

        self.assertEqual(data_date, '2026-10-15')
        self.assertEqual(by_operator['张三'], [
            {'store': '3', 'tier': '钻1'},
            {'store': '12', 'tier': '金2'},
        ])
        self.assertEqual(by_operator['李四'], [{'store': '8', 'tier': '银3'}])


if __name__ == '__main__':
    unittest.main()
