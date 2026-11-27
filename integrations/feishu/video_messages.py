"""Feishu video uploads and bot chat lookup."""

import io
import os
import tempfile

import requests
from werkzeug.utils import secure_filename


def _upload_feishu_message_video(get_access_token, upload):
    token = get_access_token()
    if not token:
        return False, '获取飞书访问令牌失败', {}
    filename = secure_filename(str(getattr(upload, 'filename', '') or '')) or 'test-video.mp4'
    try:
        duration_ms = _get_video_duration_ms(upload)
        upload.stream.seek(0)
        upload_data = {'file_type': 'mp4', 'file_name': filename}
        if duration_ms > 0:
            upload_data['duration'] = str(duration_ms)
        response = requests.post(
            'https://open.feishu.cn/open-apis/im/v1/files',
            headers={'Authorization': f'Bearer {token}'},
            data=upload_data,
            files={'file': (filename, upload.stream, upload.mimetype or 'video/mp4')},
            timeout=120,
        )
        payload = response.json() if response.content else {}
    except Exception as exc:
        return False, f'上传视频失败：{exc}', {}
    if response.status_code >= 400 or payload.get('code') != 0:
        raw_message = str(payload.get('msg') or f'飞书上传接口返回 HTTP {response.status_code}')
        return False, raw_message, payload
    file_key = str((payload.get('data') or {}).get('file_key') or '').strip()
    if not file_key:
        return False, '飞书上传成功但未返回 file_key', payload
    return True, file_key, payload


def _get_video_duration_ms(upload):
    """Read MP4 duration in milliseconds for Feishu's video metadata."""
    temp_path = ''
    try:
        import cv2
        upload.stream.seek(0)
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.write(upload.stream.read())
            temp_path = tmp.name
        capture = cv2.VideoCapture(temp_path)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        capture.release()
        if fps <= 0 or frames <= 0:
            return 0
        return max(1, round(frames / fps * 1000))
    except Exception:
        return 0
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _upload_feishu_video_cover(get_access_token, upload):
    """Extract and upload the first frame so the message has visible content before playback."""
    token = get_access_token()
    if not token:
        return ""
    temp_path = ""
    try:
        import cv2
        upload.stream.seek(0)
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.write(upload.stream.read())
            temp_path = tmp.name
        capture = cv2.VideoCapture(temp_path)
        ok, frame = capture.read()
        capture.release()
        if not ok or frame is None:
            return ""
        ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok:
            return ""
        response = requests.post(
            'https://open.feishu.cn/open-apis/im/v1/images',
            headers={'Authorization': f'Bearer {token}'},
            files={'image': ('video-cover.jpg', io.BytesIO(encoded.tobytes()), 'image/jpeg')},
            data={'image_type': 'message'},
            timeout=30,
        )
        payload = response.json() if response.content else {}
        if response.status_code >= 400 or payload.get('code') != 0:
            return ""
        return str((payload.get('data') or {}).get('image_key') or '').strip()
    except Exception:
        return ""
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _list_feishu_bot_chats(get_access_token):
    """List chats visible to the app bot."""
    token = get_access_token()
    if not token:
        return [], '获取飞书访问令牌失败'

    chats = []
    page_token = ''
    try:
        while True:
            params = {'page_size': 100}
            if page_token:
                params['page_token'] = page_token
            response = requests.get(
                'https://open.feishu.cn/open-apis/im/v1/chats',
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                timeout=15,
            )
            payload = response.json() if response.content else {}
            if response.status_code >= 400 or payload.get('code') != 0:
                return [], str(payload.get('msg') or f'查询群聊失败（HTTP {response.status_code}）')
            data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
            for item in data.get('items') or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or '').strip()
                chat_id = str(item.get('chat_id') or '').strip()
                if name and chat_id:
                    chats.append({'name': name, 'chat_id': chat_id})
            page_token = str(data.get('page_token') or '').strip()
            if not page_token:
                break
    except Exception as exc:
        return [], f'查询群聊失败：{exc}'
    chats.sort(key=lambda item: item['name'].casefold())
    return chats, ''


def _resolve_feishu_chat_name(chat_name, list_chats):
    """Resolve a visible Feishu group name to a chat_id using the bot token."""
    target = str(chat_name or '').strip()
    if not target:
        return '', '请选择群聊'
    if target.startswith('oc_'):
        return target, ''
    chats, error = list_chats()
    if error:
        return '', error
    matches = [(item['name'], item['chat_id']) for item in chats]

    exact = [(name, cid) for name, cid in matches if name.casefold() == target.casefold()]
    if len(exact) == 1:
        return exact[0][1], ''
    if len(exact) > 1:
        return '', f'存在多个同名群聊“{target}”，请先修改群名以便区分'
    suggestions = [name for name, _ in matches if target.casefold() in name.casefold()][:5]
    suffix = f'，相近群聊：{"、".join(suggestions)}' if suggestions else ''
    return '', f'未找到群聊“{target}”。请确认机器人已加入该群聊{suffix}'
