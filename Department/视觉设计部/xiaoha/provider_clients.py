"""Model requests, polling and error handling for Xiaoha providers."""

from __future__ import annotations

from typing import Any


def call_omnia_sync_image_api(
    model,
    prompt,
    uploaded_files,
    aspect_ratio,
    resolution,
    *,
    size,
    Any,
    GEMINI_IMAGE_ASPECT_RATIOS,
    Image,
    OMNIAKEY_API_BASE,
    OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
    OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS,
    OMNIA_IMAGE_MODEL_LABELS,
    OmniaImageOutcomeUnknown,
    base64,
    build_omnia_task_error_message,
    enforce_global_no_distortion_rules,
    get_external_request_kwargs,
    get_uploaded_input_closest_aspect_ratio,
    image_bytes_to_data_url,
    io,
    load_omnia_api_key,
    math,
    prepare_omnia_media_request_inputs,
    re,
    record_omnia_provider_status,
    redact_background_error_text,
    requests,
) -> dict[str, Any]:
    record_omnia_provider_status("rejected")
    api_key = load_omnia_api_key()
    if not api_key:
        raise RuntimeError("OmniaKey 未配置 OMNIAKEY_API_KEY，请联系管理员完成配置。")
    files = prepare_omnia_media_request_inputs(list(uploaded_files or []))
    payload: dict[str, Any] = {
        "model": model,
        "prompt": enforce_global_no_distortion_rules(prompt),
        "n": 1,
        "response_format": "b64_json",
    }
    normalized_resolution = str(resolution or "").strip().upper()
    # The synchronous API accepts pixel size; Gemini's media-task parameters
    # (aspect_ratio/image_size) are ignored on this endpoint.
    normalized_ratio = str(aspect_ratio or "").strip()
    if normalized_ratio not in GEMINI_IMAGE_ASPECT_RATIOS:
        normalized_ratio = get_uploaded_input_closest_aspect_ratio(files[0], "1:1") if files else "1:1"
    ratio_width, ratio_height = map(int, normalized_ratio.split(":"))
    edge = {"1K": 1024, "2K": 2048, "4K": 4096}.get(normalized_resolution, 1024)
    scale = math.sqrt(ratio_width / ratio_height)
    width = max(8, round(edge * scale / 8) * 8)
    height = max(8, round(edge / scale / 8) * 8)
    payload["size"] = f"{width}x{height}"
    if size and size != "auto":
        if not re.fullmatch(r"[1-9]\d{1,4}x[1-9]\d{1,4}", str(size)):
            raise ValueError("图片尺寸格式无效，请使用宽x高。")
        exact_width, exact_height = map(int, size.split("x"))
        if max(exact_width, exact_height) > 16384 or exact_width * exact_height > 4096 ** 2:
            raise ValueError("请求的图片尺寸超过 4K 像素面积上限。")
        payload["size"] = size
    endpoint = "edits" if files else "generations"
    headers = {"Authorization": f"Bearer {api_key}"}
    if files:
        # Send real file parts; the Nano edit route does not reliably consume
        # JSON data URLs. Let requests supply the multipart boundary.
        image_field = "image" if len(files) == 1 else "image[]"
        request_body = {
            "data": payload,
            "files": [(image_field, (item["name"], item["data"], item["type"])) for item in files],
        }
    else:
        headers["Content-Type"] = "application/json"
        request_body = {"json": payload}
    # OmniaKey's synchronous Images API bypasses the failing media-task worker.
    # Its idempotency behavior is not documented, so submit exactly once.
    record_omnia_provider_status("uncertain")
    try:
        response = requests.post(
            f"{OMNIAKEY_API_BASE}/v1/images/{endpoint}",
            headers=headers,
            **request_body,
            **get_external_request_kwargs(
                timeout=(OMNIAKEY_CONNECT_TIMEOUT_SECONDS, OMNIAKEY_SYNC_IMAGE_TIMEOUT_SECONDS),
                use_proxy=False,
            ),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise OmniaImageOutcomeUnknown(
            "OmniaKey 同步生图连接中断或等待超时，远端结果尚未确认。"
            "为避免重复计费，未自动重新提交；请先在服务商后台确认结果。"
        ) from exc
    except requests.RequestException as exc:
        raise OmniaImageOutcomeUnknown(
            "OmniaKey 同步生图响应传输中断，远端结果尚未确认，未自动重新提交。"
        ) from exc
    request_id = str(response.headers.get("x-request-id") or "").strip()
    request_note = f"（请求 {request_id}）" if request_id else ""
    if response.status_code >= 500 or response.status_code == 408:
        raise OmniaImageOutcomeUnknown(
            f"OmniaKey 同步生图返回 HTTP {response.status_code}，远端结果尚未确认，"
            "未自动重新提交；请先在服务商后台确认结果。" + request_note
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise OmniaImageOutcomeUnknown(
            "OmniaKey 同步生图返回无法解析的响应，未自动重新提交。" + request_note
        ) from exc
    if not isinstance(data, dict):
        raise OmniaImageOutcomeUnknown("OmniaKey 同步生图响应格式异常，未自动重新提交。" + request_note)
    if response.status_code >= 400 or data.get("error"):
        record_omnia_provider_status("rejected" if response.status_code >= 400 else "failed")
        raise RuntimeError(
            f"OmniaKey 同步生图失败（HTTP {response.status_code}）："
            + redact_background_error_text(build_omnia_task_error_message(data)) + request_note
        )
    record_omnia_provider_status("success")
    images = []
    for item in data.get("data") or []:
        if not isinstance(item, dict):
            continue
        encoded = str(item.get("b64_json") or "").strip()
        if encoded:
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(image_bytes)) as image:
                    mime = Image.MIME.get(image.format, "image/png")
                    image.verify()
            except Exception as exc:
                raise RuntimeError("OmniaKey 返回的图片数据无法解码。" + request_note) from exc
            images.append(image_bytes_to_data_url(image_bytes, mime))
        elif item.get("url"):
            images.append(str(item["url"]))
    if not images:
        raise RuntimeError("OmniaKey 同步生图未返回图片。" + request_note)
    return {
        "images": images, "text": "", "raw": data,
        "requested_resolution": normalized_resolution,
        "channel": f"{OMNIA_IMAGE_MODEL_LABELS.get(model, model)} · OmniaKey Images API",
    }


def call_omnia_image_api(
    model,
    prompt,
    uploaded_files,
    aspect_ratio,
    resolution,
    max_attempts,
    *,
    call_omnia_media_image_api,
    resolve_omnia_image_model,
) -> dict[str, Any]:
    omnia_model = resolve_omnia_image_model(model)
    # 同步 Images 接口会在长时间生图时被服务商网关以 524 中断。
    # 异步提交立即取得任务 ID，后续仅查询原任务，不回退到同步接口。
    return call_omnia_media_image_api(omnia_model or model, prompt, uploaded_files, aspect_ratio, resolution, max_attempts)


def call_omnia_media_image_api(
    model,
    prompt,
    uploaded_files,
    aspect_ratio,
    resolution,
    max_attempts,
    *,
    Any,
    GEMINI_IMAGE_ASPECT_RATIOS,
    GEMINI_IMAGE_SIZES,
    NANO_BANANA_MODEL,
    OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
    OMNIAKEY_MEDIA_MAX_ATTEMPTS,
    OMNIAKEY_MEDIA_RETRY_DELAYS,
    OMNIAKEY_MEDIA_TASKS_URL,
    OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES,
    OMNIAKEY_READ_TIMEOUT_SECONDS,
    OMNIAKEY_TASK_RECEIPTS_FILE,
    OmniaImageOutcomeUnknown,
    _OPENROUTER_ERROR_LOG_LOCK,
    base64,
    build_omnia_task_error_message,
    collect_omnia_image_task,
    current_omnia_call_metadata,
    datetime,
    enforce_global_no_distortion_rules,
    get_external_request_kwargs,
    get_request_limiter,
    get_uploaded_input_closest_aspect_ratio,
    json,
    load_omnia_api_key,
    prepare_omnia_media_request_inputs,
    record_omnia_provider_status,
    record_omnia_task,
    requests,
    resolve_omnia_image_model,
    time,
    timezone,
    uuid4,
) -> dict[str, Any]:
    record_omnia_provider_status("rejected")
    omnia_model = resolve_omnia_image_model(model)
    if not omnia_model:
        raise RuntimeError(f"OmniaKey 不支持该生图模型：{model}")
    api_key = load_omnia_api_key()
    if not api_key:
        raise RuntimeError("OmniaKey 未配置 OMNIAKEY_API_KEY，请先在环境变量或 config.py 中配置。")

    prepared_files = prepare_omnia_media_request_inputs(list(uploaded_files or []))
    operation = "edit" if prepared_files else "generate"
    parameters: dict[str, Any] = {}
    normalized_aspect_ratio = str(aspect_ratio or "").strip()
    if omnia_model == NANO_BANANA_MODEL and normalized_aspect_ratio not in GEMINI_IMAGE_ASPECT_RATIOS:
        normalized_aspect_ratio = get_uploaded_input_closest_aspect_ratio(prepared_files[0], "1:1") if prepared_files else "1:1"
    if normalized_aspect_ratio in GEMINI_IMAGE_ASPECT_RATIOS:
        parameters["aspect_ratio"] = normalized_aspect_ratio
    normalized_resolution = str(resolution or "").strip().upper()
    if normalized_resolution in GEMINI_IMAGE_SIZES:
        parameters["image_size"] = normalized_resolution

    task_input: dict[str, Any] = {
        "prompt": enforce_global_no_distortion_rules(prompt),
    }
    if prepared_files:
        references = [
            {"data": base64.b64encode(item["data"]).decode("ascii"), "mime_type": item["type"]}
            for item in prepared_files
        ]
        if len(references) == 1:
            task_input["image"] = references[0]
        else:
            task_input["images"] = references
    payload = {
        "model": omnia_model,
        "type": "image",
        "operation": operation,
        "input": task_input,
        "parameters": parameters,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"xiaoha-{uuid4().hex}",
    }
    normalized_max_attempts = max(int(max_attempts or OMNIAKEY_MEDIA_MAX_ATTEMPTS), 1)
    response = None
    last_request_error: requests.RequestException | None = None
    record_omnia_provider_status("uncertain")
    for attempt_index in range(normalized_max_attempts):
        try:
            response = requests.post(
                OMNIAKEY_MEDIA_TASKS_URL,
                headers=headers,
                json=payload,
                **get_external_request_kwargs(
                    timeout=(OMNIAKEY_CONNECT_TIMEOUT_SECONDS, OMNIAKEY_READ_TIMEOUT_SECONDS),
                    use_proxy=False,
                ),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_request_error = exc
            if attempt_index + 1 >= normalized_max_attempts:
                raise OmniaImageOutcomeUnknown(
                    "OmniaKey 提交结果尚未确认，同一幂等键重试仍未收到结果，未自动重新提交。"
                ) from exc
            time.sleep(OMNIAKEY_MEDIA_RETRY_DELAYS[min(attempt_index, len(OMNIAKEY_MEDIA_RETRY_DELAYS) - 1)])
            continue
        except requests.RequestException as exc:
            raise OmniaImageOutcomeUnknown(
                "OmniaKey 提交响应传输中断，远端结果尚未确认，未自动重新提交。"
            ) from exc
        if (
            response.status_code in OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES
            and attempt_index + 1 < normalized_max_attempts
        ):
            retry_delay = OMNIAKEY_MEDIA_RETRY_DELAYS[min(attempt_index, len(OMNIAKEY_MEDIA_RETRY_DELAYS) - 1)]
            if response.status_code == 429:
                get_request_limiter().cooldown("omnia_image", seconds=retry_delay)
            time.sleep(retry_delay)
            continue
        break

    if response is None:
        raise RuntimeError(f"OmniaKey 连接失败：{last_request_error or '未收到响应'}")
    if response.status_code >= 500 or response.status_code == 408:
        raise OmniaImageOutcomeUnknown(
            f"OmniaKey 提交返回 HTTP {response.status_code}，远端结果尚未确认，未自动重新提交。"
        )
    try:
        create_data = response.json()
    except Exception as exc:
        raise OmniaImageOutcomeUnknown(f"OmniaKey 提交响应无法解析（HTTP {response.status_code}），未自动重新提交。") from exc
    if response.status_code >= 400:
        record_omnia_provider_status("rejected")
        raise RuntimeError(
            f"OmniaKey 创建图片任务失败（HTTP {response.status_code}）：{build_omnia_task_error_message(create_data)}"
        )

    if not isinstance(create_data, dict):
        raise OmniaImageOutcomeUnknown("OmniaKey 提交响应格式异常，远端结果尚未确认，未自动重新提交。")
    task_id = str((create_data or {}).get("id") or "").strip()
    if not task_id:
        raise OmniaImageOutcomeUnknown("OmniaKey 提交响应没有任务 ID，远端结果尚未确认，未自动重新提交。")

    # logs 已挂载持久化目录。只保存回执，避免写入密钥、提示词或参考图。
    receipt = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "model": omnia_model,
        "resolution": normalized_resolution,
        "idempotency_key": headers["Idempotency-Key"],
        **current_omnia_call_metadata(),
    }
    try:
        OMNIAKEY_TASK_RECEIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _OPENROUTER_ERROR_LOG_LOCK:
            with OMNIAKEY_TASK_RECEIPTS_FILE.open("a", encoding="utf-8") as receipt_file:
                receipt_file.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise OmniaImageOutcomeUnknown(
            f"OmniaKey 任务已提交（任务 {task_id}），但回执保存失败，未自动重新提交。请继续查询原任务。"
        ) from exc
    try:
        record_omnia_task(task_id)
    except Exception as exc:
        raise OmniaImageOutcomeUnknown(
            f"OmniaKey 任务已提交（任务 {task_id}），通道回执关联失败，请继续查询原任务，未自动重新提交。"
        ) from exc
    return collect_omnia_image_task(task_id, create_data, api_key, omnia_model, normalized_resolution)


def resume_omnia_image_task(
    task_id,
    model,
    resolution,
    *,
    collect_omnia_image_task,
    load_omnia_api_key,
    re,
    resolve_omnia_image_model,
) -> dict[str, Any]:
    """恢复已提交任务的查询和下载，不创建新的付费生图任务。"""
    task_id = str(task_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
        raise ValueError("OmniaKey 任务编号无效。")
    api_key = load_omnia_api_key()
    if not api_key:
        raise RuntimeError("OmniaKey 未配置 OMNIAKEY_API_KEY，请联系管理员完成配置。")
    omnia_model = resolve_omnia_image_model(model)
    if not omnia_model:
        raise ValueError("OmniaKey 生图模型无效。")
    return collect_omnia_image_task(task_id, {"status": "queued"}, api_key, omnia_model, str(resolution or "").strip().upper())


def collect_omnia_image_task(
    task_id,
    create_data,
    api_key,
    omnia_model,
    normalized_resolution,
    *,
    Any,
    OMNIAKEY_CONNECT_TIMEOUT_SECONDS,
    OMNIAKEY_MEDIA_TASKS_URL,
    OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES,
    OMNIAKEY_READ_TIMEOUT_SECONDS,
    OMNIAKEY_TASK_POLL_INTERVAL_SECONDS,
    OMNIAKEY_TASK_TIMEOUT_SECONDS,
    OMNIA_IMAGE_MODEL_LABELS,
    OmniaImageOutcomeUnknown,
    build_omnia_task_error_message,
    get_external_request_kwargs,
    get_request_limiter,
    image_bytes_to_data_url,
    record_background_job_error,
    record_omnia_provider_status,
    requests,
    time,
    urllib,
) -> dict[str, Any]:
    deadline = time.monotonic() + OMNIAKEY_TASK_TIMEOUT_SECONDS
    task_data: dict[str, Any] = dict(create_data or {})
    poll_failures = 0
    while time.monotonic() < deadline:
        status = str(task_data.get("status") or "").strip().lower()
        if status == "succeeded":
            record_omnia_provider_status("success")
            break
        if status in {"failed", "canceled", "cancelled"}:
            record_omnia_provider_status("failed")
            error = RuntimeError(
                f"OmniaKey 图片任务失败（任务 {task_id}）：{build_omnia_task_error_message(task_data)}"
            )
            record_background_job_error(task_id, "omnia_image", status, error)
            raise error
        time.sleep(OMNIAKEY_TASK_POLL_INTERVAL_SECONDS)
        try:
            poll_response = requests.get(
                f"{OMNIAKEY_MEDIA_TASKS_URL}/{urllib.parse.quote(task_id)}",
                headers={"Authorization": f"Bearer {api_key}"},
                **get_external_request_kwargs(
                    timeout=(OMNIAKEY_CONNECT_TIMEOUT_SECONDS, OMNIAKEY_READ_TIMEOUT_SECONDS),
                    use_proxy=False,
                ),
            )
        except requests.RequestException as exc:
            poll_failures += 1
            if poll_failures < 4:
                continue
            raise OmniaImageOutcomeUnknown(
                f"OmniaKey 查询图片任务失败（任务 {task_id}，已重试 3 次），远端结果尚未确认，未自动重新提交。"
            ) from exc
        if poll_response.status_code in OMNIAKEY_MEDIA_TRANSIENT_STATUS_CODES:
            if poll_response.status_code == 429:
                get_request_limiter().cooldown("omnia_image", seconds=OMNIAKEY_TASK_POLL_INTERVAL_SECONDS)
            poll_failures += 1
            if poll_failures < 4:
                continue
        else:
            poll_failures = 0
        if poll_response.status_code >= 400:
            try:
                poll_error = poll_response.json()
            except Exception:
                poll_error = poll_response.text
            raise OmniaImageOutcomeUnknown(
                f"OmniaKey 查询图片任务失败（任务 {task_id}，HTTP {poll_response.status_code}）："
                f"{build_omnia_task_error_message(poll_error if isinstance(poll_error, dict) else {'error': {'message': poll_error}})}。"
                "远端结果尚未确认，未自动重新提交。"
            )
        try:
            task_data = poll_response.json()
            if not isinstance(task_data, dict):
                raise ValueError("Invalid task response")
        except Exception as exc:
            raise OmniaImageOutcomeUnknown(f"OmniaKey 查询图片任务 {task_id} 响应无法解析，未自动重新提交。") from exc
    else:
        raise OmniaImageOutcomeUnknown(
            f"OmniaKey 图片任务等待超时（{OMNIAKEY_TASK_TIMEOUT_SECONDS} 秒，任务 {task_id}）。"
            "远端结果尚未确认，未自动重新提交，请继续查询原任务。"
        )

    assets = [asset for asset in list(task_data.get("assets") or []) if isinstance(asset, dict)]
    image_assets = [asset for asset in assets if str(asset.get("kind") or "image").strip() == "image"]
    first_asset = next(iter(image_assets), None)
    if not first_asset:
        raise RuntimeError("OmniaKey 图片任务没有返回可用图片。")
    asset_url = str(first_asset.get("url") or "").strip()
    if not asset_url:
        raise RuntimeError("OmniaKey 图片任务没有返回图片下载地址。")
    for download_attempt in range(3):
        try:
            with get_request_limiter().slot("download"):
                image_response = requests.get(
                    asset_url,
                    **get_external_request_kwargs(timeout=(OMNIAKEY_CONNECT_TIMEOUT_SECONDS, OMNIAKEY_READ_TIMEOUT_SECONDS), use_proxy=False),
                )
            image_response.raise_for_status()
            break
        except requests.RequestException as exc:
            if download_attempt == 2:
                raise OmniaImageOutcomeUnknown(
                    f"OmniaKey 图片已生成（任务 {task_id}），但下载失败，未自动重新提交生图。请恢复原任务的图片下载。"
                ) from exc
            time.sleep(download_attempt + 1)
    mime_type = (
        str(first_asset.get("mime_type") or "").strip()
        or image_response.headers.get("Content-Type", "").split(";", 1)[0].strip()
        or "image/jpeg"
    )
    return {
        "images": [image_bytes_to_data_url(image_response.content, mime_type)],
        "text": "",
        "raw": task_data,
        "requested_resolution": normalized_resolution,
        "channel": f"{OMNIA_IMAGE_MODEL_LABELS.get(omnia_model, omnia_model)} · OmniaKey",
    }


def call_openrouter_images_api(
    model,
    prompt,
    uploaded_files,
    aspect_ratio,
    resolution,
    max_attempts,
    *,
    call_omnia_image_api,
    resolve_omnia_image_model,
) -> dict[str, Any]:
    """Run supported image models through OmniaKey's image endpoints."""
    omnia_model = resolve_omnia_image_model(model)
    if omnia_model:
        return call_omnia_image_api(
            model=omnia_model,
            prompt=prompt,
            uploaded_files=uploaded_files,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            max_attempts=max_attempts,
        )
    raise RuntimeError(f"OmniaKey 不支持该生图模型：{model}")


def call_ark_seedream_images_api(
    prompt,
    uploaded_files,
    size,
    *,
    ARK_IMAGES_CONNECT_TIMEOUT_SECONDS,
    ARK_IMAGES_MAX_ATTEMPTS,
    ARK_IMAGES_READ_TIMEOUT_SECONDS,
    ARK_IMAGES_RETRY_DELAYS,
    ARK_IMAGES_URL,
    ARK_SEEDREAM_5_PRO_MODEL,
    ARK_SEEDREAM_5_PRO_SIZE,
    Any,
    ImageOutcomeUnknown,
    enforce_global_no_distortion_rules,
    file_to_data_url,
    get_external_request_kwargs,
    get_request_limiter,
    load_ark_api_key,
    prepare_ark_seedream_uploaded_input,
    requests,
    time,
) -> dict[str, Any]:
    api_key = load_ark_api_key()
    if not api_key:
        raise RuntimeError("即梦 5 Pro 未配置 ARK_API_KEY。")

    normalized_files = list(uploaded_files or [])
    if not normalized_files:
        raise RuntimeError("即梦 5 Pro 扩图失败：请先上传 1 张原图。")
    if len(normalized_files) > 10:
        raise RuntimeError("即梦 5 Pro 单次最多支持 10 张参考图。")

    image_inputs = [
        file_to_data_url(prepare_ark_seedream_uploaded_input(uploaded_file))
        for uploaded_file in normalized_files
    ]
    payload: dict[str, Any] = {
        "model": ARK_SEEDREAM_5_PRO_MODEL,
        "prompt": enforce_global_no_distortion_rules(prompt),
        "image": image_inputs[0] if len(image_inputs) == 1 else image_inputs,
        "size": str(size or ARK_SEEDREAM_5_PRO_SIZE).strip() or ARK_SEEDREAM_5_PRO_SIZE,
        "response_format": "url",
        "watermark": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = None
    last_request_error: requests.RequestException | None = None
    for attempt_index in range(ARK_IMAGES_MAX_ATTEMPTS):
        try:
            response = requests.post(
                ARK_IMAGES_URL,
                headers=headers,
                json=payload,
                **get_external_request_kwargs(
                    timeout=(ARK_IMAGES_CONNECT_TIMEOUT_SECONDS, ARK_IMAGES_READ_TIMEOUT_SECONDS),
                    use_proxy=False,
                ),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise ImageOutcomeUnknown(
                "即梦 5 Pro 连接中断或等待超时，远端结果尚未确认，未自动重新提交。"
            ) from exc
        except requests.RequestException as exc:
            raise ImageOutcomeUnknown(
                "即梦 5 Pro 响应传输中断，远端结果尚未确认，未自动重新提交。"
            ) from exc
        if response.status_code >= 500 or response.status_code == 408:
            raise ImageOutcomeUnknown(
                f"即梦 5 Pro 返回 HTTP {response.status_code}，远端结果尚未确认，未自动重新提交。"
            )
        if (
            response.status_code == 429
            and attempt_index + 1 < ARK_IMAGES_MAX_ATTEMPTS
        ):
            retry_delay = ARK_IMAGES_RETRY_DELAYS[min(attempt_index, len(ARK_IMAGES_RETRY_DELAYS) - 1)]
            get_request_limiter().cooldown("ark", seconds=retry_delay)
            time.sleep(retry_delay)
            continue
        break

    if response is None:
        raise RuntimeError(f"即梦 5 Pro 连接失败：{last_request_error or '未收到响应'}")
    try:
        data = response.json()
    except Exception as exc:
        raise ImageOutcomeUnknown(f"即梦 5 Pro 返回了无法解析的内容（HTTP {response.status_code}），未自动重新提交。") from exc
    if response.status_code >= 400:
        error_payload = data.get("error") if isinstance(data, dict) else data
        error_message = (
            error_payload.get("message") or error_payload
            if isinstance(error_payload, dict)
            else error_payload
        )
        raise RuntimeError(f"即梦 5 Pro 请求失败（HTTP {response.status_code}）：{error_message}")

    images: list[str] = []
    for item in list(data.get("data") or []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("url") or "").strip()
        if image_url:
            images.append(image_url)
            continue
        encoded_image = str(item.get("b64_json") or "").strip()
        if encoded_image:
            images.append(f"data:image/png;base64,{encoded_image}")
    if not images:
        raise RuntimeError("即梦 5 Pro 没有返回可用图片。")
    return {
        "images": images,
        "text": "",
        "raw": data,
        "channel": "即梦 5 Pro · 火山方舟",
        "requested_resolution": payload["size"],
    }


def call_omnia_chat_api(
    model,
    prompt,
    uploaded_files,
    *,
    Any,
    ImageOutcomeUnknown,
    OMNIAKEY_CHAT_COMPLETIONS_URL,
    OMNIAKEY_MEDIA_RETRY_DELAYS,
    OMNIAKEY_VISION_TEXT_FALLBACK_MODELS,
    OMNIAKEY_VISION_TEXT_MODEL,
    extract_response_payload,
    file_to_data_url,
    get_external_request_kwargs,
    get_request_limiter,
    load_omnia_api_key,
    prepare_openrouter_request_inputs,
    record_omnia_model,
    record_omnia_provider_status,
    redact_background_error_text,
    requests,
    time,
) -> dict[str, Any]:
    """Call OmniKey's OpenAI-compatible chat endpoint for text and vision work."""
    record_omnia_provider_status("rejected")
    api_key = load_omnia_api_key()
    if not api_key:
        raise RuntimeError("OmniaKey 未配置 OMNIAKEY_API_KEY，请联系管理员完成配置。")

    content: list[dict[str, Any]] = [{"type": "text", "text": str(prompt or "").strip()}]
    for safe_uploaded_file in prepare_openrouter_request_inputs(list(uploaded_files or [])):
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": file_to_data_url(safe_uploaded_file)},
            }
        )
    requested_model = str(model or "").strip()
    candidate_models = (requested_model,)
    if requested_model == OMNIAKEY_VISION_TEXT_MODEL:
        candidate_models += tuple(
            candidate
            for candidate in OMNIAKEY_VISION_TEXT_FALLBACK_MODELS
            if candidate and candidate != requested_model
        )

    last_error: RuntimeError | None = None
    for index, candidate_model in enumerate(candidate_models):
        record_omnia_model(candidate_model)
        record_omnia_provider_status("uncertain")
        try:
            response = requests.post(
                OMNIAKEY_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": candidate_model,
                    "messages": [{"role": "user", "content": content}],
                    "stream": False,
                },
                **get_external_request_kwargs(timeout=120, use_proxy=False),
            )
        except requests.RequestException as exc:
            raise ImageOutcomeUnknown(
                "OmniaKey 文字请求连接中断或等待超时，远端结果尚未确认，未自动重新提交。"
            ) from exc

        retry_delay = OMNIAKEY_MEDIA_RETRY_DELAYS[min(index, len(OMNIAKEY_MEDIA_RETRY_DELAYS) - 1)]
        if response.status_code == 429:
            get_request_limiter().cooldown("omnia_text", seconds=retry_delay)
        try:
            data = response.json()
        except Exception as exc:
            if response.status_code >= 500 or response.status_code < 400 or response.status_code == 408:
                raise ImageOutcomeUnknown(
                    f"OmniaKey 文字响应无法解析（HTTP {response.status_code}），远端结果尚未确认，未自动重新提交。"
                ) from exc
            record_omnia_provider_status("rejected")
            last_error = RuntimeError(f"OmniaKey 响应解析失败（HTTP {response.status_code}）。")
            should_fallback = response.status_code in {425, 429}
        else:
            if response.status_code < 400 and isinstance(data, dict) and data.get("choices"):
                return extract_response_payload(data)
            error_payload = data.get("error") if isinstance(data, dict) else data
            error_message = (
                error_payload.get("message") or "未提供具体错误信息"
                if isinstance(error_payload, dict)
                else error_payload or "未提供具体错误信息"
            )
            error_code = str(error_payload.get("code") or "").lower() if isinstance(error_payload, dict) else ""
            explicit_rejection = error_code in {
                "no_available_channel", "provider_submit_rejected", "model_not_found", "unsupported_model",
            } or any(marker in str(error_message).lower() for marker in ("no available channel", "no_available_channel"))
            if (response.status_code >= 500 or response.status_code == 408) and not explicit_rejection:
                raise ImageOutcomeUnknown(
                    f"OmniaKey 文字请求返回 HTTP {response.status_code}，远端结果尚未确认，未自动重新提交。"
                )
            record_omnia_provider_status("rejected" if explicit_rejection or 400 <= response.status_code < 500 else "failed")
            last_error = RuntimeError(
                f"OmniaKey 请求失败（HTTP {response.status_code}）：{redact_background_error_text(error_message)}"
            )
            # Only an explicit rejection can safely choose another model.
            should_fallback = response.status_code in {425, 429} or explicit_rejection
        if not should_fallback or index + 1 >= len(candidate_models):
            break
        if response.status_code == 429:
            time.sleep(retry_delay)

    raise last_error or RuntimeError("OmniaKey 未返回可用的视觉分析结果。")


def call_openrouter(
    model,
    prompt,
    uploaded_files,
    output_mode,
    aspect_ratio,
    image_size,
    *,
    call_omnia_chat_api,
    call_openrouter_images_api,
    enforce_global_no_distortion_rules,
) -> dict[str, Any]:
    request_prompt = (
        enforce_global_no_distortion_rules(prompt)
        if output_mode == "image"
        else str(prompt or "").strip()
    )
    if output_mode == "image":
        return call_openrouter_images_api(
            model=model,
            prompt=request_prompt,
            uploaded_files=list(uploaded_files or []),
            aspect_ratio=aspect_ratio,
            resolution=image_size,
        )
    return call_omnia_chat_api(
        model=model,
        prompt=request_prompt,
        uploaded_files=list(uploaded_files or []),
    )
