"""旧导入兼容入口。"""
import sys
from core.database import bjc as _implementation
sys.modules[__name__] = _implementation
