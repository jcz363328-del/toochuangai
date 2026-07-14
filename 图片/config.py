import os
import sys


_CONFIG_DIR = os.path.dirname(os.path.abspath(globals().get("__file__", "config.py")))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CONFIG_DIR, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from secret_settings import image_site_config_namespace


globals().update(image_site_config_namespace())
