from __future__ import annotations

import io
import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


A_PLUS_REFERENCE_LAB_FEATURE_KEY = "a_plus_reference_lab"
A_PLUS_REFERENCE_LAB_DEFAULT_ROOT = Path(
    os.getenv("A_PLUS_REFERENCE_LIBRARY_ROOT", r"C:\Users\admin\Desktop\A++")
)
A_PLUS_REFERENCE_LAB_MAX_PRODUCT_IMAGES = 8
A_PLUS_REFERENCE_LAB_MAX_STYLE_IMAGES = 2
A_PLUS_REFERENCE_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

A_PLUS_REFERENCE_STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "auto": {
        "label": "自动匹配",
        "description": "根据上传素材和补充要求自动选择商业视觉方向。",
        "desktop": (),
        "mobile": (),
    },
    "fashion_editorial": {
        "label": "时尚杂志 · 高对比",
        "description": "强主视觉、超大标题、深色层次与编辑式留白。",
        "desktop": ("4.jpg", "40.jpg"),
        "mobile": ("25.jpg", "4.jpg"),
    },
    "pink_y2k": {
        "label": "粉紫 Y2K · 拼贴",
        "description": "粉紫渐变、贴纸语汇、年轻化排版与有控制的叠层。",
        "desktop": ("2.jpg", "20.jpg"),
        "mobile": ("25.jpg", "2.jpg"),
    },
    "warm_luxury": {
        "label": "暖棕橙 · 轻奢美妆",
        "description": "奶油暖色、产品质感、柔和曲线与高级商业光影。",
        "desktop": ("8.jpg", "45.jpg"),
        "mobile": ("25.jpg", "45.jpg"),
    },
    "clean_blue": {
        "label": "蓝白 · 清晰科技",
        "description": "清楚的产品说明、理性网格、蓝白对比与步骤化表达。",
        "desktop": ("16.jpg", "72.jpg"),
        "mobile": ("25.jpg", "16.jpg"),
    },
    "neon_color_block": {
        "label": "荧光撞色 · 潮流海报",
        "description": "高饱和撞色、大字号、强节奏与品牌化图形语言。",
        "desktop": ("54.jpg", "68.jpg"),
        "mobile": ("25.jpg", "54.jpg"),
    },
}


def get_a_plus_reference_style_options() -> list[str]:
    return list(A_PLUS_REFERENCE_STYLE_PRESETS)


def get_a_plus_reference_style_label(style_key: str) -> str:
    preset = A_PLUS_REFERENCE_STYLE_PRESETS.get(str(style_key or "").strip())
    if preset is None:
        preset = A_PLUS_REFERENCE_STYLE_PRESETS["auto"]
    return str(preset["label"])


def get_a_plus_reference_style_description(style_key: str) -> str:
    preset = A_PLUS_REFERENCE_STYLE_PRESETS.get(str(style_key or "").strip())
    if preset is None:
        preset = A_PLUS_REFERENCE_STYLE_PRESETS["auto"]
    return str(preset["description"])


def infer_a_plus_reference_style(custom_prompt: str) -> str:
    normalized = str(custom_prompt or "").strip().lower()
    keyword_groups = (
        ("pink_y2k", ("粉", "紫", "y2k", "甜酷", "少女", "梦幻")),
        ("warm_luxury", ("棕", "橙", "奶油", "暖", "轻奢", "自然", "裸色")),
        ("clean_blue", ("蓝", "科技", "清晰", "理性", "洁净", "专业", "说明")),
        ("neon_color_block", ("荧光", "撞色", "潮流", "大胆", "海报", "高饱和")),
        ("fashion_editorial", ("黑", "红", "金", "杂志", "时尚", "高对比", "高级")),
    )
    for style_key, keywords in keyword_groups:
        if any(keyword in normalized for keyword in keywords):
            return style_key
    return "fashion_editorial"


def resolve_a_plus_reference_style(style_key: str, custom_prompt: str = "") -> str:
    normalized = str(style_key or "auto").strip()
    if normalized == "auto":
        return infer_a_plus_reference_style(custom_prompt)
    if normalized not in A_PLUS_REFERENCE_STYLE_PRESETS:
        return "fashion_editorial"
    return normalized


def _reference_root(root: str | Path | None = None) -> Path:
    if root is None or not str(root).strip():
        return A_PLUS_REFERENCE_LAB_DEFAULT_ROOT
    return Path(str(root)).expanduser()


@lru_cache(maxsize=8)
def _scan_a_plus_reference_library_cached(root_text: str) -> dict[str, Any]:
    root = Path(root_text)
    summary: dict[str, Any] = {
        "root": str(root),
        "available": root.is_dir(),
        "file_count": 0,
        "image_count": 0,
        "mobile_count": 0,
        "desktop_count": 0,
        "possible_composite_count": 0,
        "unreadable_count": 0,
    }
    if not root.is_dir():
        return summary
    files = sorted((path for path in root.iterdir() if path.is_file()), key=lambda path: path.name.lower())
    summary["file_count"] = len(files)
    for path in files:
        if path.suffix.lower() not in A_PLUS_REFERENCE_IMAGE_SUFFIXES and path.suffix:
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    width, height = (int(value) for value in image.size)
        except Exception:
            summary["unreadable_count"] += 1
            continue
        summary["image_count"] += 1
        ratio = height / float(max(width, 1))
        if width <= 700 and ratio >= 2.2:
            summary["mobile_count"] += 1
        elif 1300 <= width <= 1550 and ratio >= 1.5:
            summary["desktop_count"] += 1
        elif width >= 1600 and ratio < 1.9:
            summary["possible_composite_count"] += 1
    return summary


def scan_a_plus_reference_library(root: str | Path | None = None) -> dict[str, Any]:
    return dict(_scan_a_plus_reference_library_cached(str(_reference_root(root).resolve())))


def select_a_plus_reference_paths(
    style_key: str,
    layout_key: str,
    custom_prompt: str = "",
    root: str | Path | None = None,
    limit: int = A_PLUS_REFERENCE_LAB_MAX_STYLE_IMAGES,
) -> tuple[str, list[Path]]:
    resolved_style = resolve_a_plus_reference_style(style_key, custom_prompt)
    preset = A_PLUS_REFERENCE_STYLE_PRESETS[resolved_style]
    device_key = "mobile" if str(layout_key or "").startswith("mobile") else "desktop"
    library_root = _reference_root(root)
    selected: list[Path] = []
    for file_name in tuple(preset.get(device_key) or ()):
        candidate = library_root / str(file_name)
        if candidate.is_file():
            selected.append(candidate)
        if len(selected) >= max(int(limit), 0):
            break
    return resolved_style, selected


def _find_vertical_gutter_segments(image: Image.Image) -> list[tuple[int, int]]:
    preview = image.convert("RGB")
    preview.thumbnail((640, 960), Image.Resampling.LANCZOS)
    width, height = preview.size
    if width < 160 or height < 240:
        return [(0, image.width)]
    pixels = preview.load()
    sample_step = max(height // 240, 1)
    sample_rows = range(0, height, sample_step)
    row_count = max(len(sample_rows), 1)
    gutter_columns: list[int] = []
    for x in range(max(int(width * 0.12), 1), min(int(width * 0.88), width - 1)):
        near_white_count = 0
        for y in sample_rows:
            red, green, blue = pixels[x, y]
            if min(red, green, blue) >= 247 and max(red, green, blue) - min(red, green, blue) <= 6:
                near_white_count += 1
        if near_white_count / float(row_count) >= 0.97:
            gutter_columns.append(x)
    if not gutter_columns:
        return [(0, image.width)]

    gutter_groups: list[tuple[int, int]] = []
    group_start = gutter_columns[0]
    group_end = group_start
    for x in gutter_columns[1:]:
        if x <= group_end + 1:
            group_end = x
            continue
        gutter_groups.append((group_start, group_end + 1))
        group_start = x
        group_end = x
    gutter_groups.append((group_start, group_end + 1))
    gutter_groups = [
        group
        for group in gutter_groups
        if group[1] - group[0] >= max(int(width * 0.004), 2)
    ]
    if not gutter_groups:
        return [(0, image.width)]

    scale_x = image.width / float(width)
    boundaries = [0]
    for gutter_start, gutter_end in gutter_groups:
        boundaries.extend(
            [
                max(0, min(image.width, int(round(gutter_start * scale_x)))),
                max(0, min(image.width, int(round(gutter_end * scale_x)))),
            ]
        )
    boundaries.append(image.width)
    segments: list[tuple[int, int]] = []
    for index in range(0, len(boundaries) - 1, 2):
        left = boundaries[index]
        right = boundaries[index + 1]
        if right - left >= int(image.width * 0.18):
            segments.append((left, right))
    return segments or [(0, image.width)]


def prepare_a_plus_reference_style_input(
    reference_path: str | Path,
    layout_key: str,
) -> dict[str, Any]:
    path = Path(reference_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            working = ImageOps.exif_transpose(source).convert("RGB")
    segments = _find_vertical_gutter_segments(working)
    split_applied = len(segments) > 1
    if split_applied:
        target_ratio = 600 / 1800 if str(layout_key or "").startswith("mobile") else 1464 / 2400
        selected_left, selected_right = min(
            segments,
            key=lambda segment: (
                abs(((segment[1] - segment[0]) / float(max(working.height, 1))) - target_ratio),
                -(segment[1] - segment[0]),
            ),
        )
        working = working.crop((selected_left, 0, selected_right, working.height))
    output = io.BytesIO()
    working.save(output, format="JPEG", quality=90, optimize=True)
    device_suffix = "mobile" if str(layout_key or "").startswith("mobile") else "desktop"
    segment_suffix = "_split" if split_applied else ""
    return {
        "data": output.getvalue(),
        "name": f"{path.stem}_{device_suffix}_style{segment_suffix}.jpg",
        "type": "image/jpeg",
        "source_name": path.name,
        "split_applied": split_applied,
    }


def build_a_plus_reference_lab_instruction(
    style_key: str,
    layout_key: str,
    product_image_count: int,
    style_reference_count: int,
    custom_prompt: str = "",
    auto_repair_crops: bool = True,
) -> str:
    resolved_style = resolve_a_plus_reference_style(style_key, custom_prompt)
    preset = A_PLUS_REFERENCE_STYLE_PRESETS[resolved_style]
    is_mobile = str(layout_key or "").startswith("mobile")
    normalized_product_count = max(int(product_image_count), 0)
    visual_center_target = (
        2
        if normalized_product_count <= 1
        else 3
        if normalized_product_count <= 3
        else 4
    )
    support_area_target = (
        3
        if normalized_product_count <= 1
        else 4
        if normalized_product_count <= 3
        else 5
    )
    source_usage_instruction = (
        f"若这 {normalized_product_count} 张上传图都含有清晰、完整且不重复的可用内容，成品至少要使用 4 组来自不同源图或不同语义组的真实证据；"
        if normalized_product_count >= 4
        else (
            f"若这 {normalized_product_count} 张上传图含有多组清晰、完整且不重复的可用内容，优先同时使用至少 2 组真实证据；"
            if normalized_product_count >= 2
            else (
                "当只有一张源图时，只能拆分使用其中清晰完整的真实语义组；"
                if normalized_product_count == 1
                else "没有真实源图时不得生成任何商品或商业内容；"
            )
        )
    )
    device_instruction = (
        "当前输出是手机版：必须重新组织为单列阅读，放大标题与商品，减少同屏小元素；禁止把电脑版直接缩小或居中裁切。"
        if is_mobile
        else "当前输出是电脑版：使用宽画布的不对称构图、尺度对比和跨区域视觉动线，同时保持关键文字与商品安全。"
    )
    return (
        "A+测试上传素材池自由创作规则："
        f"本次只有 {normalized_product_count} 张用户上传图片，除此之外没有任何图片参考、模板参考或外部元素来源。"
        "把上传图片中真实可见的人物、商品、包装、Logo、文字、配件、效果图、步骤图和场景片段拆解为可选内容池；"
        "所有元素都是可选项，没有任何一张上传图必须整张使用，第 1 张也不是必须照抄的主图。"
        "可以根据商业表达自由选择、舍弃、放大、缩小、重新取景、叠层和重排这些真实元素，但凡被采用的元素必须保持原人物身份、商品款式、包装结构、Logo 拼写、颜色、材质、数量和比例。"
        "严禁生成上传图片中不存在的可识别内容，包括新人物、新眼睛、新商品、新包装、新睫毛款式、新工具、新刷子、新镊子、新胶水瓶、新镜子、新花朵、新丝带、新徽章、新图标、新认证和新文案；"
        "只允许新建设计性的纯背景、抽象色块、渐变、无语义纹理、光影和投影，且这些背景元素不得伪装成商品、配件或认证标识。"
        "同一人物或商品在不同上传图中出现时，只能选择一个最完整角度作为主要版本；不得把不同图片中的脸部、商品结构、包装文字或配件融合成一个不存在的新对象。"
        "源图边缘已经缺失的商品、包装、Logo、文字和配件不得猜测补画；如果其他上传图没有同一对象的完整真实依据，就直接舍弃该残缺元素。"
        "所有可读文字只能逐字来自上传图片中清晰完整的原文或用户明确输入；看不清、被截断或无法确认的文字整组不用，禁止近似品牌名、改写卖点、虚构参数和乱码。"
        "文字大小必须服从可用文本框，而不是反过来撑破版式：先为每组文字确定远离四边的内部栏宽，再按最长一行选择字号；短标题可以大，长标题必须自动降低字号并在自然语义停顿处换行。"
        "任何一行文字在排入文本框后都必须仍有左右呼吸空间；右对齐文字只能对齐内部栏线，不能贴画布右边，左对齐文字也不能贴画布左边。"
        "禁止为了维持超大字号或单行标题而牺牲完整性；如果空间不足，依次采用语义换行、缩小字号、缩短文本框内行宽、移动整组位置，绝不能裁掉尾字、单词、标点、描边或阴影。"
        f"采用“{preset['label']}”商业方向：{preset['description']}该方向只是文字化艺术指导，不对应、也不加载任何 A++ 文件夹图片。"
        "生成前先在内部盘点素材角色并选出：最强人物或商品、可核实的细节或效果证据、可读文字、包装或套装、步骤或场景；再把不同真实语义组分配到顶部、中段和下段的视觉中心，缺少的角色直接跳过，不能补造。"
        f"{source_usage_instruction}无法确认、已经被截断或本质重复的内容不参与计数，也不得为了达到数量而猜测补画。"
        f"先建立贯穿全图的统一设计系统，再沿长图纵向组织约 {visual_center_target} 个可独立停留的视觉中心：一个略占优势的首屏主中心，加上分布在中段和下段的次视觉中心；全图约 {support_area_target} 个有明显主次变化的内容场景和一个简洁品牌收尾。"
        "每个次视觉中心都必须拥有足够面积、清晰的主体、独立的明暗或色彩反差和明确构图动作，不能退化成主视觉旁边的小缩略图、同尺寸卡片或普通说明区；不得把全部高价值素材集中在顶部而让中下段失去视觉重量。"
        "优先让不同视觉中心分别承担人物氛围、商品或包装锚点、效果或细节证据、步骤或套装信息等不同商业角色；只有上传素材中确实存在对应真实内容时才安排该角色。"
        "支撑内容不是等高卡片：应从以下真实素材驱动的布局手法中按需选择并混合——满版或半满版摄影、超大商品前景、局部特写窗口、大小错落的双图关系、错位文字区、横向信息带、包装陈列台、步骤节奏、前景遮挡和跨区色块；没有对应真实内容的手法不得使用。"
        "纯版式层允许新增连续品牌色背景、大面积渐变、抽象几何或有机色块、低透明度无语义纹理、统一轮廓的裁切窗口、细分隔线、半透明材质面、柔和投影、高光反射、光晕、景深和留白区；禁止新增箭头、编号、图标、徽章、标签、按钮、奖章或任何看起来像商品配件和认证的装饰。"
        "商业设计感必须通过一套可重复的版式语汇建立：从上述允许项中选择三至五种并贯穿全图，统一色彩、圆角或曲线、线条粗细、投影和透明度；不得每个区域随机换一套效果。"
        "整图至少要同时出现一处满版或半满版首屏强视觉、两处位于不同纵向区域的大中型次视觉锚点、一组与主体有层叠关系的特写窗口，以及一处承托商品或包装的深浅对比落点；只有对应真实素材存在时执行，不得造物。"
        "相邻两个支撑场景不得连续使用相同的白色底、相同尺寸和相同卡片结构；必须用明暗切换、尺度反差、色块穿插或背景摄影形成商业广告的节奏。"
        "必须形成背景氛围层、中景信息与图形层、前景商品或人物层；首屏主中心可以最强，但中段和下段的次中心也必须具备明确焦点和独立视觉重量，至少三处内容要通过前后遮挡、跨区色块、光影延续或景深自然连接，但不得遮住人物五官、商品结构、包装、Logo 和文字。"
        "全图要有至少三种尺度层级：一个超大主中心、两到四个大中型次中心、少量小型辅助信息；不同中心交替使用满版视觉、局部特写、克制留白和结构化信息，形成强弱、疏密、明暗与虚实起伏。"
        "内容丰富来自真实信息的重新编排和多层空间关系，不来自塞满所有素材；禁止整图由同尺寸、同底色、同圆角卡片机械堆叠，也禁止只有一张主图加大片无目的空背景。"
        "背景、色块、场景、光影或纹理必须连续铺到画布四边，成品不得出现页边距、相框、白边、黑边或任何空白边带。"
        "任何安全区、像素、坐标、距离、标尺、箭头和制作批注只能存在于内部思考，绝不能被绘制或写进成品。"
        "禁止把同一人物或商品做成并排克隆、镜像复制或完全相同取景的机械重复；当真实语义组不足以建立多个中心时，同一张完整真实素材最多可以出现两次，一次作为完整或大比例视觉锚点，另一次只能作为明显不同取景的局部细节，且不得改变人物身份、商品结构、包装、Logo、颜色、数量或比例。主文字组总数不超过五组。"
        f"{device_instruction}"
    )
