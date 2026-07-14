import copy
import json
import mimetypes
import re
import threading
import time
import uuid
import base64
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from flask import Blueprint, Flask, abort, jsonify, render_template, request, send_file, session
from bjc import dui_db, sf_db
from department_permissions import permission_manager
from secret_settings import env

api_key = env("SEEDANCE_API_KEY") or env("VOLCENGINE_API_KEY")
base_url = env("SEEDANCE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODEL_SEEDANCE_2 = "doubao-seedance-2-0-260128"
MODEL_SEEDANCE_2_FAST = "doubao-seedance-2-0-fast-260128"
MODEL_ALLOWED_RESOLUTIONS = {
    MODEL_SEEDANCE_2: {"720p", "1080p"},
    MODEL_SEEDANCE_2_FAST: {"720p"},
}
model = MODEL_SEEDANCE_2
seedance_web_bp = Blueprint("seedance_web", __name__, template_folder="templates")
PROJECT_ROOT = Path(__file__).resolve().parent
SEEDANCE_STORAGE_ROOT = Path(r"D:\Seedance")
SEEDANCE_GENERATED_DIR = SEEDANCE_STORAGE_ROOT / "Seedance生成视频"
SEEDANCE_REFERENCE_DIR = SEEDANCE_STORAGE_ROOT / "Seedance参考视频图片"
JOBS = {}
JOBS_LOCK = threading.Lock()


def pick_value(data, keys):
    for key in keys:
        if key in data and data[key]:
            return data[key]
    return None


def _preview_text(value, limit=1200):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _looks_like_portrait_infringement(text):
    s = str(text or "").lower()
    keywords = [
        "肖像", "人像", "侵权", "版权", "真人", "名人", "人脸", "未经授权", "portrait", "copyright",
        "face", "celebrity", "likeness", "personality rights"
    ]
    return any(k in s for k in keywords)


def _extract_seedance_error_text(obj):
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, list):
        parts = [_extract_seedance_error_text(x) for x in obj]
        return " | ".join([x for x in parts if x])
    if isinstance(obj, dict):
        parts = []
        for key in ["message", "msg", "error", "error_message", "detail", "details", "reason", "reason_text", "code_msg"]:
            if key in obj:
                one = _extract_seedance_error_text(obj.get(key))
                if one:
                    parts.append(one)
        for key in ["data", "result", "output"]:
            if key in obj:
                one = _extract_seedance_error_text(obj.get(key))
                if one:
                    parts.append(one)
        if parts:
            seen = []
            for x in parts:
                if x not in seen:
                    seen.append(x)
            return " | ".join(seen)
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)
    return str(obj)


def _summarize_seedance_failure(payload):
    text = _extract_seedance_error_text(payload)
    if _looks_like_portrait_infringement(text):
        return "疑似命中人像/肖像权限制，请更换为已授权素材，或改用非真人参考图后重试。"
    if text:
        return _preview_text(text, limit=500)
    return "生成失败，请稍后重试。"


def _send_feishu_text_to_open_id(open_id, message_text):
    oid = str(open_id or "").strip()
    text = str(message_text or "").strip()
    if not oid or not text:
        return False, {}
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, {"error": "无法获取 tenant_access_token"}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
        payload = {
            "receive_id": oid,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        data = _safe_json(resp) or {"status_code": resp.status_code, "text": _preview_text(resp.text)}
        return bool(resp.status_code == 200 and isinstance(data, dict) and int(data.get("code") or 0) == 0), data
    except Exception as exc:
        return False, {"error": str(exc)}


def _notify_seedance_submitter(open_id, title, lines):
    oid = str(open_id or "").strip()
    if not oid:
        return False, {}
    out_lines = [str(title or "").strip()]
    for line in (lines or []):
        text = str(line or "").strip()
        if text:
            out_lines.append(text)
    return _send_feishu_text_to_open_id(oid, "\n".join(out_lines))


def post_with_fallback(base_url_text, headers, payload):
    paths = [
        "/contents/generations/tasks",
        "/content/generations/tasks",
        "/content_generation/tasks",
        "/content-generation/tasks",
    ]
    tried = []
    for path in paths:
        url = f"{base_url_text}{path}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
        except Exception as exc:
            tried.append({"url": url, "error": str(exc)})
            continue
        item = {"url": url, "status_code": response.status_code}
        if response.status_code >= 400:
            data = _safe_json(response)
            if data is not None:
                item["response_json"] = data
            else:
                item["response_text"] = _preview_text(response.text)
        tried.append(item)
        if response.status_code != 404:
            return response, path, tried
    return None, None, tried


def get_with_fallback(base_url_text, task_id, headers):
    paths = [
        f"/contents/generations/tasks/{task_id}",
        f"/content/generations/tasks/{task_id}",
        f"/content_generation/tasks/{task_id}",
        f"/content-generation/tasks/{task_id}",
    ]
    tried = []
    for path in paths:
        url = f"{base_url_text}{path}"
        try:
            response = requests.get(url, headers=headers, timeout=60)
        except Exception as exc:
            tried.append({"url": url, "error": str(exc)})
            continue
        tried.append({"url": url, "status_code": response.status_code})
        if response.status_code != 404:
            return response, path, tried
    return None, None, tried


def extract_task_id(data):
    task_id = pick_value(data, ["id", "task_id"])
    if task_id:
        return task_id
    for key in ["data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["id", "task_id"])
            if nested:
                return nested
    return None


def extract_status(data):
    direct = pick_value(data, ["status", "state", "task_status"])
    if direct:
        return str(direct).lower()
    for key in ["data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["status", "state", "task_status"])
            if nested:
                return str(nested).lower()
    return "unknown"


def extract_video_url(data):
    direct = pick_value(data, ["video_url"])
    if direct:
        return direct
    for key in ["content", "data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["video_url"])
            if nested:
                return nested
    return None


def extract_last_frame_url(data):
    direct = pick_value(data, ["last_frame_url", "cover_url", "poster_url"])
    if direct:
        return direct
    for key in ["content", "data", "result", "output"]:
        value = data.get(key)
        if isinstance(value, dict):
            nested = pick_value(value, ["last_frame_url", "cover_url", "poster_url"])
            if nested:
                return nested
    return None


def _to_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return False


def _merge_advanced_options(payload, advanced_options):
    if not isinstance(advanced_options, dict):
        return payload
    merged = copy.deepcopy(payload)
    blocked = {"model", "content"}
    for key, value in advanced_options.items():
        k = str(key or "").strip()
        if not k or k in blocked:
            continue
        merged[k] = value
    return merged


def build_media_url(media_path, default_mime, label, allow_local_file=True):
    if str(media_path).startswith(("http://", "https://")):
        return str(media_path)
    if not allow_local_file:
        raise ValueError(f"{label}仅支持 http/https 链接，请先上传到可访问 URL: {media_path}")
    path = Path(media_path)
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"{label}路径是目录，请传具体文件路径: {media_path}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label}不存在: {media_path}")
    mime_type = mimetypes.guess_type(str(path))[0] or default_mime
    media_base64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{media_base64}"


def download_video(video_url, output_dir, task_id):
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    parsed = urlsplit(video_url)
    filename = Path(parsed.path).name or f"{task_id}.mp4"
    if not filename.lower().endswith(".mp4"):
        filename = f"{task_id}.mp4"
    save_path = output_dir_path / filename
    response = requests.get(video_url, stream=True, timeout=120)
    response.raise_for_status()
    with save_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return save_path


def download_last_frame(image_url, output_dir, task_id):
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    parsed = urlsplit(image_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    save_path = output_dir_path / f"{task_id}_last_frame{suffix}"
    response = requests.get(image_url, stream=True, timeout=120)
    response.raise_for_status()
    with save_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)
    return save_path


def extract_first_frame(video_path, output_dir, task_id):
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    save_path = output_dir_path / f"{task_id}_first_frame.jpg"
    try:
        import cv2  # optional dependency
    except Exception as exc:
        raise RuntimeError(f"提取首帧失败：缺少 cv2 依赖 ({exc})")
    cap = cv2.VideoCapture(str(video_path))
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("提取首帧失败：视频无法读取")
    if not cv2.imwrite(str(save_path), frame):
        raise RuntimeError("提取首帧失败：保存图片失败")
    return save_path


def _normalize_image_refs(image_refs):
    normalized = []
    for item in image_refs:
        value = str(item).strip()
        if not value:
            continue
        if value.startswith(("data:", "http://", "https://", "asset://")):
            normalized.append(value)
        else:
            normalized.append(build_media_url(value, "image/png", "图片"))
    return normalized


def _normalize_video_refs(video_refs):
    normalized = []
    for item in video_refs:
        value = str(item).strip()
        if not value:
            continue
        if value.startswith(("http://", "https://", "asset://")):
            normalized.append(value)
        else:
            raise ValueError(f"视频参考需要可公开访问 URL 或 asset:// 素材: {value}")
    return normalized


def _normalize_audio_refs(audio_refs):
    normalized = []
    for item in audio_refs:
        value = str(item).strip()
        if not value:
            continue
        if value.startswith(("http://", "https://", "asset://")):
            normalized.append(value)
        else:
            raise ValueError(f"音频参考需要可公开访问 URL 或 asset:// 素材: {value}")
    return normalized


def _build_content(prompt, image_refs, video_refs, audio_refs):
    content = []
    if prompt:
        content.append({"type": "text", "text": prompt})
    for image_url in image_refs:
        content.append(
            {
                "role": "reference_image",
                "type": "image_url",
                "image_url": {"url": image_url},
            }
        )
    for video_url in video_refs:
        content.append(
            {
                "role": "reference_video",
                "type": "video_url",
                "video_url": {"url": video_url},
            }
        )
    for audio_url in audio_refs:
        content.append(
            {
                "role": "reference_audio",
                "type": "audio_url",
                "audio_url": {"url": audio_url},
            }
        )
    return content


def _pick_refs_by_mentions(prompt, raw_refs, token_prefix, label_text):
    token = str(token_prefix or "").strip()
    mentions = [int(x) for x in re.findall(rf"@{re.escape(token)}(\d+)", prompt or "", flags=re.IGNORECASE)]
    cleaned_prompt = re.sub(rf"@{re.escape(token)}\d+", "", prompt or "", flags=re.IGNORECASE).strip()
    if not mentions:
        return cleaned_prompt, raw_refs
    selected = []
    for idx in mentions:
        pos = idx - 1
        if pos < 0 or pos >= len(raw_refs):
            raise ValueError(f"提示词中的 @{token}{idx} 超出{label_text}范围，当前仅有 {len(raw_refs)} 个{label_text}")
        selected.append(raw_refs[pos])
    return cleaned_prompt, selected


def _extract_mention_indexes(prompt, token_prefix):
    token = str(token_prefix or "").strip()
    return [int(x) for x in re.findall(rf"@{re.escape(token)}(\d+)", prompt or "", flags=re.IGNORECASE)]


def _ref_display_name(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("data:"):
        return "[本地上传]"
    if text.startswith("asset://"):
        return text
    normalized = text.replace("\\", "/")
    name = normalized.split("/")[-1] or normalized
    try:
        return requests.utils.unquote(name)
    except Exception:
        return name


def _build_mention_note(img_mentions, vid_mentions, aud_mentions, image_paths, video_paths, audio_paths):
    lines = []
    if img_mentions:
        pairs = [f"@img{idx}={_ref_display_name(path)}" for idx, path in zip(img_mentions, image_paths)]
        lines.append("图片引用: " + "; ".join(pairs))
    if vid_mentions:
        pairs = [f"@vid{idx}={_ref_display_name(path)}" for idx, path in zip(vid_mentions, video_paths)]
        lines.append("视频引用: " + "; ".join(pairs))
    if aud_mentions:
        pairs = [f"@aud{idx}={_ref_display_name(path)}" for idx, path in zip(aud_mentions, audio_paths)]
        lines.append("音频引用: " + "; ".join(pairs))
    return "\n".join(lines)


def _create_task_with_fallback(base_url, headers, payload):
    candidates = []
    candidates.append(copy.deepcopy(payload))
    if "ratio" in payload:
        slim = copy.deepcopy(payload)
        slim.pop("ratio", None)
        candidates.append(slim)
    if "resolution" in payload:
        slim = copy.deepcopy(payload)
        slim.pop("resolution", None)
        candidates.append(slim)
    if "ratio" in payload and "resolution" in payload:
        slim = copy.deepcopy(payload)
        slim.pop("ratio", None)
        slim.pop("resolution", None)
        candidates.append(slim)

    seen = set()
    tried = []
    for candidate in candidates:
        key = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        response, create_path, create_tried = post_with_fallback(base_url, headers, candidate)
        tried.append({"payload": candidate, "create_tried": create_tried})
        if response is None:
            continue
        if response.status_code < 400:
            return response, create_path, tried
    return None, None, tried


def _is_safe_path(path: Path):
    safe_roots = [PROJECT_ROOT, SEEDANCE_STORAGE_ROOT]
    resolved = path.resolve()
    for root in safe_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except Exception:
            continue
    return False


def _seedance_sql_escape(value):
    return str(value or "").replace("%", "%%").replace("'", "''")


def _decode_data_url(data_url):
    if not str(data_url).startswith("data:"):
        raise ValueError("不是 data URL")
    header, b64_data = str(data_url).split(",", 1)
    if ";base64" not in header:
        raise ValueError("仅支持 base64 data URL")
    mime = header[5:].split(";")[0].strip().lower() or "application/octet-stream"
    return mime, base64.b64decode(b64_data)


def _guess_ext_from_mime(mime, fallback_ext):
    ext = mimetypes.guess_extension(mime or "")
    if ext:
        return ext
    return fallback_ext


def _save_reference_media(refs, job_id, media_type):
    SEEDANCE_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    fallback_ext_map = {"image": ".png", "video": ".mp4", "audio": ".mp3"}
    fallback_ext = fallback_ext_map.get(media_type, ".bin")
    for idx, ref in enumerate(refs or [], start=1):
        value = str(ref or "").strip()
        if not value:
            continue
        blob = None
        mime = ""
        if value.startswith("data:"):
            mime, blob = _decode_data_url(value)
        elif value.startswith(("http://", "https://")):
            response = requests.get(value, timeout=60)
            response.raise_for_status()
            blob = response.content
            mime = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        else:
            source_path = Path(value)
            if source_path.exists() and source_path.is_file():
                blob = source_path.read_bytes()
                mime = mimetypes.guess_type(str(source_path))[0] or ""
            else:
                continue
        ext = _guess_ext_from_mime(mime, fallback_ext)
        target_name = f"{job_id}_{media_type}_{idx}{ext}"
        target_path = SEEDANCE_REFERENCE_DIR / target_name
        target_path.write_bytes(blob)
        saved_paths.append(str(target_path.resolve()))
    return saved_paths


def _prepare_reference_urls(refs, job_id, media_type, public_base_url):
    SEEDANCE_REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    prepared_urls = []
    saved_paths = []
    fallback_ext_map = {"image": ".png", "video": ".mp4", "audio": ".mp3"}
    fallback_ext = fallback_ext_map.get(media_type, ".bin")
    for idx, ref in enumerate(refs or [], start=1):
        value = str(ref or "").strip()
        if not value:
            continue
        if value.startswith("asset://"):
            prepared_urls.append(value)
            saved_paths.append(value)
            continue
        blob = None
        mime = ""
        if value.startswith("data:"):
            mime, blob = _decode_data_url(value)
        elif value.startswith(("http://", "https://")):
            response = requests.get(value, timeout=60)
            response.raise_for_status()
            blob = response.content
            mime = str(response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        else:
            source_path = Path(value)
            if not source_path.exists() or not source_path.is_file():
                continue
            blob = source_path.read_bytes()
            mime = mimetypes.guess_type(str(source_path))[0] or ""
        ext = _guess_ext_from_mime(mime, fallback_ext)
        filename = f"{job_id}_{media_type}_{idx}{ext}"
        target_path = (SEEDANCE_REFERENCE_DIR / filename).resolve()
        target_path.write_bytes(blob)
        saved_paths.append(str(target_path))
        prepared_urls.append(f"{public_base_url}/{job_id}/{quote(filename)}")
    return prepared_urls, saved_paths


def _insert_seedance_record(
    generated_video_paths,
    generated_first_frame_paths,
    generated_last_frame_paths,
    reference_video_paths,
    reference_image_paths,
    reference_audio_paths,
    uploader_name,
    duration_seconds,
    quantity,
    prompt_text,
    resolution_text,
):
    shengchengshipinlujin = _seedance_sql_escape(
        "|".join((generated_video_paths or []) + (generated_first_frame_paths or []) + (generated_last_frame_paths or []))
    )
    shipinlujin = _seedance_sql_escape("|".join(reference_video_paths or []))
    tupianlujin = _seedance_sql_escape("|".join(reference_image_paths or []))
    yinpin = _seedance_sql_escape("|".join(reference_audio_paths or []))
    xingming = _seedance_sql_escape(uploader_name)
    tishici = _seedance_sql_escape(prompt_text)
    fenbianlv = _seedance_sql_escape(resolution_text)
    riqi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    shichang_sql = "NULL" if duration_seconds in (None, "") else str(int(duration_seconds))
    shuliang_sql = str(int(quantity or 0))
    sql_insert = f"""
        INSERT INTO Seedance
        (shengchengshipinlujin, shipinlujin, tupianlujin, yinpin, xingming, shichang, shuliang, tishici, fenbianlv, riqi)
        VALUES
        (
            N'{shengchengshipinlujin}',
            N'{shipinlujin}',
            N'{tupianlujin}',
            N'{yinpin}',
            N'{xingming}',
            {shichang_sql},
            {shuliang_sql},
            N'{tishici}',
            N'{fenbianlv}',
            '{riqi}'
        )
    """
    dui_db(sql_insert)


def _split_path_list(value):
    text = str(value or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.split("|") if str(x).strip()]


def _looks_like_image_path(path_text):
    suffix = Path(str(path_text or "")).suffix.lower()
    return suffix in {".jpg", ".jpeg", ".png", ".webp"}


def _set_job(job_id, **kwargs):
    with JOBS_LOCK:
        if job_id not in JOBS:
            return
        JOBS[job_id].update(kwargs)


def _start_job(body, job_id=None):
    job_id = str(job_id or uuid.uuid4().hex)
    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
            "message": "排队中",
            "created_at": time.time(),
            "result": None,
            "error": None,
        }
    threading.Thread(target=_run_generate_job, args=(job_id, body), daemon=True).start()
    return job_id


def _start_postprocess_job(
    job_id,
    result,
    task_items,
    output_dir,
    max_workers,
    auto_download_first_frame,
    auto_download_last_frame,
    saved_video_ref_paths,
    saved_image_ref_paths,
    saved_audio_ref_paths,
    uploader_name,
    submitter_open_id,
    duration,
    count,
    db_prompt_text,
    resolution,
):
    threading.Thread(
        target=_run_postprocess_job,
        args=(
            job_id,
            result,
            task_items,
            output_dir,
            max_workers,
            auto_download_first_frame,
            auto_download_last_frame,
            saved_video_ref_paths,
            saved_image_ref_paths,
            saved_audio_ref_paths,
            uploader_name,
            submitter_open_id,
            duration,
            count,
            db_prompt_text,
            resolution,
        ),
        daemon=True,
    ).start()


def _run_postprocess_job(
    job_id,
    result,
    task_items,
    output_dir,
    max_workers,
    auto_download_first_frame,
    auto_download_last_frame,
    saved_video_ref_paths,
    saved_image_ref_paths,
    saved_audio_ref_paths,
    uploader_name,
    submitter_open_id,
    duration,
    count,
    db_prompt_text,
    resolution,
):
    generated_video_paths = []
    generated_first_frame_paths = []
    generated_last_frame_paths = []
    try:
        success_items = [item for item in task_items if item.get("status") in {"succeeded", "success", "completed"}]
        _set_job(job_id, stage="postprocess", message="视频已返回，后台下载处理中")
        if success_items:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(success_items))) as executor:
                future_map = {}
                for item in success_items:
                    video_url = str(item.get("video_url") or "").strip()
                    if not video_url:
                        item["postprocess_error"] = {"message": "缺少 video_url，无法下载本地视频"}
                        continue
                    future_map[executor.submit(download_video, video_url, output_dir, item["task_id"])] = item
                total_dl = max(1, len(future_map))
                done_dl = 0
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        save_path = Path(future.result()).resolve()
                        item["video_saved"] = str(save_path)
                        item["local_preview_url"] = f"api/local-video?path={quote(str(save_path))}"
                        item["local_download_url"] = f"api/local-video?download=1&path={quote(str(save_path))}"
                        generated_video_paths.append(str(save_path))
                    except Exception as exc:
                        item["postprocess_error"] = {"message": f"下载失败: {exc}"}
                    done_dl += 1
                    _set_job(job_id, stage="postprocess", message=f"视频已返回，后台下载中 {done_dl}/{total_dl}", result=result)
            for item in success_items:
                local_video_path = str(item.get("video_saved") or "").strip()
                if auto_download_first_frame and local_video_path:
                    try:
                        first_frame_path = Path(extract_first_frame(local_video_path, output_dir, item["task_id"])).resolve()
                        item["first_frame_saved"] = str(first_frame_path)
                        item["first_frame_local_preview_url"] = f"api/local-media?path={quote(str(first_frame_path))}"
                        generated_first_frame_paths.append(str(first_frame_path))
                    except Exception as exc:
                        item["first_frame_error"] = str(exc)
                last_frame_url = str(item.get("last_frame_url") or "").strip()
                if auto_download_last_frame and last_frame_url:
                    try:
                        last_frame_path = Path(download_last_frame(last_frame_url, output_dir, item["task_id"])).resolve()
                        item["last_frame_saved"] = str(last_frame_path)
                        item["last_frame_local_preview_url"] = f"api/local-media?path={quote(str(last_frame_path))}"
                        generated_last_frame_paths.append(str(last_frame_path))
                    except Exception as exc:
                        item["last_frame_error"] = str(exc)

        _set_job(job_id, stage="postprocess", message="视频已返回，后台写入记录中", result=result)
        _insert_seedance_record(
            generated_video_paths=generated_video_paths,
            generated_first_frame_paths=generated_first_frame_paths,
            generated_last_frame_paths=generated_last_frame_paths,
            reference_video_paths=saved_video_ref_paths,
            reference_image_paths=saved_image_ref_paths,
            reference_audio_paths=saved_audio_ref_paths,
            uploader_name=uploader_name,
            duration_seconds=duration,
            quantity=count,
            prompt_text=db_prompt_text,
            resolution_text=resolution,
        )
        result["db_write"] = {
            "table": "Seedance",
            "generated_video_paths": generated_video_paths,
            "generated_first_frame_paths": generated_first_frame_paths,
            "generated_last_frame_paths": generated_last_frame_paths,
            "reference_video_paths": saved_video_ref_paths,
            "reference_image_paths": saved_image_ref_paths,
            "reference_audio_paths": saved_audio_ref_paths,
            "submitter_name": uploader_name,
        }
        result["postprocess"] = {
            "status": "done",
            "message": "后台后处理完成",
            "finished_at": time.time(),
        }
        _set_job(job_id, stage="done", message="视频已返回，后台后处理完成", result=result)
    except Exception as exc:
        result["postprocess"] = {
            "status": "failed",
            "message": f"后台后处理失败: {exc}",
            "finished_at": time.time(),
        }
        _set_job(job_id, stage="done", message=f"视频已返回，但后台后处理失败: {exc}", result=result)
        _notify_seedance_submitter(
            submitter_open_id if 'submitter_open_id' in locals() else "",
            "Seedance 后台处理失败",
            [f"原因：{_preview_text(exc, 180)}", "视频通常已生成，可先在页面预览；本地下载或入库未完全完成。"],
        )


def _run_generate_job(job_id, body):
    try:
        _set_job(job_id, status="running", progress=2, stage="prepare", message="准备参数")
        local_api_key = str(api_key or "").strip()
        local_base_url = str(base_url or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")
        local_model = str(body.get("model") or model or MODEL_SEEDANCE_2).strip()
        if local_model not in MODEL_ALLOWED_RESOLUTIONS:
            raise ValueError("model 仅支持 Seedance 2.0 或 Seedance 2.0 Fast")
        uploader_name = str(body.get("_submitter_name") or "未知用户").strip()
        submitter_open_id = str(body.get("_submitter_open_id") or "").strip()
        if not local_api_key:
            raise ValueError("seedance_web.py 缺少 api_key")
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt 不能为空")
        original_prompt = prompt
        count = int(body.get("count") or 1)
        duration = body.get("duration")
        duration = int(duration) if duration not in (None, "") else None
        ratio = str(body.get("ratio") or "").strip()
        resolution = str(body.get("resolution") or "").strip()
        if resolution and resolution not in MODEL_ALLOWED_RESOLUTIONS.get(local_model, set()):
            if local_model == MODEL_SEEDANCE_2_FAST:
                raise ValueError("Seedance 2.0 Fast 仅支持 720p")
            raise ValueError("Seedance 2.0 仅支持 720p 或 1080p")
        generate_audio = _to_bool(body.get("generate_audio"))
        return_last_frame = True
        auto_download_frames = _to_bool(body.get("auto_download_frames")) if "auto_download_frames" in body else None
        if auto_download_frames is None:
            auto_download_first_frame = _to_bool(body.get("auto_download_first_frame")) if "auto_download_first_frame" in body else True
            auto_download_last_frame = _to_bool(body.get("auto_download_last_frame")) if "auto_download_last_frame" in body else True
        else:
            auto_download_first_frame = auto_download_frames
            auto_download_last_frame = auto_download_frames
        service_tier = str(body.get("service_tier") or "").strip()
        enable_search = _to_bool(body.get("enable_search"))
        sample_mode = _to_bool(body.get("sample_mode"))
        watermark = _to_bool(body.get("watermark")) if "watermark" in body else True
        advanced_options = body.get("advanced_options")
        if isinstance(advanced_options, str):
            advanced_options = advanced_options.strip()
            advanced_options = json.loads(advanced_options) if advanced_options else {}
        if advanced_options is None:
            advanced_options = {}
        if not isinstance(advanced_options, dict):
            raise ValueError("advanced_options 必须是 JSON 对象")
        output_dir = str(SEEDANCE_GENERATED_DIR)
        timeout_seconds = int(body.get("timeout_seconds") or 900)
        poll_interval_seconds = int(body.get("poll_interval_seconds") or 5)
        max_workers = min(max(1, int(body.get("max_workers") or 4)), max(1, count))

        raw_image_refs = [str(x).strip() for x in (body.get("image_refs") or []) if str(x).strip()]
        raw_video_refs = [str(x).strip() for x in (body.get("video_refs") or []) if str(x).strip()]
        raw_audio_refs = [str(x).strip() for x in (body.get("audio_refs") or []) if str(x).strip()]
        img_mentions = _extract_mention_indexes(original_prompt, "img")
        vid_mentions = _extract_mention_indexes(original_prompt, "vid")
        aud_mentions = _extract_mention_indexes(original_prompt, "aud")
        prompt, picked_image_refs = _pick_refs_by_mentions(prompt, raw_image_refs, "img", "图片")
        prompt, picked_video_refs = _pick_refs_by_mentions(prompt, raw_video_refs, "vid", "视频")
        prompt, picked_audio_refs = _pick_refs_by_mentions(prompt, raw_audio_refs, "aud", "音频")
        image_refs = _normalize_image_refs(picked_image_refs)
        video_refs = _normalize_video_refs(picked_video_refs)
        audio_refs = _normalize_audio_refs(picked_audio_refs)
        saved_image_ref_paths = [str(x).strip() for x in (body.get("_reference_image_saved_paths") or []) if str(x).strip()]
        saved_video_ref_paths = [str(x).strip() for x in (body.get("_reference_video_saved_paths") or []) if str(x).strip()]
        saved_audio_ref_paths = [str(x).strip() for x in (body.get("_reference_audio_saved_paths") or []) if str(x).strip()]
        if not saved_image_ref_paths and image_refs:
            saved_image_ref_paths = _save_reference_media(image_refs, job_id, "image")
        if not saved_video_ref_paths and video_refs:
            saved_video_ref_paths = _save_reference_media(video_refs, job_id, "video")
        if not saved_audio_ref_paths and audio_refs:
            saved_audio_ref_paths = _save_reference_media(audio_refs, job_id, "audio")
        mention_note = _build_mention_note(
            img_mentions,
            vid_mentions,
            aud_mentions,
            saved_image_ref_paths,
            saved_video_ref_paths,
            saved_audio_ref_paths,
        )
        db_prompt_text = prompt if not mention_note else f"{prompt}\n\n[引用素材]\n{mention_note}"

        content = _build_content(prompt, image_refs, video_refs, audio_refs)
        text_only_content = _build_content(prompt, [], [], [])
        headers = {"Authorization": f"Bearer {local_api_key}", "Content-Type": "application/json"}

        _set_job(job_id, progress=8, stage="submit", message="提交任务中")

        def submit_one(_):
            payload = {"model": local_model, "content": content}
            if duration is not None:
                payload["duration"] = duration
            if ratio and ratio != "智能":
                payload["ratio"] = ratio
            if resolution:
                payload["resolution"] = resolution
            if generate_audio:
                payload["generate_audio"] = True
            if return_last_frame:
                payload["return_last_frame"] = True
            if service_tier:
                payload["service_tier"] = service_tier
            if enable_search:
                payload["enable_search"] = True
            if sample_mode:
                payload["sample_mode"] = True
            payload["watermark"] = bool(watermark)
            if enable_search:
                payload["tools"] = [{"type": "web_search"}]
            payload = _merge_advanced_options(payload, advanced_options)
            create_response, create_path, all_tried = _create_task_with_fallback(local_base_url, headers, payload)
            if create_response is None:
                return {"ok": False, "error": "创建任务失败", "tried": all_tried}
            create_data = create_response.json()
            task_id = extract_task_id(create_data)
            if not task_id:
                return {"ok": False, "error": "创建成功但未解析到 task_id", "response": create_data}
            return {
                "ok": True,
                "task_id": task_id,
                "status": "submitted",
                "create_path": create_path,
                "last_data": create_data,
                "submit_time": time.time(),
            }

        submissions = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(submit_one, i) for i in range(count)]
            for future in as_completed(futures):
                submissions.append(future.result())
                done_count = len(submissions)
                submit_progress = 8 + int((done_count / max(1, count)) * 17)
                _set_job(job_id, progress=submit_progress, message=f"已提交 {done_count}/{count}")

        failed_submissions = [s for s in submissions if not s.get("ok")]
        if failed_submissions:
            failure_payload = {"error": "部分任务提交失败", "failed_submissions": failed_submissions}
            raise RuntimeError(json.dumps(failure_payload, ensure_ascii=False))

        task_items = submissions
        running_statuses = {"submitted", "queued", "running", "processing", "pending"}
        terminal_statuses = {"succeeded", "success", "completed", "failed", "cancelled", "canceled", "expired"}
        deadline = time.time() + timeout_seconds
        _set_job(job_id, progress=28, stage="poll", message="生成中")

        while time.time() < deadline:
            unfinished = [item for item in task_items if item.get("status") in running_statuses]
            if not unfinished:
                break
            time.sleep(poll_interval_seconds)
            with ThreadPoolExecutor(max_workers=min(max_workers, len(unfinished))) as executor:
                future_map = {
                    executor.submit(get_with_fallback, local_base_url, item["task_id"], headers): item for item in unfinished
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    get_response, _, get_tried = future.result()
                    if get_response is None:
                        item["status"] = "failed"
                        item["error"] = {"message": "查询失败", "tried": get_tried}
                        continue
                    if get_response.status_code >= 400:
                        item["status"] = "failed"
                        item["error"] = {"message": f"查询失败 status={get_response.status_code}", "text": get_response.text[:1200]}
                        continue
                    item["last_data"] = get_response.json()
                    status = extract_status(item["last_data"])
                    item["status"] = status if status in terminal_statuses or status in running_statuses else "running"
                    if item["status"] in {"succeeded", "success", "completed"}:
                        video_url = extract_video_url(item["last_data"] or {})
                        if video_url:
                            item["video_url"] = video_url
                        last_frame_url = extract_last_frame_url(item["last_data"] or {})
                        if last_frame_url:
                            item["last_frame_url"] = last_frame_url

            done_cnt = len([i for i in task_items if i.get("status") in terminal_statuses])
            poll_progress = 28 + int((done_cnt / max(1, count)) * 57)
            _set_job(
                job_id,
                progress=min(85, poll_progress),
                message=f"生成中 {done_cnt}/{count}",
                result={"tasks": task_items},
            )

        for item in task_items:
            if item.get("status") in running_statuses:
                item["status"] = "timeout"

        success_items = []
        failed_items = []
        for item in task_items:
            if item.get("status") in {"succeeded", "success", "completed"}:
                video_url = str(item.get("video_url") or extract_video_url(item.get("last_data", {})) or "").strip()
                if not video_url:
                    item["status"] = "failed"
                    item["error"] = {"message": "任务成功但无 video_url"}
                    failed_items.append(item)
                    continue
                item["video_url"] = video_url
                last_frame_url = str(item.get("last_frame_url") or extract_last_frame_url(item.get("last_data") or {}) or "").strip()
                if last_frame_url:
                    item["last_frame_url"] = last_frame_url
                success_items.append(item)
            else:
                failed_items.append(item)

        result = {
            "ok": len(failed_items) == 0,
            "model": local_model,
            "options": {
                "generate_audio": generate_audio,
                "return_last_frame": return_last_frame,
                "auto_download_frames": auto_download_first_frame and auto_download_last_frame,
                "auto_download_first_frame": auto_download_first_frame,
                "auto_download_last_frame": auto_download_last_frame,
                "service_tier": service_tier,
                "enable_search": enable_search,
                "sample_mode": sample_mode,
                "watermark": watermark,
                "advanced_options": advanced_options,
            },
            "postprocess": {
                "status": "pending" if success_items else "skipped",
                "message": "视频已返回，后台处理中" if success_items else "无可处理成功视频",
                "started_at": time.time(),
            },
            "summary": {
                "count": count,
                "success_count": len(success_items),
                "failed_count": len(failed_items),
            },
            "db_write": {
                "table": "Seedance",
                "generated_video_paths": [],
                "generated_first_frame_paths": [],
                "generated_last_frame_paths": [],
                "reference_video_paths": saved_video_ref_paths,
                "reference_image_paths": saved_image_ref_paths,
                "reference_audio_paths": saved_audio_ref_paths,
                "submitter_name": uploader_name,
            },
            "tasks": task_items,
        }
        _set_job(
            job_id,
            status="succeeded" if result["ok"] else "failed",
            progress=100,
            stage="done",
            message="视频已返回，后台处理中" if success_items else "执行失败",
            result=result,
            error=None if result["ok"] else "部分任务失败",
            finished_at=time.time(),
        )
        if success_items:
            success_label = "Seedance 视频生成成功" if not failed_items else "Seedance 视频生成部分成功"
            notify_lines = [
                f"提示词：{_preview_text(prompt, 120)}",
                f"成功：{len(success_items)} 个，失败：{len(failed_items)} 个",
                "视频已返回页面，可先预览；下载、抽帧和写库正在后台继续处理。",
            ]
            _notify_seedance_submitter(submitter_open_id, success_label, notify_lines)
        else:
            failure_reason = _summarize_seedance_failure({"failed_items": failed_items})
            _notify_seedance_submitter(
                submitter_open_id,
                "Seedance 视频生成失败",
                [f"提示词：{_preview_text(prompt, 120)}", f"原因：{failure_reason}"],
            )
        if success_items:
            _start_postprocess_job(
                job_id=job_id,
                result=result,
                task_items=task_items,
                output_dir=output_dir,
                max_workers=max_workers,
                auto_download_first_frame=auto_download_first_frame,
                auto_download_last_frame=auto_download_last_frame,
                saved_video_ref_paths=saved_video_ref_paths,
                saved_image_ref_paths=saved_image_ref_paths,
                saved_audio_ref_paths=saved_audio_ref_paths,
                uploader_name=uploader_name,
                submitter_open_id=submitter_open_id,
                duration=duration,
                count=count,
                db_prompt_text=db_prompt_text,
                resolution=resolution,
            )
    except Exception as exc:
        error_text = str(exc)
        friendly_error = _summarize_seedance_failure(error_text)
        _set_job(job_id, status="failed", stage="failed", message=friendly_error or "执行失败", error=error_text, progress=100, finished_at=time.time())
        submitter_open_id = str((body or {}).get("_submitter_open_id") or "").strip()
        prompt_text = str((body or {}).get("prompt") or "").strip()
        _notify_seedance_submitter(
            submitter_open_id,
            "Seedance 视频生成失败",
            [f"提示词：{_preview_text(prompt_text, 120)}", f"原因：{friendly_error or '执行失败'}"],
        )


@seedance_web_bp.get("/")
def seedance_web_index():
    return render_template("seedance_web.html")


@seedance_web_bp.post("/api/preview-images")
def seedance_web_api_preview_images():
    body = request.get_json(force=True, silent=True) or {}
    refs = body.get("image_refs") or []
    items = []
    for idx, item in enumerate(refs, start=1):
        value = str(item).strip()
        if not value:
            continue
        try:
            if value.startswith(("data:", "http://", "https://")):
                src = value
            else:
                src = build_media_url(value, "image/png", "图片")
            items.append({"index": idx, "ref": value, "src": src})
        except Exception as exc:
            items.append({"index": idx, "ref": value, "error": str(exc)})
    return jsonify({"ok": True, "items": items})


@seedance_web_bp.post("/api/generate")
def seedance_web_api_generate():
    try:
        body = request.get_json(force=True, silent=False) or {}
        body["_submitter_name"] = str(session.get("feishu_user_name") or "未知用户").strip()
        body["_submitter_open_id"] = str(session.get("feishu_open_id") or session.get("feishu_user_id") or "").strip()
        job_id = uuid.uuid4().hex
        public_media_base = request.host_url.rstrip("/") + "/seedance-web/api/media"
        image_refs = [x for x in (body.get("image_refs") or []) if str(x).strip()]
        video_refs = [x for x in (body.get("video_refs") or []) if str(x).strip()]
        audio_refs = [x for x in (body.get("audio_refs") or []) if str(x).strip()]
        prepared_image_urls = _normalize_image_refs(image_refs)
        image_saved_paths = _save_reference_media(prepared_image_urls, job_id, "image") if prepared_image_urls else []
        prepared_video_urls, video_saved_paths = _prepare_reference_urls(video_refs, job_id, "video", public_media_base)
        prepared_audio_urls, audio_saved_paths = _prepare_reference_urls(audio_refs, job_id, "audio", public_media_base)
        if image_refs and len(prepared_image_urls) != len(image_refs):
            raise ValueError("参考图片上传失败，请重新上传后再试")
        if video_refs and len(prepared_video_urls) != len(video_refs):
            raise ValueError("参考视频上传失败，请重新上传后再试")
        if audio_refs and len(prepared_audio_urls) != len(audio_refs):
            raise ValueError("参考音频上传失败，请重新上传后再试")
        body["image_refs"] = prepared_image_urls
        body["video_refs"] = prepared_video_urls
        body["audio_refs"] = prepared_audio_urls
        body["_reference_image_saved_paths"] = image_saved_paths
        body["_reference_video_saved_paths"] = video_saved_paths
        body["_reference_audio_saved_paths"] = audio_saved_paths
        _start_job(body, job_id=job_id)
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@seedance_web_bp.get("/api/generate/<job_id>")
def seedance_web_api_generate_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job 不存在"}), 404
    return jsonify(job)


@seedance_web_bp.get("/api/history")
def seedance_web_api_history():
    user_name = str(session.get("feishu_user_name") or "").strip()
    if not user_name:
        return jsonify({"ok": False, "error": "未检测到飞书登录用户"}), 401
    limit = request.args.get("limit", "20").strip()
    try:
        limit_num = max(1, min(100, int(limit)))
    except Exception:
        limit_num = 20
    user_sql = _seedance_sql_escape(user_name)
    sql_query = f"""
        SELECT TOP {limit_num}
            riqi, tishici, shengchengshipinlujin, shipinlujin, tupianlujin, yinpin, fenbianlv, shichang, shuliang
        FROM Seedance
        WHERE xingming = N'{user_sql}'
        ORDER BY riqi DESC
    """
    rows = sf_db(sql_query) or []
    out = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 9:
            continue
        generated_paths = _split_path_list(row[2])
        video_paths = [p for p in generated_paths if not _looks_like_image_path(p)]
        first_frame_paths = [p for p in generated_paths if _looks_like_image_path(p) and "_first_frame" in Path(str(p)).name]
        last_frame_paths = [p for p in generated_paths if _looks_like_image_path(p) and "_last_frame" in Path(str(p)).name]
        generated_urls = [f"api/local-video?path={quote(str(p))}" for p in video_paths]
        generated_download_urls = [f"api/local-video?download=1&path={quote(str(p))}" for p in video_paths]
        first_frame_preview_urls = [f"api/local-media?path={quote(str(p))}" for p in first_frame_paths]
        first_frame_download_urls = [f"api/local-media?download=1&path={quote(str(p))}" for p in first_frame_paths]
        last_frame_preview_urls = [f"api/local-media?path={quote(str(p))}" for p in last_frame_paths]
        last_frame_download_urls = [f"api/local-media?download=1&path={quote(str(p))}" for p in last_frame_paths]
        out.append(
            {
                "riqi": str(row[0] or ""),
                "tishici": str(row[1] or ""),
                "shengchengshipinlujin": generated_paths,
                "shipinlujin": _split_path_list(row[3]),
                "tupianlujin": _split_path_list(row[4]),
                "yinpin": _split_path_list(row[5]),
                "fenbianlv": str(row[6] or ""),
                "shichang": str(row[7] or ""),
                "shuliang": str(row[8] or ""),
                "video_preview_urls": generated_urls,
                "video_download_urls": generated_download_urls,
                "first_frame_preview_urls": first_frame_preview_urls,
                "first_frame_download_urls": first_frame_download_urls,
                "last_frame_preview_urls": last_frame_preview_urls,
                "last_frame_download_urls": last_frame_download_urls,
            }
        )
    return jsonify({"ok": True, "items": out, "user_name": user_name})


@seedance_web_bp.get("/api/media/<job_id>/<filename>")
def seedance_web_api_media(job_id, filename):
    safe_name = Path(filename).name
    if not safe_name.startswith(f"{job_id}_"):
        return abort(403)
    file_path = (SEEDANCE_REFERENCE_DIR / safe_name).resolve()
    if not file_path.exists() or not file_path.is_file():
        return abort(404)
    if not _is_safe_path(file_path):
        return abort(403)
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return send_file(file_path, mimetype=mime, as_attachment=False)


@seedance_web_bp.get("/api/local-video")
def seedance_web_api_local_video():
    path = request.args.get("path", "").strip()
    if not path:
        return abort(400)
    file_path = Path(path).resolve()
    if not file_path.exists() or not file_path.is_file():
        return abort(404)
    if not _is_safe_path(file_path):
        return abort(403)
    as_attachment = request.args.get("download", "0") == "1"
    return send_file(file_path, mimetype="video/mp4", as_attachment=as_attachment, download_name=file_path.name)


@seedance_web_bp.get("/api/local-media")
def seedance_web_api_local_media():
    path = request.args.get("path", "").strip()
    if not path:
        return abort(400)
    file_path = Path(path).resolve()
    if not file_path.exists() or not file_path.is_file():
        return abort(404)
    if not _is_safe_path(file_path):
        return abort(403)
    as_attachment = request.args.get("download", "0") == "1"
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return send_file(file_path, mimetype=mime, as_attachment=as_attachment, download_name=file_path.name)


def create_standalone_app():
    standalone_app = Flask(__name__, template_folder="templates")
    standalone_app.register_blueprint(seedance_web_bp)
    return standalone_app


if __name__ == "__main__":
    create_standalone_app().run(host="127.0.0.1", port=8787, debug=False)
