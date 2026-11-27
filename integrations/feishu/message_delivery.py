"""Send, update and recall Feishu messages and card attachments."""

from __future__ import annotations


def _feishu_get_message_read_users(
    message_id,
    user_id_type,
    page_size,
    *,
    _feishu_http,
    permission_manager,
):
    mid = str(message_id or "").strip()
    uid_type = str(user_id_type or "").strip() or "open_id"
    if not mid:
        return [], "缺少消息ID"
    try:
        token = permission_manager.get_access_token()
        if not token:
            return [], "获取飞书访问令牌失败"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        out = []
        seen = set()
        page_token = ""
        loops = 0
        while True:
            loops += 1
            params = {
                "user_id_type": uid_type,
                "page_size": max(1, min(100, int(page_size or 100))),
            }
            if page_token:
                params["page_token"] = page_token
            resp = _feishu_http.get(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}/read_users",
                headers=headers,
                params=params,
                timeout=10
            )
            data = resp.json() if resp is not None else {}
            resp_code = int(data.get("code")) if isinstance(data, dict) and str(data.get("code")).strip() != "" else -1
            if not resp or resp.status_code != 200 or not isinstance(data, dict) or resp_code != 0:
                return out, str((data or {}).get("msg") or (data or {}).get("message") or data or f"HTTP {getattr(resp, 'status_code', 'unknown')}")
            data_obj = data.get("data") or {}
            for item in (data_obj.get("items") or []):
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("user_id") or "").strip()
                if uid and uid not in seen:
                    seen.add(uid)
                    out.append(uid)
            if not data_obj.get("has_more"):
                break
            page_token = str(data_obj.get("page_token") or "").strip()
            if not page_token or loops >= 20:
                break
        return out, ""
    except Exception as e:
        return [], str(e)


def _feishu_recall_message(
    message_id,
    *,
    _feishu_http,
    permission_manager,
):
    mid = str(message_id or "").strip()
    if not mid:
        return False, "缺少消息ID", {}
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, "获取飞书访问令牌失败", {}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        resp = _feishu_http.delete(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}",
            headers=headers,
            timeout=10
        )
        data = resp.json() if resp is not None else {}
        resp_code = int(data.get("code")) if isinstance(data, dict) and str(data.get("code")).strip() != "" else -1
        if resp and resp.status_code == 200 and isinstance(data, dict) and resp_code == 0:
            return True, "", data
        if isinstance(data, dict) and resp_code == 230110:
            return True, "", data
        return False, str((data or {}).get("msg") or (data or {}).get("message") or data or f"HTTP {getattr(resp, 'status_code', 'unknown')}"), data
    except Exception as e:
        return False, str(e), {}


def _feishu_send_message_detail(
    receive_id,
    receive_id_type,
    msg_type,
    content_obj,
    *,
    json,
    permission_manager,
):
    rid = str(receive_id or "").strip()
    rtype = str(receive_id_type or "").strip()
    mtype = str(msg_type or "").strip()
    if not rid or not rtype or not mtype:
        return False, {}
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, {}
        import requests
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={rtype}"
        payload = {
            "receive_id": rid,
            "msg_type": mtype,
            "content": json.dumps(content_obj or {}, ensure_ascii=False)
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10).json()
        return resp.get("code") == 0, resp if isinstance(resp, dict) else {}
    except Exception:
        return False, {}


def _feishu_send_message(
    receive_id,
    receive_id_type,
    msg_type,
    content_obj,
    *,
    _feishu_send_message_detail,
):
    ok, _ = _feishu_send_message_detail(receive_id, receive_id_type, msg_type, content_obj)
    return ok


def _feishu_update_message_card(
    message_id,
    card_obj,
    *,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    datetime,
    json,
    permission_manager,
):
    mid = str(message_id or "").strip()
    if not mid or not isinstance(card_obj, dict) or not card_obj:
        return False, "缺少消息ID或卡片内容"
    try:
        token = permission_manager.get_access_token()
        if not token:
            return False, "获取飞书访问令牌失败"
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "msg_type": "interactive",
            "content": json.dumps(card_obj, ensure_ascii=False)
        }
        resp = {}
        ok = False
        err_msg = ""
        if mid.startswith("om_"):
            candidate_urls = [
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
            ]
        else:
            candidate_urls = [
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=open_message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}?message_id_type=message_id",
                f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}"
            ]
        for url in candidate_urls:
            try:
                one_resp = requests.patch(url, headers=headers, json=payload, timeout=10).json()
            except Exception as inner_e:
                one_resp = {"code": -1, "msg": str(inner_e)}
            resp = one_resp
            ok = resp.get("code") == 0
            if ok:
                break
            err_msg = str(resp.get("msg") or resp.get("message") or resp)
        try:
            _feishu_recent_events.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "stage": "report_card_patch_result",
                "message_id": mid,
                "ok": ok,
                "resp": resp,
            })
            if len(_feishu_recent_events) > _feishu_recent_events_limit:
                del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
        except Exception:
            pass
        return ok, "" if ok else err_msg
    except Exception as e:
        return False, str(e)


def _feishu_upload_image_by_path(
    image_path,
    *,
    mimetypes,
    os,
    permission_manager,
    relocate_storage_path,
    requests,
):
    path = relocate_storage_path(image_path)
    if not path or (not os.path.exists(path)):
        return ""
    try:
        token = permission_manager.get_access_token()
        if not token:
            return ""
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            files = {"image": (os.path.basename(path), f, mime)}
            data = {"image_type": "message"}
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                files=files,
                data=data,
                timeout=20
            ).json()
        return str((resp or {}).get("data", {}).get("image_key") or "").strip()
    except Exception:
        return ""
