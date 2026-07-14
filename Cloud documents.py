import re
import json
import requests
import time
import hashlib


class CloudDocumentsScoringAgent:
    def __init__(self, access_token_getter, ocr_image_func=None, app_id="", app_secret=""):
        self._access_token_getter = access_token_getter
        self._ocr_image_func = ocr_image_func
        self._app_id = str(app_id or "").strip()
        self._app_secret = str(app_secret or "").strip()
        self._http = requests.Session()
        self._ocr_cache = {}
        self._ocr_cache_ttl_seconds = 300
        self._doc_cache = {}
        self._doc_cache_ttl_seconds = 300
        self._sdk_client = None

    def _get_lark_sdk_client(self):
        if self._sdk_client is not None:
            return self._sdk_client
        if not self._app_id or not self._app_secret:
            return None
        try:
            import lark_oapi as lark
            client = lark.Client.builder() \
                .app_id(self._app_id) \
                .app_secret(self._app_secret) \
                .log_level(lark.LogLevel.ERROR) \
                .build()
            self._sdk_client = client
            return self._sdk_client
        except Exception:
            return None

    def _download_media_with_sdk(self, file_token):
        t = str(file_token or "").strip()
        if not t:
            return None, "", ""
        client = self._get_lark_sdk_client()
        if client is None:
            return None, "", ""
        try:
            from lark_oapi.api.drive.v1 import DownloadMediaRequest
            request = DownloadMediaRequest.builder() \
                .file_token(t) \
                .extra("无") \
                .build()
            response = client.drive.v1.media.download(request)
            if not response.success():
                return None, "", f"下载图片失败（SDK）：{response.code} {response.msg}"
            file_obj = getattr(response, "file", None)
            file_name = str(getattr(response, "file_name", "") or "").lower()
            if file_obj is None:
                return None, "", "下载图片失败（SDK）：返回结果中无文件流"
            content = file_obj.read()
            if not content:
                return None, "", "下载图片失败（SDK）：下载文件为空"
            mime = ""
            if file_name.endswith(".png"):
                mime = "image/png"
            elif file_name.endswith(".webp"):
                mime = "image/webp"
            elif file_name.endswith(".gif"):
                mime = "image/gif"
            elif file_name.endswith(".bmp"):
                mime = "image/bmp"
            elif file_name.endswith(".jpeg") or file_name.endswith(".jpg"):
                mime = "image/jpeg"
            return content, mime, ""
        except Exception as e:
            return None, "", f"下载图片失败（SDK异常）：{str(e)}"

    def _doc_cache_get(self, key):
        now = time.time()
        expired = [k for k, v in (self._doc_cache or {}).items() if not isinstance(v, dict) or (now - float(v.get("ts") or 0)) > self._doc_cache_ttl_seconds]
        for k in expired:
            self._doc_cache.pop(k, None)
        item = self._doc_cache.get(key) if isinstance(self._doc_cache, dict) else None
        if isinstance(item, dict) and item.get("text"):
            return str(item.get("text") or "")
        return ""

    def _doc_cache_set(self, key, text):
        if not isinstance(self._doc_cache, dict):
            return
        t = (text or "").strip()
        if not t:
            return
        self._doc_cache[key] = {"ts": time.time(), "text": t}

    def resolve_url_to_doc(self, url):
        token, doc_type = self._parse_doc_token_from_url(url)
        if not token:
            return "", "", "未能从链接中解析出文档token，请直接粘贴飞书云文档链接。"

        access_token = self._access_token_getter() if callable(self._access_token_getter) else ""
        if not access_token:
            return "", "", "当前无法获取飞书tenant_access_token，无法拉取云文档内容。"

        if doc_type != "wiki":
            return token, doc_type, ""

        headers = {"Authorization": f"Bearer {access_token}"}
        wiki_api = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={token}"
        try:
            resp = self._http.get(wiki_api, headers=headers, timeout=15)
            data = resp.json() if resp is not None else None
            if resp.status_code != 200:
                return "", "", f"wiki解析失败 {resp.status_code} {str(resp.text or '')[:200]}"
            if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                code = data.get("code") if isinstance(data, dict) else ""
                msg = data.get("msg") if isinstance(data, dict) else ""
                if str(code) == "99991672":
                    return "", "", "缺少wiki应用身份权限（wiki:node:read / wiki:wiki:readonly / wiki:wiki）。"
                return "", "", f"wiki解析失败 {code} {msg}"
            node = (data.get("data") or {}).get("node") or {}
            obj_token = str(node.get("obj_token") or "").strip()
            obj_type = str(node.get("obj_type") or "").strip().lower()
            if not obj_token or not obj_type:
                return "", "", "wiki解析失败（未返回obj_token/obj_type）"
            return obj_token, obj_type, ""
        except Exception as e:
            return "", "", f"wiki解析异常 {str(e)}"

    def extract_urls(self, text):
        t = str(text or "")
        urls = re.findall(r"https?://[^\s<>()\"']+", t)
        cleaned = []
        seen = set()
        for u in urls:
            u = u.strip().rstrip(".,;:!?)，。；：！】》）")
            if not u:
                continue
            if u in seen:
                continue
            seen.add(u)
            cleaned.append(u)
        return cleaned

    def _parse_doc_token_from_url(self, url):
        u = str(url or "").strip()
        if not u:
            return "", ""
        patterns = [
            (r"/docx/([a-zA-Z0-9]+)", "docx"),
            (r"/docs/([a-zA-Z0-9]+)", "docs"),
            (r"/wiki/([a-zA-Z0-9]+)", "wiki"),
            (r"/doc/([a-zA-Z0-9]+)", "doc"),
        ]
        for pat, typ in patterns:
            m = re.search(pat, u)
            if m:
                return (m.group(1) or "").strip(), typ
        m = re.search(r"(doxcn[a-zA-Z0-9]+)", u)
        if m:
            return (m.group(1) or "").strip(), "docx"
        return "", ""

    def fetch_document_text(self, url, include_images_ocr=True):
        token, doc_type, err = self.resolve_url_to_doc(url)
        if err:
            if "缺少wiki应用身份权限" in err:
                return "", (
                    "拉取云文档失败：wiki解析失败（缺少wiki应用身份权限）。\n"
                    "请在飞书开放平台为该自建应用开通并发布生效以下任一权限：\n"
                    "- wiki:node:read（推荐）\n"
                    "- wiki:wiki:readonly\n"
                    "- wiki:wiki\n"
                    "开通后再试。\n\n"
                    "绕过方式：不要发知识库/Wiki链接，改发“文档本体”的 docx 链接（/docx/xxxx），或把周报内容直接粘贴到群里。"
                )
            return "", f"拉取云文档失败：{err}"

        if doc_type not in {"docx", "doc", "docs", ""}:
            return "", f"当前文档类型为 {doc_type}，暂不支持读取。你可以把内容复制到消息里再评分。"

        cache_key = f"{doc_type or ''}:{token}:{1 if include_images_ocr else 0}"
        cached_text = self._doc_cache_get(cache_key)
        if cached_text:
            return cached_text, ""

        access_token = self._access_token_getter() if callable(self._access_token_getter) else ""
        headers = {"Authorization": f"Bearer {access_token}"}
        candidates = []
        if doc_type in {"docx", "docs", ""}:
            candidates.append(("GET", f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/raw_content", None))
            candidates.append(("GET", f"https://open.feishu.cn/open-apis/docx/v1/documents/{token}/raw_content?lang=0", None))



        def _friendly_error(code, msg):
            c = str(code or "").strip()
            m = str(msg or "").strip()
            if c == "95006":
                return (
                    "拉取云文档失败：95006（通常是“应用无权读取该文档”）。\n"
                    "请按下面任一方式处理：\n"
                    "1) 在云文档右上角「分享」→「添加协作者」里，把“图创AI/自建应用”加入可阅读；\n"
                    "2) 把文档权限改为「组织内可阅读」（并确保机器人/应用也在可见范围内）；\n"
                    "3) 在飞书开放平台给该应用开通云文档相关权限（docx/doc/drive 只读），并发布/生效到当前租户。\n"
                    "如果不方便改权限：直接把周报/月报内容粘贴到群里，我也能按相同规则评分。"
                )
            if c in {"20009", "11210"}:
                return "拉取云文档失败：应用在当前租户未安装/不可用，请确认应用已安装到这个企业。"
            if c in {"20010", "11225"}:
                return "拉取云文档失败：用户/资源对应用不可见，请在开放平台调整应用可见范围或数据权限。"
            if c in {"10017"}:
                return "拉取云文档失败：机器人不是资源所有者/无权限读取该文档，请在云文档里把机器人加入协作者。"
            return ""

        last_err = ""
        doc_text = ""
        for method, api, payload in candidates:
            try:
                if method == "GET":
                    resp = self._http.get(api, headers=headers, timeout=15)
                else:
                    resp = self._http.post(api, headers=headers, json=payload, timeout=15)
                raw = resp.text or ""
                try:
                    data = resp.json()
                except Exception:
                    data = None
                if resp.status_code != 200:
                    last_err = f"{resp.status_code} {raw[:200]}"
                    continue
                if isinstance(data, dict):
                    code = data.get("code")
                    msg = data.get("msg")
                    if int(code or 0) != 0:
                        friendly = _friendly_error(code, msg)
                        if friendly:
                            return "", friendly
                        last_err = f"{code} {msg}"
                        continue
                    d = data.get("data") or {}
                    if isinstance(d, dict):
                        content = d.get("content")
                        if isinstance(content, str) and content.strip():
                            doc_text = content.strip()
                            break
                        body = d.get("body") or d.get("document") or d
                        if isinstance(body, str) and body.strip():
                            doc_text = body.strip()
                            break
                        if isinstance(body, dict):
                            txt = json.dumps(body, ensure_ascii=False)
                            if txt.strip():
                                doc_text = txt.strip()
                                break
                if raw.strip():
                    doc_text = raw.strip()
                    break
            except Exception as e:
                last_err = str(e)
                continue

        if not doc_text:
            return "", f"拉取云文档失败：{last_err or '未知错误'}。请确认机器人有该文档查看权限，或将周报内容直接粘贴到消息里。"

        if doc_type in {"docx", "docs", ""} and callable(getattr(self, "_ocr_image_func", None)):
            if include_images_ocr:
                merged, _ = self._append_docx_images_ocr(token, doc_text)
                doc_text = merged

        self._doc_cache_set(cache_key, doc_text)
        return doc_text, ""

    def fetch_docx_image_tokens_debug(self, document_id, max_tokens=None, max_pages=60):
        doc_id = str(document_id or "").strip()
        if not doc_id:
            return [], "缺少document_id", {
                "block_total": 0,
                "image_like_block_total": 0,
                "token_candidate_total": 0
            }

        access_token = self._access_token_getter() if callable(self._access_token_getter) else ""
        if not access_token:
            return [], "当前无法获取飞书tenant_access_token，无法拉取云文档图片。", {
                "block_total": 0,
                "image_like_block_total": 0,
                "token_candidate_total": 0
            }

        headers = {"Authorization": f"Bearer {access_token}"}
        page_token = ""
        collected = []
        seen = set()
        stats = {
            "block_total": 0,
            "image_like_block_total": 0,
            "token_candidate_total": 0
        }

        direct_token_keys = {
            "file_token", "image_token", "media_token", "resource_token", "object_token"
        }
        token_parent_hints = {
            "image", "media", "file", "attachment", "thumbnail", "cover", "origin_image"
        }

        def _collect_token(v):
            if not isinstance(v, str):
                return
            s = v.strip()
            if not s or len(s) < 10:
                return
            stats["token_candidate_total"] += 1
            if s not in seen:
                seen.add(s)
                collected.append(s)

        def walk(obj, parent_key=""):
            if obj is None:
                return
            if isinstance(obj, dict):
                lk_set = {str(k).lower() for k in obj.keys()}
                block_type = str(obj.get("block_type") or obj.get("type") or "").lower()
                is_block = ("block_id" in obj) or ("block_type" in obj) or ("children" in obj and "text" in lk_set)
                is_image_like = (
                    ("image" in block_type) or ("media" in block_type) or ("file" in block_type) or ("attachment" in block_type) or
                    bool({"image", "media", "file", "attachment", "gallery"} & lk_set)
                )
                if is_block:
                    stats["block_total"] += 1
                    if is_image_like:
                        stats["image_like_block_total"] += 1
                for k, v in obj.items():
                    lk = str(k).lower()
                    if lk in direct_token_keys:
                        _collect_token(v)
                    elif lk == "token" and (str(parent_key or "").lower() in token_parent_hints or lk_set & token_parent_hints):
                        _collect_token(v)
                    elif lk in {"src", "source"} and isinstance(v, dict):
                        maybe = v.get("token") or v.get("file_token") or v.get("image_token") or v.get("media_token")
                        _collect_token(maybe)
                    walk(v, parent_key=lk)
            elif isinstance(obj, list):
                for it in obj:
                    walk(it, parent_key=parent_key)

        for _ in range(int(max_pages or 60)):
            try:
                url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks"
                params = {"page_size": 500}
                if page_token:
                    params["page_token"] = page_token
                resp = self._http.get(url, headers=headers, params=params, timeout=15)
                data = resp.json() if resp is not None else None
                if resp.status_code != 200:
                    return [], f"获取块失败 {resp.status_code} {str(resp.text or '')[:200]}", stats
                if not isinstance(data, dict) or int(data.get("code") or 0) != 0:
                    code = data.get("code") if isinstance(data, dict) else ""
                    msg = str(data.get("msg") if isinstance(data, dict) else "" or "").strip()
                    lm = msg.lower()
                    if "scope" in lm or "access denied" in lm or "permission" in lm:
                        return [], (
                            "获取云文档图片失败：应用缺少读取文档块/媒体信息的权限，或文档对应用不可见。\n"
                            "请确认：\n"
                            "1) 文档已在「分享」里添加应用/机器人为可阅读；\n"
                            "2) 飞书开放平台已为该自建应用开通并发布生效云文档相关只读权限；\n"
                            "3) 若需要识别图片文字，还需开通“媒体下载”相关权限（如 docs:document.media:download）。"
                        ), stats
                    return [], f"获取块失败 {code} {msg}", stats
                d = data.get("data") or {}
                items = d.get("items") or []
                walk(items, parent_key="items")
                if max_tokens is not None and len(collected) >= int(max_tokens):
                    break
                page_token = str(d.get("page_token") or "").strip()
                if not page_token:
                    break
            except Exception as e:
                return [], f"获取块异常 {str(e)}", stats

        if max_tokens is None:
            return collected, "", stats
        return collected[:int(max_tokens)], "", stats

    def fetch_docx_image_tokens(self, document_id, max_tokens=None, max_pages=60):
        tokens, err, _ = self.fetch_docx_image_tokens_debug(document_id, max_tokens=max_tokens, max_pages=max_pages)
        return tokens, err

    def download_media_bytes(self, file_token):
        t = str(file_token or "").strip()
        if not t:
            return None, "", ""

        access_token = self._access_token_getter() if callable(self._access_token_getter) else ""
        if not access_token:
            return None, "", ""

        headers = {"Authorization": f"Bearer {access_token}"}
        urls = [
            f"https://open.feishu.cn/open-apis/drive/v1/medias/{t}/download",
            f"https://open.feishu.cn/open-apis/drive/v1/media/{t}/download",
        ]
        last_error = ""
        for url in urls:
            try:
                resp = self._http.get(url, headers=headers, timeout=20)
                if resp.status_code == 200 and resp.content:
                    return resp.content, str(resp.headers.get("Content-Type") or ""), ""
                raw = resp.text or ""
                try:
                    data = resp.json()
                except Exception:
                    data = None
                if isinstance(data, dict) and int(data.get("code") or 0) != 0:
                    msg = str(data.get("msg") or "").strip()
                    last_error = f"{data.get('code')} {msg}".strip()
                    if "scope" in msg.lower() or "access denied" in msg.lower() or "permission" in msg.lower():
                        return None, "", (
                            "下载图片失败：应用缺少“云文档媒体下载”相关权限，或图片对应用不可见。"
                            "请在飞书开放平台为该自建应用开通并发布生效：docs:document.media:download（或 drive 相关下载权限），"
                            "并确保文档已分享给应用/机器人后再试。"
                        )
                    return None, "", f"下载图片失败：{data.get('code')} {msg}"
                if resp.status_code in {401, 403}:
                    last_error = f"http {resp.status_code}"
                    return None, "", (
                        "下载图片失败：权限不足（401/403）。请确认文档已分享给应用/机器人，"
                        "并为自建应用开通“云文档媒体下载”相关权限后再试。"
                    )
                if raw:
                    last_error = raw[:200]
            except Exception as e:
                last_error = str(e)
                continue
        sdk_blob, sdk_mime, sdk_err = self._download_media_with_sdk(t)
        if sdk_blob:
            return sdk_blob, sdk_mime, ""
        if sdk_err:
            return None, "", sdk_err
        if last_error:
            return None, "", f"下载图片失败：{last_error}"
        return None, "", ""

    def _append_docx_images_ocr(self, document_id, base_text):
        text = (base_text or "").strip()
        tokens, err = self.fetch_docx_image_tokens(document_id, max_tokens=None, max_pages=80)
        if err or not tokens:
            return text, err

        now = time.time()
        expired = [k for k, v in (self._ocr_cache or {}).items() if not isinstance(v, dict) or (now - float(v.get("ts") or 0)) > self._ocr_cache_ttl_seconds]
        for k in expired:
            self._ocr_cache.pop(k, None)

        doc_id = str(document_id or "").strip()
        digest = hashlib.sha1((",".join(tokens)).encode("utf-8", errors="ignore")).hexdigest()
        cache_key = f"{doc_id}|{digest}"
        cached = self._ocr_cache.get(cache_key) if isinstance(self._ocr_cache, dict) else None
        if isinstance(cached, dict) and cached.get("text"):
            ocr_text = str(cached.get("text") or "").strip()
            merged = f"【图片OCR文字（可能不完整）】\n{ocr_text}\n\n【文档正文】\n{text}".strip()
            if len(merged) > 90000:
                merged = merged[:90000].strip()
            return merged, ""

        warnings = []
        ocr_parts = []
        batch = []
        batch_index = 1
        for ft in tokens:
            blob, mime, dl_err = self.download_media_bytes(ft)
            if not blob:
                if dl_err:
                    warnings.append(dl_err)
                continue
            batch.append((blob, mime))
            if len(batch) >= 4:
                try:
                    t = self._ocr_image_func(batch)
                except Exception:
                    t = ""
                t = (t or "").strip()
                if t:
                    ocr_parts.append(f"【OCR批次{batch_index}】\n{t}".strip())
                    batch_index += 1
                batch = []

        if batch:
            try:
                t = self._ocr_image_func(batch)
            except Exception:
                t = ""
            t = (t or "").strip()
            if t:
                ocr_parts.append(f"【OCR批次{batch_index}】\n{t}".strip())

        if not ocr_parts:
            warn = warnings[0] if warnings else ""
            if warn:
                appended = f"{text}\n\n【图片内容】\n（未能读取/识别图片文字：{warn}）"
                return appended.strip(), warn
            return text, ""

        ocr_text = "\n\n".join(ocr_parts).strip()

        if isinstance(self._ocr_cache, dict):
            self._ocr_cache[cache_key] = {"ts": now, "text": ocr_text}

        merged = f"【图片OCR文字（可能不完整）】\n{ocr_text}\n\n【文档正文】\n{text}".strip()
        if len(merged) > 90000:
            merged = merged[:90000].strip()
        return merged.strip(), ""

    def infer_report_kind(self, prompt_text):
        t = str(prompt_text or "").strip()
        if "月报" in t:
            return "月报"
        if "周报" in t:
            return "周报"
        return "周报/月报"

    def build_scoring_messages(self, report_text, prompt_text):
        kind = self.infer_report_kind(prompt_text)
        report = (report_text or "").strip()
        if len(report) > 80000:
            report = report[:80000].strip()
        system_content = (
            "你是“周报/月报评分智能体”。你必须严格使用固定评分规则，权重不得改动，输出必须稳定一致。\n"
            "语言风格要求：可以使用少量、自然的原生emoji来增强可读性，但不要堆砌。\n"
            "评分总分100分，分项与权重如下：\n"
            "1) 目标与产出对齐 20分：是否清晰说明目标、输出、与目标的对应关系。\n"
            "2) 数据与事实支撑 20分：是否给出关键数据、证据、口径说明；避免空泛。\n"
            "3) 过程复盘与洞察 20分：是否解释原因、得失、关键决策与影响。\n"
            "4) 问题识别与风险 15分：是否明确问题、风险、影响范围、优先级。\n"
            "5) 下周/下月计划可执行性 15分：是否有明确行动、负责人/协作方、里程碑与时间。\n"
            "6) 表达与结构 10分：结构是否清晰、信息密度高、便于阅读。\n"
            "输出格式必须包含：\n"
            "A. 总分（0-100）与等级（S/A/B/C/D）\n"
            "B. 分项得分表（逐项给分+一句话理由）\n"
            "C. 不足清单（按影响从高到低排序，至少5条）\n"
            "D. 不足的具体原因 + 原文证据（与不足一一对应：每条不足都必须包含“具体原因”和“原文引用”）\n"
            "   - 具体原因：说明为什么不足、缺了什么信息、会造成什么影响。\n"
            "   - 原文引用：从文档中复制1-3段关键原文（用引号包裹），并标注你是从哪一段/哪一句判断的。\n"
            "   - 如果文档中完全找不到对应原文，请写“未在文档中找到对应原文”，不得编造。\n"
            "E. 可执行改进建议（与不足一一对应，给出具体写法/补充信息建议）\n"
            "E. 下一版周报/月报模板（可直接复制使用）\n"
            "不要编造报告中不存在的数据；如果缺失，明确说明“缺失项”并给出需要补充的字段。"
        )
        user_content = f"请对下面这份{kind}进行评分并出具改进报告。\n\n【用户提问】\n{(prompt_text or '').strip()}\n\n【云文档内容】\n{report}"
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
