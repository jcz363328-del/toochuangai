"""旧导入兼容入口。"""
import sys
from integrations.feishu import cloud_documents as _implementation
sys.modules[__name__] = _implementation
