"""Prepare and dispatch Jimeng signed requests and upscale jobs."""

from __future__ import annotations

from typing import Any


def load_jimeng_credentials(
    *,
    load_config_namespace,
    os,
) -> tuple[str, str]:
    env_access_key = (
        os.getenv("VOLCENGINE_ACCESS_KEY_ID", "").strip()
        or os.getenv("JIMENG_ACCESS_KEY_ID", "").strip()
        or os.getenv("JIMENG_ACCESS_KEY", "").strip()
        or os.getenv("AK", "").strip()
    )
    env_secret_key = (
        os.getenv("VOLCENGINE_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("JIMENG_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("JIMENG_SECRET_KEY", "").strip()
        or os.getenv("SK", "").strip()
    )
    if env_access_key and env_secret_key:
        return env_access_key, env_secret_key

    namespace = load_config_namespace()
    if not namespace:
        return "", ""

    access_key = ""
    secret_key = ""
    for key_name in (
        "jimeng_access_key_id",
        "jimeng_access_key",
        "JIMENG_ACCESS_KEY_ID",
        "VOLCENGINE_ACCESS_KEY_ID",
        "AK",
    ):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            access_key = value
            break
    for key_name in (
        "jimeng_secret_access_key",
        "jimeng_secret_key",
        "JIMENG_SECRET_ACCESS_KEY",
        "VOLCENGINE_SECRET_ACCESS_KEY",
        "SK",
    ):
        value = str(namespace.get(key_name, "")).strip()
        if value:
            secret_key = value
            break
    return access_key, secret_key


def build_jimeng_auth_headers(
    action,
    body_text,
    *,
    JIMENG_API_HOST,
    JIMENG_API_REGION,
    JIMENG_API_SERVICE,
    JIMENG_API_VERSION,
    _jimeng_hmac_bytes,
    _jimeng_normalize_query,
    _jimeng_sha256_hex,
    datetime,
    load_config_namespace,
    load_jimeng_credentials,
    timezone,
) -> dict[str, str]:
    access_key, secret_key = load_jimeng_credentials()
    single_api_key = str(load_config_namespace().get("jimeng_jimeng_api_key", "")).strip()
    if not access_key or not secret_key:
        if single_api_key:
            raise RuntimeError(
                "Agent 需要火山引擎 AK/SK 签名鉴权，当前 config.py 里只有 `jimeng_jimeng_api_key` 单个值，"
                "还需要补充 `jimeng_access_key_id` 和 `jimeng_secret_access_key`。"
            )
        raise RuntimeError(
            "未找到即梦的火山引擎 AK/SK。请在环境变量中配置 `AK`、`SK`，"
            "或在 config.py 中配置 `jimeng_access_key_id` 和 `jimeng_secret_access_key`。"
        )

    now_utc = datetime.now(timezone.utc)
    request_date = now_utc.strftime("%Y%m%dT%H%M%SZ")
    short_date = now_utc.strftime("%Y%m%d")
    canonical_query = _jimeng_normalize_query(
        {
            "Action": action,
            "Version": JIMENG_API_VERSION,
        }
    )
    payload_hash = _jimeng_sha256_hex(body_text)
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (
        "content-type:application/json\n"
        f"host:{JIMENG_API_HOST}\n"
        f"x-content-sha256:{payload_hash}\n"
        f"x-date:{request_date}\n"
    )
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{short_date}/{JIMENG_API_REGION}/{JIMENG_API_SERVICE}/request"
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            request_date,
            credential_scope,
            _jimeng_sha256_hex(canonical_request),
        ]
    )
    k_date = _jimeng_hmac_bytes(secret_key.encode("utf-8"), short_date)
    k_region = _jimeng_hmac_bytes(k_date, JIMENG_API_REGION)
    k_service = _jimeng_hmac_bytes(k_region, JIMENG_API_SERVICE)
    k_signing = _jimeng_hmac_bytes(k_service, "request")
    signature = _jimeng_hmac_bytes(k_signing, string_to_sign).hex()
    authorization = (
        f"HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Content-Type": "application/json",
        "Host": JIMENG_API_HOST,
        "X-Date": request_date,
        "X-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }


def prepare_jimeng_hd_input_base64(
    uploaded_file,
    *,
    Image,
    JIMENG_HD_API_MAX_BYTES,
    JIMENG_HD_API_MAX_EDGE,
    Path,
    base64,
    get_image_extension_from_mime,
    io,
    normalize_image_bytes_for_jimeng,
    normalize_uploaded_input,
    sanitize_file_name,
) -> str:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError("Agent 高清失败：没有可用的原图数据。")
    original_name = sanitize_file_name(str(normalized.get("name") or "hd_input.jpg"))
    extension = Path(original_name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        extension = get_image_extension_from_mime(str(normalized.get("type") or "image/jpeg"))
    image_bytes, _extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            if max(working.size) > JIMENG_HD_API_MAX_EDGE:
                ratio = JIMENG_HD_API_MAX_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if "A" in working.getbands():
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")
            quality_candidates = (95, 90, 86, 82, 78, 74, 70, 66)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= JIMENG_HD_API_MAX_BYTES:
                    break
            if len(output_bytes) > JIMENG_HD_API_MAX_BYTES:
                raise RuntimeError("Agent 高清失败：原图压缩后仍超过火山智能超清接口 4.7MB 限制。")
            return base64.b64encode(output_bytes).decode("utf-8")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Agent 高清失败：原图预处理失败。{exc}") from exc


def prepare_jimeng_i2i_uploaded_input(
    uploaded_file,
    error_prefix,
    *,
    Image,
    JIMENG_I2I_MAX_BYTES,
    JIMENG_I2I_MAX_EDGE,
    Path,
    get_image_extension_from_mime,
    io,
    normalize_image_bytes_for_jimeng,
    normalize_uploaded_input,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized = normalize_uploaded_input(uploaded_file)
    image_bytes = bytes(normalized.get("data") or b"")
    if not image_bytes:
        raise RuntimeError(f"{error_prefix}：没有可用的图片数据。")
    original_name = sanitize_file_name(str(normalized.get("name") or "jimeng_i2i_input.jpg"))
    extension = Path(original_name).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        extension = get_image_extension_from_mime(str(normalized.get("type") or "image/jpeg"))
    image_bytes, extension = normalize_image_bytes_for_jimeng(image_bytes, extension)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            working = image.convert("RGBA") if "A" in image.getbands() else image.convert("RGB")
            if max(working.size) > JIMENG_I2I_MAX_EDGE:
                ratio = JIMENG_I2I_MAX_EDGE / float(max(working.size))
                resized_size = (
                    max(1, int(round(working.size[0] * ratio))),
                    max(1, int(round(working.size[1] * ratio))),
                )
                working = working.resize(resized_size, Image.Resampling.LANCZOS)
            if "A" in working.getbands():
                background = Image.new("RGB", working.size, (255, 255, 255))
                background.paste(working, mask=working.getchannel("A"))
                working = background
            else:
                working = working.convert("RGB")
            quality_candidates = (92, 88, 84, 80, 76, 72, 68, 64)
            output_bytes = b""
            for quality in quality_candidates:
                output = io.BytesIO()
                working.save(output, format="JPEG", quality=quality, optimize=True)
                output_bytes = output.getvalue()
                if len(output_bytes) <= JIMENG_I2I_MAX_BYTES:
                    break
            if len(output_bytes) > JIMENG_I2I_MAX_BYTES:
                raise RuntimeError(
                    f"{error_prefix}：图片压缩后仍超过 Agent 4.6 图生图输入限制。"
                )
            return {
                "data": output_bytes,
                "name": f"{Path(original_name).stem}.jpg",
                "type": "image/jpeg",
            }
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"{error_prefix}：图片预处理失败。{exc}") from exc


def build_jimeng_feature_prompt(
    feature,
    custom_prompt,
    aspect_ratio,
    extra_notes,
    base_instruction,
    *,
    GLOBAL_NO_DISTORTION_RULES,
    JIMENG_PROMPT_MAX_CHARS,
    _compact_prompt_text,
) -> str:
    parts: list[str] = [
        GLOBAL_NO_DISTORTION_RULES,
        _compact_prompt_text(base_instruction),
        _compact_prompt_text(feature.get("default_prompt", "")),
        f"正面提示词：{_compact_prompt_text(feature.get('positive_prompt', ''))}"
        if str(feature.get("positive_prompt", "")).strip()
        else "",
        f"负面提示词：{_compact_prompt_text(feature.get('negative_prompt', ''))}"
        if str(feature.get("negative_prompt", "")).strip()
        else "",
        f"目标画幅比例：{aspect_ratio}" if aspect_ratio != "自动" else "",
        f"补充要求：{_compact_prompt_text(custom_prompt)}" if str(custom_prompt or "").strip() else "",
        f"附加说明：{_compact_prompt_text(extra_notes)}" if str(extra_notes or "").strip() else "",
        "请输出适合商业修图或电商展示的高质量结果，仅输出最终图片。",
    ]
    prompt = "；".join(part for part in parts if part)
    prompt = _compact_prompt_text(prompt)
    if len(prompt) <= JIMENG_PROMPT_MAX_CHARS:
        return prompt
    return prompt[:JIMENG_PROMPT_MAX_CHARS].rstrip("；,，。 ") + "。"


def build_jimeng_request_payload(
    prompt,
    aspect_ratio,
    image_urls,
    feature_key,
    *,
    Any,
    JIMENG_HD_IMAGE_EDIT_SCALE,
    JIMENG_HD_OUTPUT_AREA,
    JIMENG_IMAGE_EDIT_SCALE,
    JIMENG_MAX_INPUT_IMAGES,
    JIMENG_PROMPT_MAX_CHARS,
    JIMENG_REQ_KEY,
    enforce_global_no_distortion_rules,
) -> dict[str, Any]:
    normalized_feature_key = str(feature_key or "").strip()
    locked_prompt = enforce_global_no_distortion_rules(prompt, prepend=True)
    if len(locked_prompt) > JIMENG_PROMPT_MAX_CHARS:
        locked_prompt = locked_prompt[:JIMENG_PROMPT_MAX_CHARS].rstrip("；，。 ") + "。"
    payload: dict[str, Any] = {
        "req_key": JIMENG_REQ_KEY,
        "prompt": locked_prompt,
        "force_single": True,
        "size": JIMENG_HD_OUTPUT_AREA if normalized_feature_key == "hd_batch" else 2048 * 2048,
    }
    size_map = (
        {
            "1:1": (2048, 2048),
            "4:3": (2304, 1728),
            "3:2": (2496, 1664),
            "16:9": (2560, 1440),
            "21:9": (3024, 1296),
            "9:16": (1440, 2560),
        }
        if normalized_feature_key == "hd_batch"
        else {
            "1:1": (2048, 2048),
            "4:3": (2304, 1728),
            "3:2": (2496, 1664),
            "16:9": (2560, 1440),
            "21:9": (3024, 1296),
            "9:16": (1440, 2560),
        }
    )
    selected_size = size_map.get(str(aspect_ratio or "").strip())
    if selected_size:
        payload["width"], payload["height"] = selected_size
    cleaned_image_urls = [str(item).strip() for item in (image_urls or []) if str(item).strip()]
    if cleaned_image_urls:
        payload["image_urls"] = cleaned_image_urls[:JIMENG_MAX_INPUT_IMAGES]
        payload["scale"] = (
            JIMENG_HD_IMAGE_EDIT_SCALE if normalized_feature_key == "hd_batch" else JIMENG_IMAGE_EDIT_SCALE
        )
    return payload


def jimeng_signed_post(
    action,
    body,
    timeout,
    *,
    ImageOutcomeUnknown,
    JIMENG_API_ENDPOINT,
    JIMENG_API_VERSION,
    JIMENG_CONCURRENT_LIMIT_RETRY_COUNT,
    JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS,
    JIMENG_SUBMIT_ACTION,
    build_jimeng_auth_headers,
    get_external_request_kwargs,
    get_request_limiter,
    is_jimeng_concurrent_limit_error,
    json,
    requests,
    time,
) -> dict[str, Any]:
    body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    last_error: RuntimeError | None = None
    for attempt in range(JIMENG_CONCURRENT_LIMIT_RETRY_COUNT + 1):
        headers = build_jimeng_auth_headers(action, body_text)
        try:
            response = requests.post(
                JIMENG_API_ENDPOINT,
                params={"Action": action, "Version": JIMENG_API_VERSION},
                data=body_text.encode("utf-8"),
                headers=headers,
                **get_external_request_kwargs(timeout=timeout, use_proxy=False),
            )
        except requests.RequestException as exc:
            if action == JIMENG_SUBMIT_ACTION:
                raise ImageOutcomeUnknown("即梦提交连接中断，远端结果尚未确认，未自动重新提交。") from exc
            raise RuntimeError(f"Agent 请求失败：无法连接到火山引擎视觉服务。{exc}") from exc
        if action == JIMENG_SUBMIT_ACTION and (response.status_code >= 500 or response.status_code == 408):
            raise ImageOutcomeUnknown(f"即梦提交返回 HTTP {response.status_code}，远端结果尚未确认，未自动重新提交。")
        try:
            data = response.json()
        except Exception as exc:
            if action == JIMENG_SUBMIT_ACTION and response.status_code < 400:
                raise ImageOutcomeUnknown("即梦提交响应无法解析，远端结果尚未确认，未自动重新提交。") from exc
            raise RuntimeError(
                f"Agent 响应解析失败（HTTP {response.status_code}）：{response.text[:300]}"
            ) from exc
        if response.status_code < 400:
            return data
        error_message = str(data.get("message") or response.text).strip()
        error_code = data.get("code") or data.get("status")
        if (
            response.status_code in {400, 403, 429}
            and (
                str(error_code or "").strip() == "50430"
                or is_jimeng_concurrent_limit_error(error_message)
            )
            and attempt < JIMENG_CONCURRENT_LIMIT_RETRY_COUNT
        ):
            retry_delay = JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS[
                min(attempt, len(JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS) - 1)
            ]
            get_request_limiter().cooldown("jimeng", seconds=retry_delay)
            time.sleep(retry_delay)
            continue
        request_id = (
            data.get("request_id")
            or ((data.get("ResponseMetadata") or {}).get("RequestId") if isinstance(data.get("ResponseMetadata"), dict) else None)
            or response.headers.get("x-tt-logid")
            or response.headers.get("x-request-id")
        )
        diagnostics = [f"HTTP {response.status_code}"]
        if error_code:
            diagnostics.append(f"错误码 {error_code}")
        if request_id:
            diagnostics.append(f"RequestId {request_id}")
        last_error = RuntimeError(
            f"Agent 请求失败（{'，'.join(diagnostics)}）：{error_message}"
        )
        break
    if last_error is not None:
        raise last_error
    raise RuntimeError("Agent 请求失败：请求未成功，请稍后重试。")


def poll_jimeng_task_result(
    req_key,
    task_id,
    timeout,
    *,
    ImageOutcomeUnknown,
    JIMENG_GET_RESULT_ACTION,
    JIMENG_RESULT_POLL_INTERVAL_SECONDS,
    JIMENG_RESULT_RETRY_DELAY_SECONDS,
    extract_jimeng_result_images,
    jimeng_signed_post,
    json,
    time,
) -> dict[str, Any]:
    """Keep the single vendor slot until the submitted task reaches a terminal state.

    Releasing the process lock after a local timeout is unsafe: the upstream task
    can remain in ``generating`` and the next queued submit then violates the
    account's zero-concurrency allowance.  Once a task_id exists we therefore
    retry transient query failures and wait for an explicit terminal state.
    """
    last_status = "in_queue"
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        result_body = {
            "req_key": req_key,
            "task_id": task_id,
            "req_json": json.dumps({"return_url": True}, ensure_ascii=False, separators=(",", ":")),
        }
        try:
            result_data = jimeng_signed_post(JIMENG_GET_RESULT_ACTION, result_body, timeout=timeout)
        except RuntimeError as exc:
            error_text = str(exc)
            retryable = any(
                marker in error_text
                for marker in (
                    "无法连接到火山引擎视觉服务",
                    "请求超时",
                    "错误码 50430",
                    "Concurrent Limit",
                )
            )
            if not retryable:
                raise
            last_status = "query_retry"
            time.sleep(JIMENG_RESULT_RETRY_DELAY_SECONDS)
            continue
        code = int(result_data.get("code") or 0)
        if code == 50500:
            last_status = "transient_internal_error"
            time.sleep(JIMENG_RESULT_POLL_INTERVAL_SECONDS)
            continue
        if code != 10000:
            raise RuntimeError(f"Agent 查询结果失败：{result_data.get('message') or result_data}")
        payload = result_data.get("data") or {}
        status = str(payload.get("status") or "").strip()
        last_status = status or last_status
        if status == "done":
            return extract_jimeng_result_images(payload)
        if status in {"not_found", "expired"}:
            raise RuntimeError(f"Agent 查询结果失败：任务状态为 {status}。")
        time.sleep(JIMENG_RESULT_POLL_INTERVAL_SECONDS)
    raise ImageOutcomeUnknown(
        f"即梦任务 {task_id} 持续 30 分钟仍未结束（{last_status}），远端结果尚未确认，未自动重新提交。"
    )


def call_jimeng_hd_upscale(
    uploaded_files,
    *,
    JIMENG_HD_API_RESOLUTION,
    JIMENG_HD_API_SCALE,
    JIMENG_HD_UPSCALE_REQ_KEY,
    JIMENG_SUBMIT_ACTION,
    _JIMENG_TASK_LOCK,
    get_jimeng_public_upload_base_url,
    jimeng_signed_post,
    poll_jimeng_task_result,
    prepare_jimeng_hd_input_base64,
    save_uploaded_inputs_for_jimeng,
) -> dict[str, Any]:
    normalized_files = list(uploaded_files or [])
    if not normalized_files:
        raise RuntimeError("即梦超清失败：请先上传 1 张原图。")
    submit_body = {
        "req_key": JIMENG_HD_UPSCALE_REQ_KEY,
        "resolution": JIMENG_HD_API_RESOLUTION,
        "scale": JIMENG_HD_API_SCALE,
    }
    if get_jimeng_public_upload_base_url():
        image_urls = save_uploaded_inputs_for_jimeng(normalized_files[:1])
        if not image_urls:
            raise RuntimeError("即梦超清失败：没有生成可访问的原图地址。")
        submit_body["image_urls"] = image_urls[:1]
    else:
        submit_body["binary_data_base64"] = [
            prepare_jimeng_hd_input_base64(normalized_files[0])
        ]
    with _JIMENG_TASK_LOCK:
        submit_data = jimeng_signed_post(JIMENG_SUBMIT_ACTION, submit_body, timeout=120)
        if int(submit_data.get("code") or 0) != 10000:
            raise RuntimeError(f"即梦超清提交失败：{submit_data.get('message') or submit_data}")
        task_id = str(((submit_data.get("data") or {}).get("task_id")) or "").strip()
        if not task_id:
            raise RuntimeError("即梦超清提交失败：返回结果里没有 task_id。")
        result = poll_jimeng_task_result(JIMENG_HD_UPSCALE_REQ_KEY, task_id, timeout=120)
    result["channel"] = "即梦智能超清 · 原生 8K"
    result["resolution"] = JIMENG_HD_API_RESOLUTION
    result["req_key"] = JIMENG_HD_UPSCALE_REQ_KEY
    result["task_id"] = task_id
    return result


def call_openrouter_hd_then_upscale(
    model,
    prompt,
    aspect_ratio,
    uploaded_files,
    *,
    PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
    build_portrait_hd_prompt,
    build_uploaded_input_from_image_url_raw,
    call_jimeng_hd_upscale,
    call_openrouter,
    get_portrait_hd_inputs,
) -> dict[str, Any]:
    portrait_inputs = get_portrait_hd_inputs(uploaded_files)
    base_result = call_openrouter(
        model=model,
        prompt=build_portrait_hd_prompt(prompt),
        uploaded_files=portrait_inputs,
        output_mode="image",
        aspect_ratio=aspect_ratio,
        image_size=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
    )
    original_images = list(base_result.get("images") or [])
    if not original_images:
        return base_result
    upscaled_images: list[str] = []
    fallback_messages: list[str] = []
    for index, image_url in enumerate(original_images, start=1):
        try:
            hd_input = build_uploaded_input_from_image_url_raw(image_url, base_name=f"openrouter_hd_stage_{index}.png")
            hd_result = call_jimeng_hd_upscale(uploaded_files=[hd_input])
            hd_images = list(hd_result.get("images") or [])
            if not hd_images:
                raise RuntimeError("智能超清阶段没有返回可用图片。")
            upscaled_images.append(str(hd_images[0]))
        except Exception as exc:
            upscaled_images.append(str(image_url))
            fallback_messages.append(f"第 {index} 张高清增强失败，已保留模型原图。原因：{exc}")
    result_text_parts = [str(base_result.get("text") or "").strip(), *fallback_messages]
    return {
        "images": upscaled_images,
        "text": "\n\n".join(part for part in result_text_parts if part).strip(),
        "raw": base_result.get("raw"),
        "intermediate_hd_images": original_images,
    }


def call_openrouter_portrait_hd(
    model,
    prompt,
    aspect_ratio,
    uploaded_files,
    source_only,
    preserve_native_resolution,
    *,
    PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
    build_portrait_hd_prompt,
    build_portrait_hd_size_instruction,
    call_openrouter_images_api,
    finalize_portrait_hd_result,
    get_portrait_hd_inputs,
    get_uploaded_input_closest_aspect_ratio,
    is_omnia_image_outcome_unknown,
) -> dict[str, Any]:
    portrait_inputs = list(uploaded_files or [])[:1] if source_only else get_portrait_hd_inputs(uploaded_files)
    source_input = portrait_inputs[0]
    source_aspect_ratio = get_uploaded_input_closest_aspect_ratio(source_input, fallback=aspect_ratio)
    hd_prompt = build_portrait_hd_prompt(prompt)
    if preserve_native_resolution:
        hd_prompt = hd_prompt.replace(
            "最终画布的像素宽度和像素高度必须分别与第1张原图完全一致，只提升清晰度。",
            "保持原图宽高比、完整构图和内容，以原生 4K 分辨率输出高清结果，不要缩回上传图尺寸。",
        )
    else:
        hd_prompt += "\n\n" + build_portrait_hd_size_instruction(source_input)
    try:
        result = call_openrouter_images_api(
            model=model,
            prompt=hd_prompt,
            aspect_ratio=source_aspect_ratio,
            uploaded_files=portrait_inputs,
            resolution=PORTRAIT_HD_DEFAULT_IMAGE_SIZE,
        )
        if preserve_native_resolution:
            # Keep provider originals byte-for-byte; history and downloads save these sources.
            result["channel"] = "Nano Banana 2.1 · 原生高清原图"
        else:
            result = finalize_portrait_hd_result(result, source_input)
            result["channel"] = "Images API 高清增强 · 原图尺寸输出"
        return result
    except Exception as exc:
        if is_omnia_image_outcome_unknown(exc):
            raise
        raise RuntimeError(
            "OmniaKey 原生 4K 调用失败。为避免画质降级，本次未使用聊天兼容通道或本地放大。"
            f"原因：{exc}"
        ) from exc
