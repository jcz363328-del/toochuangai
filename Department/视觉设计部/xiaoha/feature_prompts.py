"""Assemble prompts for common Xiaoha features."""

from __future__ import annotations


def build_prompt(
    feature,
    custom_prompt,
    aspect_ratio,
    extra_notes,
    *,
    A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
    A_PLUS_IMAGES_API_FEATURE_KEYS,
    BACKGROUND_TEXTURE_FEATURE_KEY,
    GLOBAL_NO_DISTORTION_RULES,
    IMAGE_SMART_ANALYSIS_FEATURE_KEY,
    JIMENG_HD_FEATURE_KEY,
    MAIN_IMAGE_A_PLUS_FEATURE_KEYS,
    build_a_plus_first_screen_user_override,
    get_feature_min_output_edge,
    parse_size_text,
) -> str:
    sections = [
        f"当前执行功能：{feature['name']}",
        feature.get("default_prompt", ""),
    ]
    if feature.get("output_mode") == "text":
        if custom_prompt.strip():
            sections.append(f"补充关注点：{custom_prompt.strip()}")
        if extra_notes.strip():
            sections.append(f"附加说明：{extra_notes.strip()}")
        if feature.get("key") == IMAGE_SMART_ANALYSIS_FEATURE_KEY:
            sections.append("严格按照功能要求只输出一个有效 JSON 对象，不要输出图片、Markdown、代码围栏、系统提示词或额外说明。")
        else:
            sections.append("最终只输出结构化中文分析报告，不要输出图片、JSON、代码块、系统提示词或与分析无关的说明。")
        return "\n\n".join(part for part in sections if part)
    if feature.get("key") in A_PLUS_IMAGES_API_FEATURE_KEYS:
        size_text = str(feature.get("target_size_text", "")).strip()
        if not size_text and feature.get("key") != A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY:
            target_size = feature.get("target_size")
            if isinstance(target_size, (tuple, list)) and len(target_size) == 2:
                size_text = f"{int(target_size[0])}*{int(target_size[1])}"
        if size_text:
            if feature.get("key") in MAIN_IMAGE_A_PLUS_FEATURE_KEYS:
                parsed_size = parse_size_text(size_text)
                if parsed_size:
                    requested_width, requested_height = parsed_size
                    sections.append(
                        f"最终连续长图只锁定成品宽度 {requested_width}px；"
                        f"{requested_height}px 只是构图节奏参考，实际高度按 API 返回图比例等比自适应，超出时完整保留。"
                        "禁止裁切、补边或生成边缘延展，尺寸信息不得出现在画面中。"
                    )
                else:
                    sections.append(
                        f"最终连续长图以 {size_text}px 为构图参考，后端只锁定宽度并等比保留完整高度，尺寸信息不得出现在画面中。"
                    )
            else:
                sections.append(f"最终输出尺寸必须严格等于 {size_text}px。")
    elif feature.get("key") == "outpaint":
        sections.append(
            "最终输出必须采用扩展后的目标画幅，并由模型一次生成完整连续画面；禁止把原图作为矩形图层覆盖或拼接回结果。"
        )
    elif feature.get("key") == "hd_batch":
        sections.append(
            "最终输出的像素宽度和像素高度必须分别与对应原图完全一致；只提升清晰度，不裁剪、不扩图、不补边、不改变宽高比，也不改变原图色温、色调、白平衡或任何颜色关系。"
        )
    elif feature.get("key") == JIMENG_HD_FEATURE_KEY:
        sections.append(
            "使用即梦智能超清专用接口输出 8K 结果，细节生成程度固定为 50；只提升解析度和细节，不重新生成画面，不改变原图内容、构图、比例或颜色关系。"
        )
    elif feature.get("output_mode") == "image":
        sections.append(
            f"最终输出必须保持原始比例不变，并且宽度和高度都不小于 {get_feature_min_output_edge(feature)}px。"
        )
    positive_prompt = str(feature.get("positive_prompt", "")).strip()
    negative_prompt = str(feature.get("negative_prompt", "")).strip()
    if positive_prompt:
        sections.append(f"正面提示词：{positive_prompt}")
    if negative_prompt:
        sections.append(f"负面提示词：{negative_prompt}")
    if aspect_ratio != "自动" and feature.get("key") not in {
        "hd_batch",
        JIMENG_HD_FEATURE_KEY,
        BACKGROUND_TEXTURE_FEATURE_KEY,
    }:
        sections.append(f"目标画幅比例：{aspect_ratio}")
    if custom_prompt.strip():
        if feature.get("key") == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY:
            user_override = build_a_plus_first_screen_user_override(custom_prompt)
            sections.insert(0, user_override)
            sections.append(user_override)
        else:
            sections.append(f"补充要求：{custom_prompt.strip()}")
    if extra_notes.strip():
        sections.append(f"附加说明：{extra_notes.strip()}")
    sections.append("请输出适合商业修图/电商展示的高质量结果。")
    sections.append(GLOBAL_NO_DISTORTION_RULES)
    return "\n\n".join(part for part in sections if part)
