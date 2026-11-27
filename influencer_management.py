"""兼容旧导入路径；实现迁至 Department.内容生产工厂.influencer_management。"""
import sys
from Department.内容生产工厂 import influencer_management as _implementation
if __name__ == "__main__":
    import runpy
    runpy.run_module("Department.内容生产工厂.influencer_management", run_name="__main__")
else:
    sys.modules[__name__] = _implementation
