"""兼容旧导入路径；实现迁至 Department.运营部.daily_replenishment_operation。"""
import sys
from Department.运营部 import daily_replenishment_operation as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.运营部.daily_replenishment_operation", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
