"""旧导入兼容入口。"""
import sys
from core.permissions import department_permissions as _implementation
sys.modules[__name__] = _implementation
