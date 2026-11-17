import unittest
from unittest.mock import patch

from innovation import special_support


class SpecialPermissionInitializationTests(unittest.TestCase):
    def test_initialization_does_not_overwrite_existing_permissions(self):
        with patch.object(special_support, '_STORAGE_READY', False), \
                patch.object(special_support, 'dui_db') as execute, \
                patch.object(special_support.permission_manager, 'clear_cache'):
            special_support.ensure_special_storage()
        permission_sql = [call.args[0] for call in execute.call_args_list
                          if 'dbo.quanxian' in call.args[0]]
        self.assertEqual(len(permission_sql), 1)
        self.assertIn('IF NOT EXISTS', permission_sql[0])
        self.assertNotIn('UPDATE dbo.quanxian', permission_sql[0])


if __name__ == '__main__':
    unittest.main()
