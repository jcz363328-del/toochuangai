"""Render A+ template skills and image text editing."""

from __future__ import annotations

from typing import Any


def build_main_image_a_plus_element_preview(
    template_input,
    elements,
    *,
    Image,
    ImageDraw,
    ImageFont,
    ImageOps,
    get_uploaded_file_bytes,
    image_bytes_to_data_url,
    io,
) -> str:
    template_bytes = get_uploaded_file_bytes(template_input)
    try:
        with Image.open(io.BytesIO(template_bytes)) as image:
            preview = ImageOps.exif_transpose(image).convert("RGBA")
            preview.thumbnail((1600, 2400), Image.Resampling.LANCZOS)
    except Exception as exc:
        raise RuntimeError(f"无法生成元素编号预览：{exc}") from exc
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    palette = (
        (126, 96, 255, 255),
        (0, 190, 170, 255),
        (255, 146, 43, 255),
        (232, 73, 135, 255),
        (55, 145, 255, 255),
        (158, 197, 61, 255),
    )
    line_width = max(2, round(min(preview.size) * 0.004))
    badge_padding = max(6, line_width * 2)
    badge_font_size = max(20, min(58, round(min(preview.size) * 0.035)))
    badge_font = None
    for font_path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/msyhbd.ttc",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            badge_font = ImageFont.truetype(font_path, badge_font_size)
            break
        except (OSError, ValueError):
            continue
    if badge_font is None:
        badge_font = ImageFont.load_default()
    for element_index, element in enumerate(elements):
        color = palette[element_index % len(palette)]
        element_id = int(element.get("id") or element_index + 1)
        for region_index, region in enumerate(list(element.get("regions") or [])):
            if not isinstance(region, (list, tuple)) or len(region) < 4:
                continue
            left = round(float(region[0]) / 1000 * preview.width)
            top = round(float(region[1]) / 1000 * preview.height)
            right = round(float(region[2]) / 1000 * preview.width)
            bottom = round(float(region[3]) / 1000 * preview.height)
            region_fill = (color[0], color[1], color[2], 30)
            draw.rectangle(
                (left, top, right, bottom),
                fill=region_fill,
                outline=color,
                width=line_width,
            )
            label = f"#{element_id}"
            text_box = draw.textbbox((0, 0), label, font=badge_font)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            badge_width = text_width + badge_padding * 2
            badge_height = text_height + badge_padding * 2
            badge_left = max(0, min(preview.width - badge_width, left))
            badge_top = max(0, top - badge_height - line_width)
            if badge_top == 0 and top < badge_height + line_width:
                badge_top = min(preview.height - badge_height, top + line_width)
            draw.rounded_rectangle(
                (badge_left, badge_top, badge_left + badge_width, badge_top + badge_height),
                radius=max(4, badge_padding),
                fill=color,
            )
            draw.text(
                (badge_left + badge_padding, badge_top + badge_padding - text_box[1]),
                label,
                fill=(255, 255, 255, 255),
                font=badge_font,
            )
            if region_index == 0:
                draw.line(
                    (
                        badge_left + badge_width / 2,
                        badge_top + badge_height,
                        (left + right) / 2,
                        (top + bottom) / 2,
                    ),
                    fill=color,
                    width=max(1, line_width // 2),
                )
    annotated = Image.alpha_composite(preview, overlay).convert("RGB")
    output = io.BytesIO()
    annotated.save(output, format="JPEG", quality=90, optimize=True)
    return image_bytes_to_data_url(output.getvalue(), "image/jpeg")


def render_a_plus_layout_skill_builder(
    feature_key,
    account_name,
    target_layout,
    *,
    Path,
    delete_a_plus_layout_skill,
    format_user_facing_error_message,
    get_active_a_plus_layout_skill_context,
    get_main_image_a_plus_layout_device,
    hashlib,
    html,
    list_available_a_plus_layout_skills,
    normalize_a_plus_layout_skill_account,
    st,
) -> dict[str, Any]:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    account_key = hashlib.sha1(normalized_account.casefold().encode("utf-8")).hexdigest()[:10]
    selection_key = f"a_plus_layout_skill_selection_{feature_key}_{account_key}"
    delete_confirmation_key = f"a_plus_layout_skill_delete_confirmation_{feature_key}_{account_key}"
    delete_notice_key = f"a_plus_layout_skill_delete_notice_{feature_key}_{account_key}"
    delete_warning_key = f"a_plus_layout_skill_delete_warning_{feature_key}_{account_key}"
    delete_notice = str(st.session_state.pop(delete_notice_key, "") or "").strip()
    delete_warning = str(st.session_state.pop(delete_warning_key, "") or "").strip()
    if delete_notice:
        st.success(delete_notice)
    if delete_warning:
        st.warning(delete_warning)
    all_available_skills = list_available_a_plus_layout_skills(normalized_account)
    target_device = get_main_image_a_plus_layout_device(target_layout)
    if target_device:
        all_skill_by_id = {
            str(skill.get("skill_id") or ""): skill
            for skill in all_available_skills
            if str(skill.get("skill_id") or "")
        }
        current_selection = str(st.session_state.get(selection_key) or "")
        current_skill = all_skill_by_id.get(current_selection, {})
        current_device = str(current_skill.get("device") or "").strip().lower()
        if current_selection and current_device and current_device != target_device:
            counterpart = next(
                (
                    skill
                    for skill in all_available_skills
                    if bool(skill.get("is_builtin"))
                    and str(skill.get("store_key") or "")
                    == str(current_skill.get("store_key") or "")
                    and str(skill.get("device") or "").strip().lower() == target_device
                ),
                None,
            )
            st.session_state[selection_key] = str(
                (counterpart or {}).get("skill_id") or ""
            )
        available_skills = [
            skill
            for skill in all_available_skills
            if str(skill.get("device") or "").strip().lower() in {"", target_device}
        ]
    else:
        available_skills = all_available_skills
    skill_by_id = {
        str(skill.get("skill_id") or ""): skill
        for skill in available_skills
        if str(skill.get("skill_id") or "")
    }
    skill_options = ["", *skill_by_id]
    if selection_key not in st.session_state:
        st.session_state[selection_key] = ""
    elif str(st.session_state.get(selection_key) or "") not in skill_options:
        st.session_state[selection_key] = ""

    st.markdown('<div class="panel-subtitle">本次使用的 A+ 版式 Skill</div>', unsafe_allow_html=True)
    selection_columns = st.columns([5, 1], gap="small")
    with selection_columns[0]:
        selected_skill_id = st.selectbox(
            "本次生成使用的 A+ 版式 Skill",
            options=skill_options,
            key=selection_key,
            format_func=lambda value: (
                "不使用版式 Skill"
                if not value
                else (
                    str(skill_by_id[value].get("title") or "A+ 版式技能")
                    if skill_by_id[value].get("is_builtin")
                    else (
                        f"{skill_by_id[value].get('title') or 'A+ 版式技能'} · "
                        f"{skill_by_id[value].get('created_at') or '时间未知'}"
                    )
                )
            ),
            label_visibility="collapsed",
        )
    with selection_columns[1]:
        if st.button(
            "删除",
            key=f"delete_a_plus_layout_skill_{feature_key}_{account_key}",
            type="secondary",
            icon=":material/delete:",
            use_container_width=True,
            disabled=(
                not bool(selected_skill_id)
                or bool(skill_by_id.get(str(selected_skill_id or ""), {}).get("is_builtin"))
            ),
        ):
            st.session_state[delete_confirmation_key] = str(selected_skill_id or "")
            st.rerun()

    pending_delete_skill_id = str(st.session_state.get(delete_confirmation_key) or "").strip()
    if pending_delete_skill_id and pending_delete_skill_id != str(selected_skill_id or ""):
        st.session_state[delete_confirmation_key] = ""
        pending_delete_skill_id = ""
    if pending_delete_skill_id and pending_delete_skill_id in skill_by_id:
        pending_skill = skill_by_id[pending_delete_skill_id]
        pending_title = str(pending_skill.get("title") or "A+ 版式技能")
        st.warning(
            f"确定删除“{pending_title}”吗？删除后，该 Skill 的结构数据、骨架图和案例文件都会被清理，无法在生成时继续选择。"
        )
        confirmation_columns = st.columns(2, gap="small")
        with confirmation_columns[0]:
            if st.button(
                "确认删除",
                key=f"confirm_delete_a_plus_layout_skill_{feature_key}_{account_key}",
                type="primary",
                icon=":material/delete_forever:",
                use_container_width=True,
            ):
                try:
                    deleted_skill = delete_a_plus_layout_skill(
                        normalized_account,
                        pending_delete_skill_id,
                    )
                except Exception as exc:
                    st.error(f"A+ 版式 Skill 删除失败：{format_user_facing_error_message(exc)}")
                else:
                    st.session_state[delete_confirmation_key] = ""
                    st.session_state[delete_notice_key] = (
                        f"已删除 A+ 版式 Skill：{deleted_skill.get('title') or pending_title}"
                    )
                    cleanup_warning = str(deleted_skill.get("cleanup_warning") or "").strip()
                    if cleanup_warning:
                        st.session_state[delete_warning_key] = cleanup_warning
                    st.rerun()
        with confirmation_columns[1]:
            if st.button(
                "取消",
                key=f"cancel_delete_a_plus_layout_skill_{feature_key}_{account_key}",
                use_container_width=True,
            ):
                st.session_state[delete_confirmation_key] = ""
                st.rerun()

    active_context = get_active_a_plus_layout_skill_context(
        normalized_account,
        str(selected_skill_id or ""),
    )
    if active_context:
        is_builtin = bool(active_context.get("is_builtin"))
        title = str(
            active_context.get("title")
            or ("店铺预置 A+ 风格" if is_builtin else "A+ 版式技能")
        ).strip()
        device = str(active_context.get("device") or "").strip().lower()
        device_label = "手机端" if device == "mobile" else "电脑端" if device == "desktop" else "通用"
        target_size = tuple(active_context.get("target_size") or ())
        target_size_label = (
            f"{int(target_size[0])}×{int(target_size[1])} px"
            if len(target_size) == 2
            else "自适应尺寸"
        )
        source_label = "店铺预置" if is_builtin else "个人 Skill"
        created_at = str(active_context.get("created_at") or "").strip()
        common = dict(active_context.get("common") or {})
        style_summary = str(common.get("style") or "使用已提炼的版式结构与视觉层级").strip()
        summary_meta = [device_label, target_size_label, source_label]
        if created_at and not is_builtin:
            summary_meta.append(created_at)
        summary_meta_html = "".join(
            f"<span>{html.escape(value)}</span>" for value in summary_meta if value
        )
        st.markdown(
            '<div class="a-plus-skill-summary">'
            '<div class="a-plus-skill-summary-head">'
            f'<div class="a-plus-skill-summary-title">{html.escape(title)}</div>'
            '<span class="a-plus-skill-status">已启用</span>'
            '</div>'
            f'<div class="a-plus-skill-summary-meta">{summary_meta_html}</div>'
            f'<div class="a-plus-skill-summary-desc">{html.escape(style_summary)}</div>'
            '<div class="a-plus-skill-summary-note">只应用结构与视觉规则，不会带入历史案例中的产品、品牌、人物或文案。</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        skeleton_path = active_context.get("skeleton")
        skeleton_bytes = b""
        if isinstance(skeleton_path, Path):
            try:
                skeleton_bytes = skeleton_path.read_bytes()
            except Exception:
                pass
        elif isinstance(skeleton_path, dict) and skeleton_path.get("data"):
            skeleton_bytes = bytes(skeleton_path.get("data") or b"")
        with st.expander("查看版式结构（可选）", expanded=False):
            preview_column, rule_column = st.columns([0.42, 0.58], gap="medium")
            with preview_column:
                st.markdown('<div class="panel-subtitle">结构骨架</div>', unsafe_allow_html=True)
                if skeleton_bytes:
                    st.image(
                        skeleton_bytes,
                        width=128 if device == "mobile" else 180,
                    )
                    st.caption("仅表示位置、比例和阅读顺序，不会出现在生成结果里。")
                else:
                    st.caption("当前 Skill 没有可用的结构骨架图。")
            with rule_column:
                reading_flow = " → ".join(
                    str(item).strip()
                    for item in list(common.get("reading_flow") or [])
                    if str(item).strip()
                ) or "按首屏、卖点、细节和收尾顺序组织内容"
                section_count = len(list(common.get("sections") or []))
                st.markdown(
                    '<div class="panel-subtitle">版式摘要</div>'
                    '<div class="a-plus-skill-detail-copy">'
                    f'<strong>阅读顺序</strong><br>{html.escape(reading_flow)}<br><br>'
                    f'<strong>结构模块</strong><br>{section_count} 个主要内容阶段'
                    '</div>',
                    unsafe_allow_html=True,
                )
            if st.checkbox(
                "显示完整结构数据",
                key=f"show_a_plus_layout_skill_data_{feature_key}_{account_key}",
            ):
                st.json(common)
    else:
        st.caption("本次不会向生成 API 附加任何历史版式 Skill。")
    return active_context


def render_main_image_a_plus_text_editor(
    source_image,
    key_prefix,
    *,
    MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS,
    consume_main_image_a_plus_text_edit_point,
    format_user_facing_error_message,
    get_main_image_a_plus_text_edit_signature,
    render_main_image_a_plus_text_edit_picker,
    sanitize_file_name,
    st,
    submit_main_image_a_plus_text_edit,
) -> None:
    normalized_source = str(source_image or "").strip()
    if not normalized_source:
        return
    source_signature = get_main_image_a_plus_text_edit_signature(normalized_source)
    safe_key = sanitize_file_name(
        f"{key_prefix or 'main_image_a_plus_text_edit'}_{source_signature}"
    )
    point_state_key = f"{safe_key}_selected_point"
    clicked_point = consume_main_image_a_plus_text_edit_point(source_signature)
    if clicked_point is not None:
        st.session_state[point_state_key] = clicked_point
    selected_point_raw = st.session_state.get(point_state_key)
    selected_point = (
        (
            int(selected_point_raw[0]),
            int(selected_point_raw[1]),
        )
        if isinstance(selected_point_raw, (list, tuple))
        and len(selected_point_raw) >= 2
        else None
    )

    with st.expander("编辑文字内容与字体", expanded=False):
        st.caption(
            "点击成品图中的目标文字，再输入新文案和字体；系统只重绘该文字块，结果会作为一张新的 A+ 成品保存。"
        )
        render_main_image_a_plus_text_edit_picker(
            normalized_source,
            source_signature,
            selected_point,
            component_key=safe_key,
        )
        point_columns = st.columns([3, 1], gap="small")
        with point_columns[0]:
            if selected_point is None:
                st.info("尚未选择文字位置，请直接点击上方图片中的文字。")
            else:
                st.success(
                    f"已选择文字位置：X {selected_point[0]} / 1000，Y {selected_point[1]} / 1000"
                )
        with point_columns[1]:
            if st.button(
                "重新选择",
                key=f"{safe_key}_clear_point",
                use_container_width=True,
                disabled=selected_point is None,
            ):
                st.session_state.pop(point_state_key, None)
                st.rerun()

        replacement_text = st.text_area(
            "修改后的文字内容",
            key=f"{safe_key}_replacement_text",
            placeholder="输入最终需要显示的准确文案",
            height=100,
            max_chars=500,
        )
        font_option = st.selectbox(
            "字体",
            MAIN_IMAGE_A_PLUS_TEXT_FONT_OPTIONS,
            key=f"{safe_key}_font_option",
        )
        custom_font = ""
        if font_option == "自定义字体":
            custom_font = st.text_input(
                "自定义字体名称或风格",
                key=f"{safe_key}_custom_font",
                placeholder="例如：DIN Condensed Bold、阿里巴巴普惠体",
                max_chars=100,
            )
        selected_font = (
            str(custom_font or "").strip()
            if font_option == "自定义字体"
            else str(font_option or "").strip()
        )
        can_submit = bool(
            selected_point is not None
            and str(replacement_text or "").strip()
            and selected_font
        )
        if st.button(
            "应用文字修改",
            key=f"{safe_key}_submit",
            type="primary",
            use_container_width=True,
            icon=":material/auto_fix_high:",
            disabled=not can_submit,
        ):
            try:
                submit_main_image_a_plus_text_edit(
                    normalized_source,
                    selected_point or (0, 0),
                    str(replacement_text or "").strip(),
                    selected_font,
                )
            except Exception as exc:
                st.error(format_user_facing_error_message(exc))
            else:
                st.rerun()
