"""旧导入兼容入口。"""
import sys
from core.config import secret_settings as _implementation
sys.modules[__name__] = _implementation
