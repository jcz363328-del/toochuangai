"""兼容旧导入路径；实现迁至 Department.技术部.review_analysis。"""
import sys
from Department.技术部 import review_analysis as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.技术部.review_analysis", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
