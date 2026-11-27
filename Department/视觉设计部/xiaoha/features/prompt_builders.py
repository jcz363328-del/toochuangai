"""Feature prompt builders for Xiaoha."""
from __future__ import annotations

def build_ai_lash_tray_cutout_prompt(base_prompt: str = "", source_size: tuple[int, int] | None = None) -> str:
    source_note = ""
    if source_size:
        source_width, source_height = source_size
        source_note = (
            f"\n原图尺寸为 {source_width}x{source_height}px。输出必须保持原图画幅比例、商品所在位置、"
            "主体高度、宽高比例、倾斜角度和透视关系一致；只把不需要的背景区域替换为纯 #00FF00，"
            "不要移动、放大、缩小、拉伸、压缩或旋转商品主体。"
        )
    rules = (
        "请严格基于上传图片执行商品抠图预处理。\n"
        "目标：只保留包含多排黑色假睫毛的长方形商品托盘/包装主体。\n"
        "必须完整保留：白色卡纸、透明塑料托盘边框、品牌文字、尺寸文字、花纹、底部说明文字、全部睫毛排布和商品透视角度。\n"
        "必须去除：桌面、左侧透明盒盖、后方支架、阴影、反光、灰尘、杂物和所有无关背景。\n"
        "颜色和高度必须严格保持：不要改变商品原有颜色、亮度、色温、饱和度、对比度和材质透明感；"
        "不要美化、不要调色、不要锐化、不要磨皮、不要重绘。\n"
        "不要改变包装文字，不要重绘文字，不要改变睫毛数量和排列，不要裁掉托盘边缘，不要添加任何新物体。\n"
        "输出要求：把完整商品主体放在纯 #00FF00 绿幕背景上。背景必须是完全纯色 #00FF00，"
        "无渐变、无纹理、无阴影、无地面、无反光、无白边、无描边、无水印。"
        "商品主体边缘必须干净平整，不要出现绿色描边、绿色光晕、绿色毛刺、绿色锯齿或绿色半透明边。"
        f"{source_note}"
    )
    base_prompt = str(base_prompt or "").strip()
    return f"{base_prompt}\n\n{rules}" if base_prompt else rules


def build_hero_style_reverse_analysis_prompt(extra_requirements: str = "") -> str:
    """让视觉模型按固定六个维度拆解参考图，并直接反写中文生图提示词。"""
    parts = [
        "你是资深电商视觉设计总监，擅长视觉风格逆向工程。",
        "请仔细观察这张参考图，从主体内容、构图布局、色彩搭配、光影效果、设计风格、细节元素六个维度做专业拆解，"
        "并据此反写一条可以直接用于 AI 生图的中文提示词。",
        "拆解要求：写清主体是谁、在什么场景、占画面什么位置与比例；构图要说明视角、镜头、景别、视觉焦点、分区与留白；"
        "色彩要说清主色、辅色、点缀色和冷暖关系；光影要说清光位、光质、明暗对比与投影；"
        "风格要说明设计语言、质感、氛围与情绪；细节要列出可复用的装饰、字体气质、图标、材质与局部特写。",
        "提示词要求：具体到主体、场景、构图、镜头、光线、色调、材质、字体气质、装饰语言和画面比例；"
        "不要出现品牌名、店铺名和真实人物姓名，不要照抄图中的全部文案；用自然中文分句描述，不要编号、不要分点符号。",
        "只返回严格 JSON，不要 Markdown、不要解释，字段固定为：",
        '{"subject":"","composition":"","color":"","lighting":"","style":"","details":"","prompt":""}',
        "其中六个拆解字段各 40-120 字，prompt 为 180-320 字。",
    ]
    normalized_extra = str(extra_requirements or "").strip()
    if normalized_extra:
        parts.append(f"用户补充要求：{normalized_extra}")
    return "".join(parts)
