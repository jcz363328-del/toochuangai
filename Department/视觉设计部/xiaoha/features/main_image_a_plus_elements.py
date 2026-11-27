"""Analyze, select and replace individual A+ image elements."""

from __future__ import annotations

from typing import Any


def parse_main_image_a_plus_element_analysis(
    response_text,
    image_size,
    *,
    Any,
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
    json,
    normalize_main_image_a_plus_element_bbox,
    re,
) -> list[dict[str, Any]]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError("元素识别没有返回结果，请重试。")
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    list_start, list_end = raw_text.find("["), raw_text.rfind("]")
    if list_start >= 0 and list_end > list_start:
        candidates.append(raw_text[list_start : list_end + 1])
    payload: Any = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            break
        except Exception:
            continue
    if payload is None:
        raise RuntimeError("元素识别结果格式不完整，请重新识别。")
    raw_elements = payload.get("elements") if isinstance(payload, dict) else payload
    if not isinstance(raw_elements, list):
        raise RuntimeError("元素识别结果中没有可用的元素列表，请重新识别。")
    elements: list[dict[str, Any]] = []
    for raw_element in raw_elements:
        if not isinstance(raw_element, dict):
            continue
        raw_regions = (
            raw_element.get("regions")
            or raw_element.get("boxes")
            or raw_element.get("bboxes")
            or raw_element.get("bbox")
            or []
        )
        if isinstance(raw_regions, dict) or (
            isinstance(raw_regions, (list, tuple))
            and len(raw_regions) >= 4
            and not isinstance(raw_regions[0], (list, tuple, dict))
        ):
            raw_regions = [raw_regions]
        regions = [
            bbox
            for bbox in (
                normalize_main_image_a_plus_element_bbox(raw_bbox, image_size)
                for raw_bbox in list(raw_regions or [])
            )
            if bbox is not None
        ]
        if not regions:
            continue
        element_name = str(
            raw_element.get("name")
            or raw_element.get("label")
            or raw_element.get("type")
            or "可替换元素"
        ).strip()[:48]
        element_type = str(raw_element.get("type") or "other").strip().lower()[:32]
        description = str(raw_element.get("description") or "").strip()[:240]
        replacement_hint = str(
            raw_element.get("replacement_hint")
            or raw_element.get("hint")
            or description
        ).strip()[:240]
        elements.append(
            {
                "id": len(elements) + 1,
                "name": element_name or f"可替换元素 {len(elements) + 1}",
                "type": element_type or "other",
                "description": description,
                "replacement_hint": replacement_hint,
                "regions": regions,
            }
        )
        if len(elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
            break
    if not elements:
        raise RuntimeError("没有识别到可替换元素，请确认上传的是完整 A+ 成品图后重试。")
    return elements


def parse_main_image_a_plus_replacement_matches(
    response_text,
    elements,
    replacement_count,
    replacement_sizes,
    *,
    Any,
    json,
    normalize_main_image_a_plus_element_bbox,
    re,
) -> list[dict[str, Any]]:
    raw_text = str(response_text or "").strip()
    if not raw_text:
        raise RuntimeError("替换素材识别没有返回结果，请重试。")
    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text, re.IGNORECASE)
    if fenced_match:
        candidates.insert(0, fenced_match.group(1).strip())
    object_start, object_end = raw_text.find("{"), raw_text.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw_text[object_start : object_end + 1])
    payload: Any = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            break
        except Exception:
            continue
    if payload is None:
        raise RuntimeError("替换素材识别结果格式不完整，请重新识别。")
    raw_matches = payload.get("matches") if isinstance(payload, dict) else payload
    if not isinstance(raw_matches, list):
        raise RuntimeError("替换素材识别结果中没有匹配清单，请重新识别。")
    valid_element_ids = {
        int(element.get("id") or index + 1)
        for index, element in enumerate(elements)
    }
    best_matches: dict[int, dict[str, Any]] = {}
    for raw_match in raw_matches:
        if not isinstance(raw_match, dict):
            continue
        try:
            element_id = int(raw_match.get("element_id") or raw_match.get("id") or 0)
            image_index = int(raw_match.get("image_index") or raw_match.get("reference_index") or 0)
        except (TypeError, ValueError):
            continue
        if element_id not in valid_element_ids or image_index < 1 or image_index > replacement_count:
            continue
        try:
            confidence = float(raw_match.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence > 1.0:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))
        replacement_size = (
            replacement_sizes[image_index - 1]
            if replacement_sizes and image_index <= len(replacement_sizes)
            else (1000, 1000)
        )
        raw_crop_box = (
            raw_match.get("crop_box")
            or raw_match.get("source_region")
            or raw_match.get("bbox")
            or raw_match.get("region")
        )
        crop_box = normalize_main_image_a_plus_element_bbox(
            raw_crop_box,
            replacement_size,
        )
        normalized_match = {
            "element_id": element_id,
            "image_index": image_index,
            "confidence": confidence,
            "crop_box": crop_box or [],
            "reason": str(raw_match.get("reason") or "").strip()[:240],
            "detected_content": str(
                raw_match.get("detected_content") or raw_match.get("content") or ""
            ).strip()[:160],
        }
        current_match = best_matches.get(element_id)
        if current_match is None or confidence > float(current_match.get("confidence") or 0):
            best_matches[element_id] = normalized_match
    return [best_matches[element_id] for element_id in sorted(best_matches)]


def analyze_main_image_a_plus_replacement_matches(
    template_input,
    elements,
    replacement_inputs,
    *,
    DEFAULT_ASPECT_RATIO,
    MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
    call_openrouter,
    get_uploaded_input_dimensions,
    parse_main_image_a_plus_replacement_matches,
) -> list[dict[str, Any]]:
    if template_input is None or not elements:
        raise RuntimeError("请先上传 A+ 模板并完成元素识别。")
    if not replacement_inputs:
        raise RuntimeError("请先上传至少 1 张用于替换的新素材图。")
    element_summary = "\n".join(
        (
            f"#{int(element.get('id') or index + 1)}｜名称：{str(element.get('name') or '元素')}｜"
            f"类型：{str(element.get('type') or 'other')}｜说明："
            f"{str(element.get('description') or element.get('replacement_hint') or '')}"
        )
        for index, element in enumerate(elements)
    )
    prompt = (
        "你是电商 A+ 替换素材匹配器。输入图片第 1 张是带有待替换元素的完整 A+ 模板，"
        "从输入图片第 2 张开始依次是用户上传的新素材图；返回 JSON 中的 image_index 从 1 开始，"
        "其中 image_index=1 对应输入图片第 2 张。请识别每张新素材里真实存在的人物、产品、包装、"
        "品牌 Logo、文字、参数、效果图和细节，并把它匹配到下面最合适的模板编号。"
        "一张素材同时包含多类有效内容时可以匹配多个编号；一个编号只能选择最合适的一张素材。"
        "每条匹配必须同时返回 crop_box，表示该替换元素在对应新素材图中的紧致范围，坐标使用 0 到 1000 的"
        "归一化整数 [left,top,right,bottom]；crop_box 只能框住真正要替换的产品、人物、Logo、文字或细节，"
        "尽量排除无关背景、其他商品、其他人物和整张海报。若一张素材匹配多个编号，必须为每个编号分别给出"
        "各自的 crop_box。无法准确定位替换部分时不要返回该匹配，禁止用整张图片范围代替。"
        "不要因为颜色相似就误配，不能识别清楚的编号不要返回。只返回严格 JSON，不要 Markdown。\n\n"
        f"模板元素清单：\n{element_summary}\n\n"
        "JSON 格式：{\"matches\":[{\"element_id\":1,\"image_index\":2,"
        "\"confidence\":0.92,\"detected_content\":\"白色假睫毛包装盒\","
        "\"crop_box\":[120,180,860,790],"
        "\"reason\":\"素材中的包装对应模板产品包装槽位\"}]}"
    )
    response = call_openrouter(
        model=MAIN_IMAGE_A_PLUS_ELEMENT_ANALYSIS_MODEL,
        prompt=prompt,
        uploaded_files=[template_input, *replacement_inputs],
        output_mode="text",
        aspect_ratio=DEFAULT_ASPECT_RATIO,
    )
    return parse_main_image_a_plus_replacement_matches(
        str(response.get("text") or ""),
        elements,
        len(replacement_inputs),
        [get_uploaded_input_dimensions(item) for item in replacement_inputs],
    )


def render_main_image_a_plus_text_edit_picker(
    source_image,
    source_signature,
    selected_point,
    component_key,
    *,
    MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY,
    json,
    re,
    st,
) -> None:
    safe_component_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(component_key or "text_picker"))
    source_json = json.dumps(str(source_image or ""), ensure_ascii=False)
    signature_json = json.dumps(str(source_signature or ""), ensure_ascii=False)
    query_key_json = json.dumps(MAIN_IMAGE_A_PLUS_TEXT_POINT_QUERY_KEY)
    selected_x = int(selected_point[0]) if selected_point is not None else -1
    selected_y = int(selected_point[1]) if selected_point is not None else -1
    html_content = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{ margin: 0; padding: 0; background: transparent; color: #eef3ff; font-family: Arial, sans-serif; }}
        .text-picker-shell {{ height: 640px; overflow: auto; border-radius: 14px; border: 1px solid rgba(139, 156, 255, .26); background: rgba(5, 12, 27, .72); }}
        .text-picker-tip {{ position: sticky; top: 0; z-index: 4; padding: 10px 12px; background: rgba(9, 18, 39, .94); color: #dfe6ff; font-size: 13px; line-height: 1.5; border-bottom: 1px solid rgba(139, 156, 255, .18); }}
        .text-picker-wrap {{ display: flex; justify-content: center; padding: 12px; }}
        .text-picker-stage {{ position: relative; display: inline-block; line-height: 0; }}
        .text-picker-image {{ display: block; width: min(100%, 760px); height: auto; cursor: crosshair; border-radius: 8px; user-select: none; -webkit-user-drag: none; }}
        .text-picker-image:hover {{ box-shadow: 0 0 0 2px rgba(126, 96, 255, .85); }}
        .text-picker-marker {{ position: absolute; width: 22px; height: 22px; margin: -11px 0 0 -11px; border: 3px solid #fff; border-radius: 50%; background: #ff4d67; box-shadow: 0 0 0 3px rgba(255,77,103,.35); pointer-events: none; display: none; }}
        .text-picker-loading {{ position: fixed; inset: 0; display: none; align-items: center; justify-content: center; background: rgba(3, 8, 22, .72); z-index: 6; font-weight: 700; }}
      </style>
    </head>
    <body>
      <div class="text-picker-shell">
        <div class="text-picker-tip" id="text-picker-tip-{safe_component_key}">点击成品图中需要修改的文字笔画或文字块中心；红点表示当前选中的位置。</div>
        <div class="text-picker-wrap">
          <div class="text-picker-stage">
            <img class="text-picker-image" id="text-picker-image-{safe_component_key}" alt="点击选择文字" />
            <span class="text-picker-marker" id="text-picker-marker-{safe_component_key}"></span>
          </div>
        </div>
      </div>
      <div class="text-picker-loading" id="text-picker-loading-{safe_component_key}">正在记录文字位置…</div>
      <script>
        (() => {{
          const image = document.getElementById("text-picker-image-{safe_component_key}");
          const marker = document.getElementById("text-picker-marker-{safe_component_key}");
          const loading = document.getElementById("text-picker-loading-{safe_component_key}");
          const hostWindow = window.parent;
          const selectedX = {selected_x};
          const selectedY = {selected_y};
          image.src = {source_json};
          image.addEventListener("load", () => {{
            if (selectedX >= 0 && selectedY >= 0) {{
              marker.style.left = `${{selectedX / 10}}%`;
              marker.style.top = `${{selectedY / 10}}%`;
              marker.style.display = "block";
            }}
          }});
          image.addEventListener("click", (event) => {{
            const rect = image.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const x = Math.max(0, Math.min(1000, Math.round((event.clientX - rect.left) / rect.width * 1000)));
            const y = Math.max(0, Math.min(1000, Math.round((event.clientY - rect.top) / rect.height * 1000)));
            const payload = JSON.stringify({{
              source_signature: {signature_json},
              x,
              y
            }});
            const nextUrl = new URL(hostWindow.location.href);
            nextUrl.searchParams.set({query_key_json}, payload);
            loading.style.display = "flex";
            hostWindow.location.assign(nextUrl.toString());
          }});
        }})();
      </script>
    </body>
    </html>
    """
    st.iframe(html_content, height=660, width="stretch")


def detect_main_image_a_plus_outer_blank_borders(
    candidate_bytes,
    *,
    Image,
    ImageOps,
    ImageStat,
    io,
) -> list[str]:
    """Detect accidental near-white/black bands around an otherwise full-bleed design."""
    try:
        with Image.open(io.BytesIO(candidate_bytes)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            if max(image.size) > 1200:
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            width, height = image.size
            if width < 80 or height < 80:
                return []
            sample_thickness = max(2, min(12, round(min(width, height) * 0.008)))
            x_padding = max(2, round(width * 0.06))
            y_padding = max(2, round(height * 0.06))
            side_boxes = {
                "左侧": (
                    (0, y_padding, sample_thickness, height - y_padding),
                    (
                        sample_thickness * 3,
                        y_padding,
                        sample_thickness * 5,
                        height - y_padding,
                    ),
                ),
                "右侧": (
                    (
                        width - sample_thickness,
                        y_padding,
                        width,
                        height - y_padding,
                    ),
                    (
                        width - sample_thickness * 5,
                        y_padding,
                        width - sample_thickness * 3,
                        height - y_padding,
                    ),
                ),
                "顶部": (
                    (x_padding, 0, width - x_padding, sample_thickness),
                    (
                        x_padding,
                        sample_thickness * 3,
                        width - x_padding,
                        sample_thickness * 5,
                    ),
                ),
                "底部": (
                    (
                        x_padding,
                        height - sample_thickness,
                        width - x_padding,
                        height,
                    ),
                    (
                        x_padding,
                        height - sample_thickness * 5,
                        width - x_padding,
                        height - sample_thickness * 3,
                    ),
                ),
            }
            issues: list[str] = []
            for side_name, (outer_box, inner_box) in side_boxes.items():
                outer_stat = ImageStat.Stat(image.crop(outer_box))
                inner_stat = ImageStat.Stat(image.crop(inner_box))
                outer_mean = [float(value) for value in outer_stat.mean[:3]]
                outer_stddev = [float(value) for value in outer_stat.stddev[:3]]
                inner_mean = [float(value) for value in inner_stat.mean[:3]]
                is_neutral = max(outer_mean) - min(outer_mean) <= 18.0
                is_blank_tone = min(outer_mean) >= 240.0 or max(outer_mean) <= 20.0
                is_uniform = max(outer_stddev) <= 10.0
                color_change = sum(
                    abs(outer_value - inner_value)
                    for outer_value, inner_value in zip(outer_mean, inner_mean)
                ) / 3.0
                if is_neutral and is_blank_tone and is_uniform and color_change >= 12.0:
                    issues.append(f"{side_name}存在连续空白边带，背景没有满版铺到画布边缘")
            return issues
    except Exception:
        return []


def submit_main_image_a_plus_manual_element_job(
    job_state_key,
    template_input,
    template_signature,
    point,
    existing_elements,
    *,
    clear_task_progress,
    datetime,
    format_user_facing_error_message,
    get_request_limiter,
    get_task_runtime,
    prepare_uploaded_input,
    run_main_image_a_plus_manual_element_job,
    set_task_progress,
    st,
) -> dict[str, Any]:
    current_state = dict(st.session_state.get(job_state_key) or {})
    if str(current_state.get("status") or "").lower() in {"queued", "running"}:
        return current_state
    runtime = get_task_runtime()
    account = str(st.session_state.get("auth_username") or "admin").strip() or "admin"
    job_id = f"a_plus_manual_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    job_state = {
        "job_id": job_id,
        "status": "queued",
        "template_signature": str(template_signature or ""),
        "point": tuple(point),
        "progress": 1,
        "stage": "点击补漏已加入账号队列",
        "error": "",
    }
    try:
        get_request_limiter().ensure_accepting()
        set_task_progress(job_id, 1, "点击补漏已加入账号队列")
        runtime.submit_generation_job(
            account,
            job_id,
            run_main_image_a_plus_manual_element_job,
            prepare_uploaded_input(template_input),
            tuple(point),
            [dict(element) for element in existing_elements],
            job_id,
        )
    except Exception as exc:
        clear_task_progress(job_id)
        job_state.update(status="error", progress=0, error=format_user_facing_error_message(exc))
    else:
        queue_state = runtime.get_generation_queue_state(job_id)
        if queue_state.get("state") in {"running", "completed"}:
            job_state.update(status="running", progress=5, stage="正在识别点击位置")
    st.session_state[job_state_key] = job_state
    return job_state


def sync_main_image_a_plus_manual_element_job(
    job_state_key,
    analysis_state_key,
    template_signature,
    *,
    MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS,
    calculate_smooth_running_progress,
    clear_task_progress,
    format_user_facing_error_message,
    get_task_progress,
    get_task_runtime,
    st,
) -> dict[str, Any]:
    job_state = dict(st.session_state.get(job_state_key) or {})
    if str(job_state.get("status") or "").lower() not in {"queued", "running"}:
        return job_state
    job_id = str(job_state.get("job_id") or "")
    runtime = get_task_runtime()
    with runtime.lock:
        future = runtime.futures.get(job_id)
    queue_state = runtime.get_generation_queue_state(job_id)
    if queue_state.get("state") == "queued":
        ahead = int(queue_state.get("ahead_count") or 0)
        job_state.update(
            status="queued", progress=1,
            stage=f"点击补漏排队中，当前账号前面还有 {ahead} 个任务" if ahead else "点击补漏排队中，等待可用执行名额",
        )
        st.session_state[job_state_key] = job_state
        return job_state
    if queue_state.get("state") == "running":
        job_state["status"] = "running"
    progress_info = get_task_progress(job_id)
    if progress_info:
        job_state["progress"] = calculate_smooth_running_progress(
            int(job_state.get("progress") or 5),
            int(progress_info.get("percent") or 5),
        )
        job_state["stage"] = str(progress_info.get("stage") or job_state.get("stage") or "正在识别")
    if future is None:
        job_state.update(
            {
                "status": "error",
                "error": "补漏识别任务状态已丢失，远端结果尚未确认，未自动重新提交。",
                "progress": 0,
            }
        )
    elif future.done():
        try:
            if future.cancelled():
                raise RuntimeError("点击补漏任务在排队时已取消，未向模型提交。")
            new_element = dict(future.result())
            analysis_state = dict(st.session_state.get(analysis_state_key) or {})
            if str(analysis_state.get("template_signature") or "") != str(template_signature or ""):
                raise RuntimeError("模板已经变化，请在当前模板上重新点击。")
            current_elements = [
                dict(item)
                for item in list(analysis_state.get("elements") or [])
                if isinstance(item, dict)
            ]
            if len(current_elements) >= MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS:
                raise RuntimeError(f"当前最多支持 {MAIN_IMAGE_A_PLUS_MAX_ELEMENT_GROUPS} 个元素组。")
            new_element["id"] = max(
                [int(element.get("id") or 0) for element in current_elements] or [0]
            ) + 1
            current_elements.append(new_element)
            st.session_state[analysis_state_key] = {
                "template_signature": template_signature,
                "elements": current_elements,
                "error": "",
            }
            job_state.update(
                {
                    "status": "completed",
                    "progress": 100,
                    "stage": "补漏识别完成",
                    "new_element": new_element,
                    "error": "",
                }
            )
        except Exception as exc:
            job_state.update(
                {
                    "status": "error",
                    "progress": 0,
                    "error": format_user_facing_error_message(exc),
                }
            )
        runtime.release_generation_job(job_id)
        clear_task_progress(job_id)
    st.session_state[job_state_key] = job_state
    return job_state


def render_main_image_a_plus_manual_element_job_status(
    job_state_key,
    analysis_state_key,
    template_signature,
    *,
    build_running_job_spinner_html,
    st,
    sync_main_image_a_plus_manual_element_job,
) -> None:
    job_state = sync_main_image_a_plus_manual_element_job(
        job_state_key,
        analysis_state_key,
        template_signature,
    )
    if str(job_state.get("status") or "").lower() == "queued":
        st.info(str(job_state.get("stage") or "点击补漏排队中"))
        return
    if str(job_state.get("status") or "").lower() == "running":
        st.markdown(
            build_running_job_spinner_html(
                int(job_state.get("progress") or 5),
                str(job_state.get("stage") or "正在识别点击位置"),
            ),
            unsafe_allow_html=True,
        )
        return
    st.rerun()
