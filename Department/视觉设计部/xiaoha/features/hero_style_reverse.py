"""A+ hero image style analysis, generation and history."""

from __future__ import annotations

from typing import Any


def parse_hero_style_reverse_analysis(
    response_text,
    *,
    Any,
    HERO_STYLE_REVERSE_FIELD_LABELS,
    json,
    re,
) -> dict[str, str]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError("参考图分析没有返回结果，请重试。")
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    parsed: dict[str, Any] | None = None
    for candidate in candidates:
        try:
            loaded = json.loads(candidate)
        except Exception:
            continue
        if isinstance(loaded, dict):
            parsed = loaded
            break
    analysis: dict[str, str] = {}
    for field_key, _label in HERO_STYLE_REVERSE_FIELD_LABELS:
        value = parsed.get(field_key) if parsed else ""
        if isinstance(value, (list, tuple)):
            value = "；".join(str(item).strip() for item in value if str(item).strip())
        analysis[field_key] = str(value or "").strip()
    prompt_text = str(parsed.get("prompt") or "").strip() if parsed else raw_text
    if not prompt_text:
        raise RuntimeError("参考图分析结果里没有可用的提示词，请重试。")
    analysis["prompt"] = prompt_text
    return analysis


def analyze_hero_style_reverse_reference(
    uploaded_input,
    extra_requirements,
    *,
    DEFAULT_ASPECT_RATIO,
    IMAGE_SMART_ANALYSIS_MODEL,
    build_hero_style_reverse_analysis_prompt,
    call_openrouter,
    parse_hero_style_reverse_analysis,
) -> dict[str, str]:
    response = call_openrouter(
        model=IMAGE_SMART_ANALYSIS_MODEL,
        prompt=build_hero_style_reverse_analysis_prompt(extra_requirements),
        uploaded_files=[uploaded_input],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    return parse_hero_style_reverse_analysis(str(response.get("text") or ""))


def optimize_hero_style_reverse_prompt(
    prompt_text,
    analysis,
    extra_requirements,
    *,
    DEFAULT_ASPECT_RATIO,
    HERO_STYLE_REVERSE_FIELD_LABELS,
    IMAGE_SMART_ANALYSIS_MODEL,
    call_openrouter,
    re,
) -> str:
    """对提示词做专业化扩写与补充，只返回优化后的提示词正文。"""
    base_prompt = str(prompt_text or "").strip()
    if not base_prompt:
        raise RuntimeError("请先生成或填写提示词。")
    breakdown = "；".join(
        f"{label}：{str((analysis or {}).get(field_key) or '').strip()}"
        for field_key, label in HERO_STYLE_REVERSE_FIELD_LABELS
        if str((analysis or {}).get(field_key) or "").strip()
    )
    instruction = (
        "你是电商 A+ 生图提示词优化师。请在保留原意的前提下，把下面这条中文提示词改写得专业、具体、可直接执行。"
        "需要补充：镜头焦段与视角、景别与构图比例、主体位置与留白、主光与补光方向、色温与色彩关系、"
        "材质与纹理、质感与氛围、画面比例和输出用途；删除空泛形容词、重复表述和互相冲突的要求。"
        "只输出优化后的提示词正文，不要解释、不要编号、不要加引号或 Markdown。\n"
        + (f"参考图拆解：{breakdown}\n" if breakdown else "")
        + (f"用户补充要求：{str(extra_requirements or '').strip()}\n" if str(extra_requirements or "").strip() else "")
        + f"原始提示词：{base_prompt}"
    )
    response = call_openrouter(
        model=IMAGE_SMART_ANALYSIS_MODEL,
        prompt=instruction,
        uploaded_files=[],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    optimized = str(response.get("text") or "").strip()
    fenced_match = re.search(r"```(?:[a-zA-Z]*)?\s*([\s\S]*?)```", optimized, re.IGNORECASE)
    if fenced_match:
        optimized = fenced_match.group(1).strip()
    optimized = optimized.strip().strip('"').strip("“”").strip()
    return optimized or base_prompt


def build_hero_style_reverse_image_input(
    image_source,
    *,
    get_external_request_kwargs,
    get_request_limiter,
    requests,
) -> dict[str, Any] | None:
    """把上一版结果图（URL）取回为可继续提交的输入图。"""
    normalized_source = str(image_source or "").strip()
    if not normalized_source.startswith(("http://", "https://")):
        return None
    try:
        with get_request_limiter().slot("download"):
            response = requests.get(
                normalized_source,
                **get_external_request_kwargs(timeout=(15, 90)),
            )
    except Exception:
        return None
    if not getattr(response, "ok", False):
        return None
    image_bytes = response.content or b""
    if not image_bytes:
        return None
    return {
        "data": image_bytes,
        "name": "hero_style_reverse_parent.png",
        "type": "image/png",
    }


def generate_hero_style_reverse_images(
    prompt_text,
    reference_files,
    count,
    aspect_ratio,
    progress_callback,
    *,
    NANO_BANANA_MODEL,
    call_openrouter_images_api,
) -> list[str]:
    """按提示词批量生成同风格图片，逐张返回结果 URL。"""
    cleaned_prompt = str(prompt_text or "").strip()
    if not cleaned_prompt:
        raise RuntimeError("请先填写生图提示词。")
    total = max(int(count or 1), 1)
    images: list[str] = []
    for index in range(total):
        result = call_openrouter_images_api(
            model=NANO_BANANA_MODEL,
            prompt=cleaned_prompt,
            uploaded_files=list(reference_files or []),
            aspect_ratio=aspect_ratio,
        )
        for image_url in result.get("images") or []:
            normalized_url = str(image_url or "").strip()
            if normalized_url:
                images.append(normalized_url)
        if callable(progress_callback):
            progress_callback(index + 1, total, len(images))
    if not images:
        raise RuntimeError("没有拿到可用图片，请调整提示词后重试。")
    return images


def hero_style_reverse_nearest_aspect_ratio(
    width,
    height,
    *,
    HERO_STYLE_REVERSE_ASPECT_OPTIONS,
) -> str:
    """按目标宽高选取最接近的可用画面比例。"""
    target_ratio = float(width) / float(height or 1)
    return min(
        (ratio for _label, ratio in HERO_STYLE_REVERSE_ASPECT_OPTIONS),
        key=lambda ratio: abs(
            float(ratio.split(":")[0]) / float(ratio.split(":")[1]) - target_ratio
        ),
    )


def resize_hero_style_reverse_output(
    image_source,
    target_width,
    target_height,
    *,
    Image,
    ImageOps,
    fit_image_to_canvas_without_distortion,
    image_bytes_to_data_url,
    io,
    load_image_bytes_from_url,
) -> str:
    """把结果图等比缩放到指定宽度；给出高度时适配到精确宽高画布。"""
    safe_width = max(int(target_width), 1)
    safe_height = max(int(target_height or 0), 1) if target_height else 0
    if safe_height and safe_width * safe_height > 64_000_000:
        raise RuntimeError("目标图片不能超过 6400 万像素，请调小宽度或高度。")
    image_bytes, _mime_type = load_image_bytes_from_url(image_source)
    with Image.open(io.BytesIO(image_bytes)) as image:
        source = ImageOps.exif_transpose(image).convert("RGB")
        if target_height:
            resized = fit_image_to_canvas_without_distortion(
                source,
                safe_width,
                max(int(target_height), 1),
            )
        else:
            proportional_height = max(1, int(round(source.height * safe_width / float(source.width))))
            resized = source.resize((safe_width, proportional_height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        resized.save(output, format="PNG")
    return image_bytes_to_data_url(output.getvalue(), "image/png")


def persist_hero_style_reverse_history(
    feature,
    images,
    prompt,
    model,
    *,
    NANO_BANANA_MODEL,
    build_local_history_records,
    get_history_cache_key,
    save_generated_images_and_record_db,
    st,
    store_local_history_records,
    sys,
) -> list[dict[str, Any]]:
    """Save reverse-engineering results through the shared history pipeline."""
    normalized_images = [str(image).strip() for image in list(images or []) if str(image).strip()]
    if not normalized_images:
        return []
    account_name = str(st.session_state.get("auth_username") or "admin").strip() or "admin"
    result = {"images": normalized_images}
    try:
        records = save_generated_images_and_record_db(
            feature=dict(feature),
            model=str(model or NANO_BANANA_MODEL),
            prompt=str(prompt or ""),
            result=result,
            account_name=account_name,
        )
    except Exception as exc:
        print(f"[hero-style-reverse-history] 数据库保存失败：{exc}", file=sys.stderr)
        records = build_local_history_records(
            feature=dict(feature),
            model=str(model or NANO_BANANA_MODEL),
            prompt=str(prompt or ""),
            result=result,
            account_name=account_name,
        )
    if records:
        store_local_history_records(account_name, str(feature.get("key") or ""), records)
        cache_key = get_history_cache_key(account_name, str(feature.get("key") or ""))
        st.session_state.history_records_cache.pop(cache_key, None)
    return records


def save_hero_reverse_draft(
    field,
    widget_key,
    *,
    st,
) -> None:
    state = st.session_state.setdefault("hero_style_reverse_state", {})
    value = st.session_state.get(widget_key)
    state.setdefault("draft", {})[field] = value
    if field == "prompt":
        state["prompt"] = str(value or "")


def submit_hero_reverse_job(
    feature,
    prompt,
    references,
    count,
    ratio,
    width,
    height,
    parent,
    parent_index,
    *,
    NANO_BANANA_MODEL,
    normalize_uploaded_input,
    st,
    submit_feature_job,
):
    state = st.session_state.setdefault("hero_style_reverse_state", {})
    state["prompt"] = str(st.session_state.get(
        f"hero_style_reverse_prompt_{feature['key']}") or state.get("prompt") or prompt)
    return submit_feature_job(feature, {
        "feature": dict(feature), "model": NANO_BANANA_MODEL,
        "prompt": prompt, "uploaded_files": [normalize_uploaded_input(f) for f in references],
        "output_mode": "image", "aspect_ratio": ratio,
        "max_output_images": 1,
        "account_name": str(st.session_state.get("auth_username") or "admin"),
        "hero_reverse_count": count, "hero_reverse_size": [width or 0, height or 0],
        "hero_reverse_parent": parent, "hero_reverse_parent_index": parent_index,
    })


def run_hero_reverse_job(
    context,
    *,
    datetime,
    generate_hero_style_reverse_images,
    resize_hero_style_reverse_output,
    set_task_progress,
):
    job_id = str(context.get("job_id") or "")
    def report(done, total, produced):
        if job_id:
            set_task_progress(job_id, 10 + int(65 * done / max(total, 1)),
                              f"已生成 {done}/{total} 张，共 {produced} 张结果")
    images = generate_hero_style_reverse_images(
        context["prompt"], context.get("uploaded_files") or [],
        context["hero_reverse_count"], context["aspect_ratio"], report,
    )
    width, height = context["hero_reverse_size"]
    if width:
        images = [resize_hero_style_reverse_output(url, width, height or None) for url in images]
    return {"images": images, "hero_reverse_batch": {
        "prompt": context["prompt"], "aspect_ratio": context["aspect_ratio"],
        "target_size": [width, height], "parent": context.get("hero_reverse_parent") or "",
        "parent_index": context.get("hero_reverse_parent_index"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }}
