"""兼容旧导入路径；实现迁至 Department.总经办.business_analysis_key_tasks。"""
import sys
from Department.总经办 import business_analysis_key_tasks as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.总经办.business_analysis_key_tasks", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
