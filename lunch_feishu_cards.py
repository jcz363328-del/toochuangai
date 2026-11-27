"""兼容旧导入路径；实现迁至 Department.人力资源与行政部.lunch_feishu_cards。"""
import sys
from Department.人力资源与行政部 import lunch_feishu_cards as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.人力资源与行政部.lunch_feishu_cards", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
