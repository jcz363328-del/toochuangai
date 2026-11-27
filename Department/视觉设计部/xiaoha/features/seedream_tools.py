"""Official Seedream layer decomposition and spatial image editing workbenches."""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
from uuid import uuid4
import zipfile

from PIL import Image, ImageDraw, ImageOps

FEATURES = (
    ("seedream_layers", "图层分离", "将图片拆成底图和透明图层，保留层级与位置"),
    ("seedream_coordinate_edit", "精准坐标编辑", "点选、框选或输入坐标，指定图片编辑区域"),
    ("seedream_mark_edit", "任意标记编辑", "画箭头、框线、圈选和涂鸦，指示编辑对象"),
)
FEATURE_KEYS = tuple(item[0] for item in FEATURES)


def feature_definitions(model):
    return [dict(key=key, name=name, summary=summary, description=summary,
                 mode="seedream_tools", output_mode="image", model=model,
                 min_images=1, max_output_images=1, default_prompt="") for key, name, summary in FEATURES]


def validate_marks(value, *, coordinates=False):
    if not isinstance(value, list) or len(value) > 40:
        raise ValueError("最多添加 40 个标记。")
    clean = []
    total = 0
    for mark in value:
        if not isinstance(mark, dict):
            raise ValueError("标记格式无效。")
        kind = mark.get("type")
        allowed = {"point", "rect"} if coordinates else {"point", "rect", "arrow", "ellipse", "brush"}
        points = mark.get("points")
        if kind not in allowed or not isinstance(points, list) or not points or len(points) > 2000:
            raise ValueError("标记类型或点位无效。")
        if (kind == "point" and len(points) != 1) or (kind in {"rect", "arrow", "ellipse"} and len(points) != 2):
            raise ValueError("该标记的点位数量无效。")
        total += len(points)
        if total > 10000:
            raise ValueError("标记过于复杂，请减少笔画。")
        normalized = []
        for point in points:
            if not isinstance(point, (tuple, list)) or len(point) != 2:
                raise ValueError("标记坐标无效。")
            x, y = map(float, point)
            if not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 999 or not 0 <= y <= 999:
                raise ValueError("坐标应在 0–999 范围内。")
            normalized.append([round(x), round(y)])
        if kind in {"rect", "ellipse"}:
            (x1, y1), (x2, y2) = normalized
            normalized = [[min(x1, x2), min(y1, y2)], [max(x1, x2), max(y1, y2)]]
            if normalized[0][0] == normalized[1][0] or normalized[0][1] == normalized[1][1]:
                raise ValueError("框选区域宽度和高度不能为零。")
        clean.append({"type": kind, "points": normalized})
    return clean


def coordinate_token(mark, image_index=1):
    if mark["type"] == "point":
        return f"图{image_index}<point>{mark['points'][0][0]} {mark['points'][0][1]}</point>"
    values = [str(value) for point in mark["points"] for value in point]
    return f"图{image_index}<bbox>{' '.join(values)}</bbox>"


def compose_edit_prompt(mode, notes, marks, region_notes=None):
    notes = str(notes or "").strip()
    marks = validate_marks(marks, coordinates=mode == "seedream_coordinate_edit")
    if not notes:
        if marks and all(str((region_notes or {}).get(str(index), "")).strip() for index in range(len(marks))):
            notes = "按每个标记对应的编辑要求执行。"
        else:
            raise ValueError("请填写编辑要求，或为每个标记填写对应的区域要求。")
    if mode == "seedream_coordinate_edit":
        if not marks:
            raise ValueError("请先点选或框选编辑区域，也可以手动输入坐标。")
        lines = [f"区域 {i+1}：{coordinate_token(mark)}。{str((region_notes or {}).get(str(i), '')).strip()}" for i, mark in enumerate(marks)]
        return "\n".join(lines) + "\n编辑要求：" + notes + "\n仅修改上述指定区域，尽量保留其余内容、构图和比例。"
    if not marks:
        # Uploaded artwork may already carry hand-drawn annotations.
        return "根据图1上的已有手绘标记编辑图片。" + notes + "\n完成后移除所有用于定位的标记线条和编号，保留其余内容。"
    return ("图1是原图，图2是同一原图的红色标记版本，仅用于定位；图3及后续图片如有则为辅助参考。"
            "红色箭头的箭头端指向编辑对象，红框、圈选和笔画指定编辑区域，黄色编号与以下要求对应。\n"
            + "\n".join(f"标记 {i+1}：{str((region_notes or {}).get(str(i), '')).strip()}" for i in range(len(marks)))
            + "\n编辑要求：" + notes + "\n以图1为内容依据，仅修改指定对象；成品中移除标记、箭头、框线、笔画和编号。")


def annotated_input(raw, marks):
    marks = validate_marks(marks)
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    stroke = max(3, round(max(image.size) / 300))
    for index, mark in enumerate(marks):
        points = [(round(x / 1000 * width), round(y / 1000 * height)) for x, y in mark["points"]]
        kind = mark["type"]
        if kind == "rect":
            draw.rectangle((*points[0], *points[1]), outline="#ff3030", width=stroke)
        elif kind == "ellipse":
            draw.ellipse((*points[0], *points[1]), outline="#ff3030", width=stroke)
        elif kind in {"brush", "arrow"}:
            draw.line(points, fill="#ff3030", width=stroke, joint="curve")
            if kind == "arrow":
                start, end = points
                angle = math.atan2(end[1] - start[1], end[0] - start[0])
                length = stroke * 5
                head = [(end[0] - length * math.cos(angle + offset), end[1] - length * math.sin(angle + offset)) for offset in (-0.5, 0.5)]
                draw.polygon([end, *head], fill="#ff3030")
        else:
            x, y = points[0]
            draw.ellipse((x-stroke*2, y-stroke*2, x+stroke*2, y+stroke*2), fill="#ff3030")
        x, y = points[-1] if kind == "arrow" else points[0]
        x = min(max(x, 0), max(width - 35, 0))
        y = min(max(y, 0), max(height - 24, 0))
        draw.rectangle((x, y, x+30, y+20), fill="#ffe468")
        draw.text((x+5, y+3), str(index+1), fill="#111111")
    output = io.BytesIO()
    image.save(output, "PNG")
    return {"data": output.getvalue(), "name": "marked-reference.png", "type": "image/png"}


def result_directory(api, account):
    return api.ensure_feature_output_dir("seedream_tools") / hashlib.sha256(str(account).encode()).hexdigest()[:24]


def canonical_input(api, source):
    normalized = api.normalize_uploaded_input(source)
    with Image.open(io.BytesIO(normalized["data"])) as opened:
        image = ImageOps.exif_transpose(opened)
        if image.width * image.height > 36000000:
            raise ValueError("原图总像素不能超过 3600 万，请先缩小原图。")
        has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
        image = image.convert("RGBA" if has_alpha else "RGB")
        output = io.BytesIO()
        image.save(output, "PNG")
    return {"data": output.getvalue(), "name": "source.png", "type": "image/png"}


def persist_result(api, context, result):
    """Download expiring originals once; retain alpha and every positioning field."""
    folder = result_directory(api, context.get("account_name") or "admin") / uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    layers = list(result.get("layers") or [])
    if layers:
        if len(layers) > 17 or any("z_index" not in layer for layer in layers):
            raise ValueError("图层分离返回了无效的层级信息。")
        layers.sort(key=lambda layer: int(layer["z_index"]))
        indices = [int(layer["z_index"]) for layer in layers]
        if len(set(indices)) != len(indices) or min(indices) < 0 or max(indices) > 16:
            raise ValueError("图层层级重复或超出模型支持范围。")
        if int(layers[0]["z_index"]) != 0:
            raise ValueError("图层分离没有返回底图。")
    else:
        layers = [{"source": source, "z_index": i, "name": "编辑结果"} for i, source in enumerate(result.get("images") or [])]
    if not layers:
        raise RuntimeError("Seedream 未返回可保存的结果。")
    saved = []
    for index, layer in enumerate(layers):
        raw, _ = api.load_image_bytes_from_url(layer["source"])
        with Image.open(io.BytesIO(raw)) as image:
            extension = ".jpg" if image.format == "JPEG" else ".png"
            actual_size = image.size
        name = f"{index:02d}_{'base' if index == 0 and context['feature']['key'] == 'seedream_layers' else 'layer'}{extension}"
        path = folder / name
        path.write_bytes(raw)
        saved.append({key: value for key, value in layer.items() if key != "source"} | {"source": str(path), "file_name": name, "pixel_size": list(actual_size)})
    result.update(images=[layer["source"] for layer in saved], layers=saved if context["feature"]["key"] == "seedream_layers" else [],
                  seedream_mode=context["feature"]["key"], seedream_artifact_dir=str(folder),
                  seedream_notes=str(context.get("prompt") or ""))
    manifest = {"model": result.get("model"), "feature": context["feature"]["key"], "usage": result.get("usage", {}),
                "request_id": result.get("request_id", ""), "layers": [{k: v for k, v in layer.items() if k != "source"} for layer in saved]}
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if result.get("layers"):
        try:
            composite_layers(saved).save(folder / "composite.png", "PNG")
            result["composite_source"] = str(folder / "composite.png")
        except (ValueError, OSError) as exc:
            result["composite_error"] = str(exc)
    with zipfile.ZipFile(folder / "layers.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in folder.iterdir():
            if path.name != "layers.zip":
                archive.write(path, path.name)
    snapshot = {k: result[k] for k in ("images", "layers", "usage", "request_id", "model", "seedream_mode", "seedream_artifact_dir", "composite_source", "composite_error") if k in result}
    (folder / "result.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return result


def composite_layers(layers, visible=None):
    base = layers[0]
    with Image.open(base["source"]) as image:
        canvas = image.convert("RGBA")
    for layer in sorted(layers[1:], key=lambda item: int(item["z_index"])):
        if visible is not None and layer["z_index"] not in visible:
            continue
        box = (layer.get("bounding_box") or {}).get("absolute")
        if box is None:
            normalized = (layer.get("bounding_box") or {}).get("normalized")
            if normalized and len(normalized) == 4:
                box = [round(normalized[0]*canvas.width/1000), round(normalized[1]*canvas.height/1000), round(normalized[2]*canvas.width/1000), round(normalized[3]*canvas.height/1000)]
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError("图层缺少边界框，无法还原图层位置。")
        left, top, right, bottom = map(int, box)
        if right <= left or bottom <= top or max(right-left, bottom-top) > 16000:
            raise ValueError("图层边界框无效。")
        with Image.open(layer["source"]) as image:
            positioned = image.convert("RGBA").resize((right-left, bottom-top), Image.Resampling.LANCZOS)
        canvas.alpha_composite(positioned, (left, top))
    return canvas


def run_job(api, context):
    mode = context["feature"]["key"]
    if mode not in FEATURE_KEYS:
        raise ValueError("未知的 Seedream 操作。")
    files = [canonical_input(api, source) for source in list(context.get("uploaded_files") or [])]
    if not files:
        raise ValueError("请先上传原图。")
    options = dict(context.get("seedream_options") or {})
    marks = validate_marks(context.get("seedream_marks") or [], coordinates=mode == "seedream_coordinate_edit")
    if mode == "seedream_layers":
        prompt = str(context.get("prompt") or "").strip()
        if len(files) != 1:
            raise ValueError("图层分离需要且仅支持 1 张原图。")
    else:
        prompt = compose_edit_prompt(mode, context.get("prompt"), marks, context.get("seedream_region_notes"))
        if mode == "seedream_mark_edit" and marks:
            raw = api.normalize_uploaded_input(files[0])["data"]
            files = [files[0], annotated_input(raw, marks), *files[1:]]
    if len(files) > 10:
        raise ValueError("包含标记图在内，最多提交 10 张参考图。")
    result = api.call_ark_seedream_images_api(
        prompt, files, size=options.get("size", "2K"), layer_decomposition=mode == "seedream_layers",
        output_format=options.get("output_format", "png"), response_format=options.get("response_format", "url"),
        watermark=options.get("watermark", True), optimize_prompt_mode=options.get("optimize_prompt_mode", "standard"),
        background=options.get("background"), interactive_edit=True,
    )
    return persist_result(api, context, result)


def render_results(api, result, key):
    st = api.st
    if not result:
        st.info("处理完成后在这里查看结果。")
        return
    layers = result.get("layers") or []
    if layers:
        st.caption(f"底图 1 张 · 独立图层 {len(layers)-1} 张")
        visible = st.multiselect("合成预览中显示的图层", [layer["z_index"] for layer in layers[1:]],
                                 default=[layer["z_index"] for layer in layers[1:]],
                                 format_func=lambda z: next(str(layer.get("name") or f"图层 {z}") for layer in layers if layer["z_index"] == z),
                                 key=key+"_visible_"+Path(result["seedream_artifact_dir"]).name)
        with st.expander("图层合成预览", expanded=True):
            try:
                output = io.BytesIO()
                preview = composite_layers(layers, visible)
                preview.thumbnail((900, 900), Image.Resampling.LANCZOS)
                preview.save(output, "PNG")
                st.image(output.getvalue(), width="stretch")
            except (ValueError, OSError) as exc:
                st.warning(f"合成预览暂不可用，独立图层仍可下载：{exc}")
        st.dataframe([{"层级": layer["z_index"], "名称": layer.get("name") or ("底图" if layer["z_index"] == 0 else "图层"),
                       "说明": layer.get("description", ""), "尺寸": str(layer.get("size") or layer.get("pixel_size")),
                       "位置": str((layer.get("bounding_box") or {}).get("absolute", "整张画布"))} for layer in layers], hide_index=True, width="stretch")
    images = list(result.get("images") or [])
    if layers:
        previews = []
        for source in images:
            with Image.open(source) as image:
                thumb = image.convert("RGBA")
                thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)
            background = Image.new("RGB", thumb.size, "#eeeeee")
            draw = ImageDraw.Draw(background)
            for y in range(0, thumb.height, 16):
                for x in range(0, thumb.width, 16):
                    if (x//16 + y//16) % 2:
                        draw.rectangle((x, y, x+15, y+15), fill="#cccccc")
            background.paste(thumb, mask=thumb.getchannel("A"))
            output = io.BytesIO()
            background.save(output, "JPEG", quality=80)
            previews.append(api.image_bytes_to_data_url(output.getvalue(), "image/jpeg"))
        api.render_zoomable_image_gallery(previews, columns=3, thumb_height=180, component_key=key+"_layers",
                                          full_images=api.build_result_download_sources(images))
    else:
        api.render_result_preview(images, show_title=False, max_width_percent=100, feature_key=key)
    for index, source in enumerate(images):
        path = Path(source)
        if path.is_file():
            label = ("底图" if index == 0 else str(layers[index].get("name") or f"图层 {index}")) if layers else "编辑结果"
            st.download_button("下载 " + label, data=lambda p=path: p.read_bytes(), file_name=path.name,
                               key=f"{key}_download_{index}_{path.parent.name}")
    folder = Path(result["seedream_artifact_dir"])
    if (folder / "layers.zip").is_file():
        st.download_button("下载全部结果与图层位置 ZIP", data=lambda: (folder/"layers.zip").read_bytes(),
                           file_name="seedream_layers.zip", mime="application/zip", key=key+"_zip_"+folder.name)
    with st.expander("任务详情与用量"):
        st.json({"模型": result.get("model"), "请求编号": result.get("request_id"), "用量": result.get("usage", {})})


def render(api, feature):
    st = api.st
    key = feature["key"]
    is_layers = key == "seedream_layers"
    api.sync_background_jobs()
    api.render_image_workbench_header(feature, "Seedream 5 Pro · 字节官方")
    st.caption(feature["description"])
    left, right = st.columns([1, 1], gap="large")
    with left:
        source = api.render_single_image_uploader("原图", key+"_source")
        marks = []
        region_notes = {}
        if source is not None and not is_layers:
            import streamlit.components.v1 as components
            editor = components.declare_component("seedream_spatial_editor", path=str(Path(__file__).with_name("seedream_editor")))
            try:
                raw = canonical_input(api, source)["data"]
            except (ValueError, OSError) as exc:
                st.error(str(exc))
                return
            signature = hashlib.sha256(raw).hexdigest()[:16]
            preview = api.build_gallery_preview_data_url(raw, "image/png")
            if preview:
                editor_key = key+"_editor_"+signature
                value = editor(image=preview[0], mode="coordinates" if key == "seedream_coordinate_edit" else "marks",
                               signature=signature, initial_marks=(st.session_state.get(editor_key) or {}).get("marks", []),
                               key=editor_key, default={"marks": []})
                try:
                    marks = validate_marks((value or {}).get("marks") or [], coordinates=key == "seedream_coordinate_edit")
                except ValueError as exc:
                    st.error(str(exc))
            if key == "seedream_coordinate_edit":
                with st.expander("手动输入坐标"):
                    coordinate_type = st.selectbox("坐标类型", ["框选", "点选"], key=key+"_kind")
                    limit = 4 if coordinate_type == "框选" else 2
                    values = [st.number_input(label, min_value=0, max_value=999, value=default, step=1, key=f"{key}_{signature}_coord_{i}")
                              for i, (label, default) in enumerate(zip(("X1", "Y1", "X2", "Y2"), (100, 100, 600, 600))) if i < limit]
                    use_manual = st.checkbox("使用以上坐标代替画布选择", key=key+"_manual")
                    if use_manual:
                        marks = [{"type": "rect" if limit == 4 else "point", "points": [values[:2]] + ([values[2:]] if limit == 4 else [])}]
            if marks:
                st.caption(f"已保存 {len(marks)} 个标记，画布修改会自动保存。")
                with st.expander("为每个区域填写要求", expanded=len(marks) <= 3):
                    for index, mark in enumerate(marks):
                        token = coordinate_token(mark) if key == "seedream_coordinate_edit" else f"标记 {index+1}"
                        region_notes[str(index)] = st.text_input(token, key=f"{key}_{signature}_region_{index}")
            elif key == "seedream_mark_edit":
                st.caption("也可上传已画好标记的图片，直接在下方描述各标记的编辑要求。")
        notes = st.text_area("拆分要求（可留空自动识别）" if is_layers else "编辑要求", key=key+"_prompt",
                             placeholder="例如：将商品、标题、装饰元素分别拆成独立图层" if is_layers else "例如：把框选区域的背景换成浅蓝色，保留商品与文字", height=140,
                             help=None if is_layers else "已为每个标记填写区域要求时，这里的整体编辑要求可以留空。")
        references = []
        if not is_layers:
            with st.expander("添加辅助参考图"):
                references = api.render_multi_image_uploader("辅助参考图", key+"_refs", max_files=8 if key == "seedream_mark_edit" else 9, preview_slot_count=3)
        with st.expander("输出设置", expanded=True):
            sizes = ["auto", "1K", "1.5K", "2K"] if is_layers else ["1K", "1.5K", "2K"]
            size = st.selectbox("分辨率", sizes, index=0 if is_layers else 2, format_func=lambda value: "自动（按原图比例适配）" if value == "auto" else value, key=key+"_size")
            output_format = st.selectbox("底图格式" if is_layers else "输出格式", ["png", "jpeg"], key=key+"_format")
            optimize = st.selectbox("生成模式", ["standard", "fast"], format_func=lambda value: "标准（质量优先）" if value == "standard" else "快速（速度优先）", key=key+"_speed")
            watermark = st.checkbox("添加 AI 生成水印", value=True, key=key+"_watermark")
            response_format = st.selectbox("图片返回方式", ["url", "b64_json"], format_func=lambda value: "下载链接（自动保存）" if value == "url" else "直接返回图片数据", key=key+"_response")
            transparent = False
            if key == "seedream_coordinate_edit" and source is not None and not references and output_format == "png":
                with Image.open(io.BytesIO(api.normalize_uploaded_input(source)["data"])) as opened:
                    has_alpha = opened.mode in {"RGBA", "LA"} or "transparency" in opened.info
                if has_alpha:
                    transparent = st.checkbox("保留透明背景", value=False, key=key+"_transparent")
        busy = (st.session_state.get("background_jobs", {}).get(key) or {}).get("status") in {"queued", "running"}
        with st.container(key="workbench_action_dock", border=True):
            action_feedback = st.empty()
            if busy:
                st.caption("任务已提交，正在排队或处理，可以切换页面。")
            submitted = st.button("开始拆分图层" if is_layers else "开始编辑", type="primary", disabled=busy or source is None, key=key+"_submit", use_container_width=True)
        if submitted:
            try:
                if not is_layers:
                    compose_edit_prompt(key, notes, marks, region_notes)
                api.submit_feature_job(feature, {"feature": dict(feature), "model": api.ARK_SEEDREAM_5_PRO_MODEL,
                    "output_mode": "image", "max_output_images": 1, "prompt": notes,
                    "uploaded_files": [api.prepare_uploaded_input(source), *[api.prepare_uploaded_input(ref) for ref in references]],
                    "seedream_marks": marks, "seedream_region_notes": region_notes,
                    "seedream_options": {"size": size, "output_format": output_format, "optimize_prompt_mode": optimize,
                                         "watermark": watermark, "response_format": response_format,
                                         "background": "transparent" if transparent else None},
                    "generation_settings": {"model": api.ARK_SEEDREAM_5_PRO_MODEL, "resolution": "2K" if size == "auto" else size},
                    "account_name": str(st.session_state.get("auth_username") or "admin")})
                st.rerun()
            except Exception as exc:
                action_feedback.error(getattr(api, "format_user_facing_error_message", str)(exc))
    with right:
        st.markdown("**处理结果**")
        if busy:
            api.render_running_job_status(key, in_result=True)
        else:
            job = st.session_state.get("background_jobs", {}).get(key) or {}
            if job.get("status") == "error":
                st.error(str(job.get("error") or "处理失败，请查看任务详情。"))
            result = st.session_state.get("feature_results", {}).get(key) or {}
            folder = result_directory(api, st.session_state.get("auth_username") or "admin")
            snapshots = sorted(folder.glob("*/result.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:60] if folder.exists() else []
            matching = []
            for path in snapshots:
                try:
                    saved = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if saved.get("seedream_mode") == key:
                    matching.append((path, saved))
            if matching:
                import datetime
                choices = [-1, *range(len(matching))] if result else list(range(len(matching)))
                index = st.selectbox("已保存的任务", choices, format_func=lambda i: "当前任务" if i == -1 else datetime.datetime.fromtimestamp(matching[i][0].stat().st_mtime).strftime("%m-%d %H:%M:%S"), key=key+"_saved")
                if index != -1:
                    result = matching[index][1]
            render_results(api, result, key)
