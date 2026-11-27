"""兼容旧导入路径；实现迁至 Department.内容生产工厂.tk_customer_service_reminder。"""
import sys
from Department.内容生产工厂 import tk_customer_service_reminder as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.内容生产工厂.tk_customer_service_reminder", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
