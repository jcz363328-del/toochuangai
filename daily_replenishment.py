"""兼容旧导入路径；实现迁至 Department.流程与AI部.daily_replenishment。"""
import sys
from Department.流程与AI部 import daily_replenishment as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.流程与AI部.daily_replenishment", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
