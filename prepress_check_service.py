"""兼容旧导入路径；实现迁至 Department.视觉设计部.prepress_check_service。"""
import sys
from Department.视觉设计部 import prepress_check_service as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.视觉设计部.prepress_check_service", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
