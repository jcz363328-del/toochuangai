"""兼容旧导入路径；实现迁至 Department.内容生产工厂.tk_gmv_authorization。"""
import sys
from Department.内容生产工厂 import tk_gmv_authorization as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.内容生产工厂.tk_gmv_authorization", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
