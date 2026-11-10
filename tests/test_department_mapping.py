import unittest

from department_permissions import DEPARTMENT_ID_MAPPING


class DepartmentMappingTests(unittest.TestCase):
    def test_operation_departments_use_current_feishu_ids(self):
        expected = {
            "od-9fca123ccde5fe9b2e8705d01365e754": "运营部",
            "od-6d3c01c56d414c3b6ae96bc973b8ce70": "运营一部",
            "od-89f78f0f72f3bfee4741b8aa1570b6c9": "运营二部",
            "od-5ad4b6e18c3734622dbdae8ba05d27fd": "运营三部",
            "od-e5024d4f6711f478ce052274d5ce33ea": "运营六部",
            "od-ee2a36f326f6cfad44ce06a80f2f07e8": "运营七部",
        }
        for department_id, department_name in expected.items():
            with self.subTest(department_id=department_id):
                self.assertEqual(DEPARTMENT_ID_MAPPING.get(department_id), department_name)

    def test_content_factory_subdepartments_are_mapped(self):
        expected = {
            "od-c560effca33bf715c15f79a0670fe6ba": "内容生产工厂",
            "od-1fd573a06618d5efc50558aa4c6c8fde": "BD部",
            "od-9eac17d59c51684f90a0a6c78ffe21ef": "BD二组",
            "od-8e234df817e0707418b6fa50b1acd9c4": "BD三组",
            "od-d98b885bdc8ee6cc33b62707404e8a43": "BD四组",
            "od-884d568d0952416a876a77c087a1d15a": "BD一组",
        }
        for department_id, department_name in expected.items():
            with self.subTest(department_id=department_id):
                self.assertEqual(DEPARTMENT_ID_MAPPING.get(department_id), department_name)


if __name__ == "__main__":
    unittest.main()
