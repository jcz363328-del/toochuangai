from __future__ import annotations

BACKGROUND_TEXTURE_PRESETS: dict[str, str] = {
    "高级哑光": "细腻、均匀的高级哑光表面，低反射、无塑料感，保留自然明暗层次",
    "柔雾磨砂": "柔和雾面磨砂质感，细颗粒漫反射，干净通透但不产生明显镜面高光",
    "微水泥": "现代微水泥质感，细微矿物颗粒与克制的不规则纹理，真实而不过度粗糙",
    "天然洞石": "天然洞石或浅色石材质感，带细微孔隙和自然层理，纹理尺度真实",
    "丝绒绒面": "细密丝绒绒面质感，柔和吸光并带轻微方向性光泽，触感高级",
    "亚麻织物": "自然亚麻织物质感，保留细密经纬纤维，纹理均匀且不过度抢眼",
    "拉丝金属": "精细拉丝金属表面，方向一致的细丝纹和受控金属反射，无廉价镀铬感",
    "磨砂玻璃": "真实磨砂玻璃质感，柔和透光、轻微散射，边缘与空间深度自然",
    "清漆镜面": "平整清漆镜面质感，反射清晰但受控，高光与环境透视符合原场景光线",
    "自然木纹": "真实细腻的自然木纹，纹理走向符合表面结构，颜色与原场景协调",
}

def build_background_texture_instruction(
    selected_presets: list[str] | tuple[str, ...] | None,
    custom_description: str = "",
) -> str:
    normalized_presets = [
        str(name).strip()
        for name in list(selected_presets or [])
        if str(name).strip() in BACKGROUND_TEXTURE_PRESETS
    ]
    parts: list[str] = []
    if normalized_presets:
        preset_details = "；".join(
            f"{name}：{BACKGROUND_TEXTURE_PRESETS[name]}" for name in normalized_presets
        )
        parts.append(f"选择的背景质感为：{preset_details}。")
    normalized_description = str(custom_description or "").strip()
    if normalized_description:
        parts.append(f"用户对背景质感的直接描述：{normalized_description}。")
    parts.append(
        "如果同时选择了预设并填写描述，请把二者自然融合；用户描述优先用于决定颜色、纹理强弱、反光程度和局部表现。"
    )
    parts.append(
        "质感只能作用于原图的场景背景表面，人物、商品、包装、文字、Logo、前景主体、轮廓边缘和主体投影不得被材质化或改写。"
    )
    return "".join(parts)
