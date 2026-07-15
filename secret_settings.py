from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_dotenv(path: str | os.PathLike[str] | None = None, override: bool = False) -> None:
    env_path = Path(path) if path else DOTENV_PATH
    if not env_path.exists():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value


load_dotenv()


def env(key: str, default: str = "") -> str:
    return str(os.environ.get(key, default) or "").strip()


TUCHUANGAI_STORAGE_ROOT = Path(env("TUCHUANGAI_STORAGE_ROOT", r"D:\tuchuangai"))

_LEGACY_STORAGE_LOCATIONS = (
    (r"D:\TC服务器\data\2026.4.2-4.3百森战略拆解", TUCHUANGAI_STORAGE_ROOT / "2026.4.2-4.3百森战略拆解"),
    (r"D:\TC服务器\data\2026-7-9传世启动仪式", TUCHUANGAI_STORAGE_ROOT / "2026-7-9传世启动仪式"),
    (r"D:\TC服务器\data\2026-06-18年会图片", TUCHUANGAI_STORAGE_ROOT / "2026-06-18年会图片"),
    (r"D:\TC服务器\data\2026-06-18年会视频", TUCHUANGAI_STORAGE_ROOT / "2026-06-18年会视频"),
    (r"D:\TC服务器\data\3.17-战略分解培训", TUCHUANGAI_STORAGE_ROOT / "3.17-战略分解培训"),
    (r"D:\TC服务器\data\洛可可培训", TUCHUANGAI_STORAGE_ROOT / "洛可可培训"),
    (r"D:\TC服务器\测试\4月16日.mp4", TUCHUANGAI_STORAGE_ROOT / "4月16日.mp4"),
    (r"D:\WorkOrder_Agent\uploads", TUCHUANGAI_STORAGE_ROOT / "uploads"),
    (r"D:\报告互动卡片图片", TUCHUANGAI_STORAGE_ROOT / "报告互动卡片图片"),
    (r"D:\报告缓存图片", TUCHUANGAI_STORAGE_ROOT / "报告缓存图片"),
    (r"D:\图片上传缓存", TUCHUANGAI_STORAGE_ROOT / "图片上传缓存"),
    (r"D:\日报历史分析", TUCHUANGAI_STORAGE_ROOT / "日报历史分析"),
    (r"D:\肌肤质感参考", TUCHUANGAI_STORAGE_ROOT / "肌肤质感参考"),
    (r"D:\视觉图片", TUCHUANGAI_STORAGE_ROOT / "视觉图片"),
    (r"D:\创新图片", TUCHUANGAI_STORAGE_ROOT / "创新图片"),
    (r"D:\报告图片", TUCHUANGAI_STORAGE_ROOT / "报告图片"),
    (r"D:\模特视频", TUCHUANGAI_STORAGE_ROOT / "模特视频"),
    (r"D:\点赞图片", TUCHUANGAI_STORAGE_ROOT / "点赞图片"),
    (r"D:\样板图", TUCHUANGAI_STORAGE_ROOT / "样板图"),
    (r"D:\AI图片", TUCHUANGAI_STORAGE_ROOT / "AI图片"),
    (r"D:\Seedance", TUCHUANGAI_STORAGE_ROOT / "Seedance"),
)


def relocate_storage_path(path_value: Any) -> str:
    """Map an absolute path from the former D: locations to the consolidated root."""
    raw = str(path_value or "").strip()
    if not raw or raw.startswith(("http://", "https://", "data:", "file://", "asset://")):
        return raw
    normalized = raw.replace("/", "\\")
    normalized_key = normalized.casefold()
    for legacy_path, current_path in _LEGACY_STORAGE_LOCATIONS:
        legacy_key = legacy_path.casefold()
        if normalized_key != legacy_key and not normalized_key.startswith(legacy_key + "\\"):
            continue
        suffix = normalized[len(legacy_path) :].lstrip("\\")
        if not suffix:
            return str(current_path)
        return str(current_path.joinpath(*[part for part in suffix.split("\\") if part]))
    return raw


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except Exception:
        return default


def env_json_dict(key: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_value = env(key)
    if not raw_value:
        return dict(default or {})
    try:
        loaded = json.loads(raw_value)
    except Exception:
        return dict(default or {})
    return loaded if isinstance(loaded, dict) else dict(default or {})


def sql_server_config(include_port: bool = False) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "server": env("DB_SERVER") or env("SQLSERVER_SERVER"),
        "database": env("DB_DATABASE") or env("DB_NAME") or env("SQLSERVER_DATABASE"),
        "user": env("DB_USER") or env("SQLSERVER_USER"),
        "password": env("DB_PASSWORD") or env("SQLSERVER_PASSWORD"),
    }
    if include_port:
        cfg["port"] = env_int("DB_PORT", env_int("SQLSERVER_PORT", 1433))
    return cfg


def get_feishu_config() -> dict[str, str]:
    return {
        "app_id": env("FEISHU_APP_ID"),
        "app_secret": env("FEISHU_APP_SECRET"),
        "production_domain": env("FEISHU_PRODUCTION_DOMAIN"),
        "callback_path": env("FEISHU_CALLBACK_PATH", "/feishu/callback"),
        "encrypt_key": env("FEISHU_ENCRYPT_KEY"),
        "verification_token": env("FEISHU_VERIFICATION_TOKEN"),
    }


def get_feishu_message_config() -> dict[str, str]:
    primary = get_feishu_config()
    return {
        "app_id": env("FEISHU_MESSAGE_APP_ID") or primary["app_id"],
        "app_secret": env("FEISHU_MESSAGE_APP_SECRET") or primary["app_secret"],
    }


def get_feishu_company_config(company_key: str) -> dict[str, str]:
    prefix = f"FEISHU_{company_key.upper()}_"
    return {
        "app_id": env(prefix + "APP_ID"),
        "app_secret": env(prefix + "APP_SECRET"),
        "verification_token": env(prefix + "VERIFICATION_TOKEN"),
        "encrypt_key": env(prefix + "ENCRYPT_KEY"),
    }


def get_feishu_company_configs() -> dict[str, dict[str, str]]:
    configs = {
        "company1": get_feishu_company_config("company1"),
        "company2": get_feishu_company_config("company2"),
    }
    if not configs["company1"].get("app_id"):
        configs["company1"] = {
            "app_id": env("FEISHU_APP_ID"),
            "app_secret": env("FEISHU_APP_SECRET"),
            "verification_token": env("FEISHU_VERIFICATION_TOKEN"),
            "encrypt_key": env("FEISHU_ENCRYPT_KEY"),
        }
    return configs


def baidu_translate_config() -> dict[str, str]:
    return {
        "app_id": env("BAIDU_TRANSLATE_APP_ID"),
        "secret_key": env("BAIDU_TRANSLATE_SECRET_KEY"),
    }


def ai_runtime_config() -> dict[str, str]:
    return {
        "provider": env("AI_PROVIDER", "siliconflow"),
        "api_key": env("OPENAI_API_KEY") or env("SILICONFLOW_API_KEY"),
        "base_url": env("OPENAI_BASE_URL") or env("SILICONFLOW_BASE_URL"),
        "text_model": env("OPENAI_TEXT_MODEL"),
        "vision_model": env("OPENAI_VISION_MODEL"),
    }


def image_site_config_namespace() -> dict[str, Any]:
    openrouter_key = env("OPENROUTER_API_KEY")
    jimeng_access_key = env("JIMENG_ACCESS_KEY_ID") or env("VOLCENGINE_ACCESS_KEY_ID")
    jimeng_secret_key = env("JIMENG_SECRET_ACCESS_KEY") or env("VOLCENGINE_SECRET_ACCESS_KEY")
    return {
        "open_routher_api_key": openrouter_key,
        "openrouter_api_key": openrouter_key,
        "OPENROUTER_API_KEY": openrouter_key,
        "server_address": env("LASHFORGE_SERVER_ADDRESS", "0.0.0.0"),
        "server_port": env_int("LASHFORGE_SERVER_PORT", 8501),
        "public_app_url": env("LASHFORGE_PUBLIC_APP_URL"),
        "login_accounts": env_json_dict("LASHFORGE_LOGIN_ACCOUNTS_JSON", {"admin": env("LASHFORGE_ADMIN_PASSWORD", "")}),
        "jimeng_jimeng_api_key": env("JIMENG_JIMENG_API_KEY") or env("SEEDANCE_API_KEY"),
        "jimeng_static_port": env_int("JIMENG_STATIC_PORT", 8502),
        "jimeng_public_upload_base_url": env("JIMENG_PUBLIC_UPLOAD_BASE_URL"),
        "jimeng_access_key_id": jimeng_access_key,
        "jimeng_secret_access_key": jimeng_secret_key,
        "JIMENG_ACCESS_KEY_ID": jimeng_access_key,
        "JIMENG_SECRET_ACCESS_KEY": jimeng_secret_key,
        "VOLCENGINE_ACCESS_KEY_ID": jimeng_access_key,
        "VOLCENGINE_SECRET_ACCESS_KEY": jimeng_secret_key,
    }


FEISHU_CONFIG = get_feishu_config()
