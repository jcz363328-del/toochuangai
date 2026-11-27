"""兼容旧导入路径；实现迁至 Department.财务部.shenzhen_total。"""
import sys
from Department.财务部 import shenzhen_total as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.财务部.shenzhen_total", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
