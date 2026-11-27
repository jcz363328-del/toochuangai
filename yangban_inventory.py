"""兼容旧导入路径；实现迁至 Department.采购部.yangban_inventory。"""
import sys
from Department.采购部 import yangban_inventory as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.采购部.yangban_inventory", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
