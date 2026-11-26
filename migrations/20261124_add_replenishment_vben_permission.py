"""Register an independent AI replenishment entry, preserving the operations entry."""
from __future__ import annotations
import importlib.util
from pathlib import Path

def apply_migration():
    source = Path(__file__).with_name('20261116_add_daily_replenishment_tiktok_permission.py')
    spec = importlib.util.spec_from_file_location('replenishment_permission_migration', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PERMISSION_ROW = {
        'gongneng': 'replenishment_vben', 'yonghu': '', 'bumen': 'AI部；流程与AI部',
        'fujigongneng': 'ai_dept', 'mingcheng': '智能补货中心-AI版',
        'miaoshu': '独立Vue补货中心，逐行15天销量动态走势，按原店铺权限读写',
    }
    module.apply_migration()

if __name__ == '__main__':
    apply_migration()
    print('replenishment_vben_permission=applied')
