import ast
import sqlite3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InnovationPointDedupTests(unittest.TestCase):
    def test_project_rewards_count_once_without_merging_distinct_projects(self):
        tree = ast.parse((ROOT / 'innovation/web_app.py').read_text(encoding='utf-8'))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == '_PROJECT_POINTS_SQL' for t in node.targets))
        query = ast.literal_eval(assignment.value).replace('ISNULL(', 'IFNULL(')
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        db.create_function('ISNUMERIC', 1, lambda value: str(value).isdigit())
        db.execute('CREATE TABLE v_quanyuanchuangxin (编号 INT, 发起人 TEXT, 标题 TEXT, 发起时间 TEXT, 最高分 INT)')
        db.executemany('INSERT INTO v_quanyuanchuangxin VALUES (?, ?, ?, ?, ?)', [
            (2569, '测试人', '项目一', '2026-06-06', 20),
            (2569, '测试人', '项目一', '2026-06-06', 20),
            (2472, '测试人', '项目二', '2026-05-15', 20),
            (2472, '测试人', '项目二', '2026-05-15', 10),
            (2399, '测试人', '项目三', '2026-03-09', 10),
            (2399, '测试人', '项目三', '2026-03-09', 10),
            (999, '其他人', '其他项目', '2026-01-01', 100),
        ])
        rows = db.execute(f'SELECT 编号, 最高分 FROM ({query}) p WHERE 发起人 = ?', ('测试人',)).fetchall()
        self.assertEqual(dict(rows), {2569: 20, 2472: 20, 2399: 10})
        self.assertEqual(len(rows), 3)
        total = db.execute(f'SELECT SUM(最高分) FROM ({query}) p WHERE 发起人 = ?', ('测试人',)).fetchone()[0]
        self.assertEqual(total, 50)


if __name__ == '__main__':
    unittest.main()
