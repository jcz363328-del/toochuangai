"""旧导入兼容入口。"""
import sys
from Department.视觉设计部.xiaoha.features import a_plus_canvas as _implementation
sys.modules[__name__] = _implementation
