"""Generate consecutive Walmart A+ pages from an Amazon A+ image."""

from typing import Any


def run_amazon_to_walmart_a_plus_job(job_context: dict[str, Any], *,
    prepare_openrouter_uploaded_input,
    split_amazon_a_plus_source,
    set_task_progress,
    AMAZON_TO_WALMART_PAGE_COUNT,
    AMAZON_TO_WALMART_PAGE_PROMPT,
    call_openrouter_images_api,
    NANO_BANANA_MODEL,
    AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    resize_image_to_exact_size,
    AMAZON_TO_WALMART_PAGE_SIZE,
    image_url_as_uploaded_input,
    uploaded_input_to_data_url,
) -> dict[str, Any]:
    uploaded_files = list(job_context.get("uploaded_files") or [])
    if len(uploaded_files) != 1:
        raise RuntimeError("亚马逊A+改沃尔玛A+需要且只能上传 1 张完整亚马逊 A+ 图片。")
    job_id = str(job_context.get("job_id") or "")
    source = prepare_openrouter_uploaded_input(uploaded_files[0])
    sections, source_was_split = split_amazon_a_plus_source(source)
    page_purposes = (
        "品牌与商品主视觉，建立第一视觉焦点",
        "核心卖点与关键产品细节，信息完整且易读",
        "使用场景、功能表现或工艺证据",
        "规格、包装、组合信息与品牌收尾",
    )
    output_images: list[str] = []
    previous_page: dict[str, Any] | None = None
    custom_prompt = str(job_context.get("custom_prompt") or "").strip()
    for page_index, (section, purpose) in enumerate(zip(sections, page_purposes), start=1):
        if job_id:
            set_task_progress(
                job_id,
                12 + (page_index - 1) * 18,
                f"正在重构沃尔玛 A+ 第 {page_index}/{AMAZON_TO_WALMART_PAGE_COUNT} 页",
            )
        if previous_page is None:
            request_inputs = [source, section]
            reference_roles = (
                "输入图第 1 张是完整亚马逊 A+，只用于核对品牌视觉系统、商品外观、Logo 与全局配色，不作为本页内容来源；"
                + (
                    "第 2 张是当前页对应的原始内容区域，是本页唯一的内容来源。"
                    if source_was_split
                    else "原图不是长图，第 2 张与第 1 张相同；本页只取与页面职责相关的内容，其余内容留给其他页。"
                )
                + "当前是第 1 页，需要建立后续三页共同遵循的视觉系统，并让底部可自然延续。"
            )
        else:
            request_inputs = [section, previous_page]
            reference_roles = (
                "输入图第 1 张是当前页对应的原始内容区域，是本页唯一的内容来源；"
                "第 2 张是已经完成的上一页，只用于承接背景边缘、配色、字体气质、光影和装饰动线。"
                "上一页的任何标题、宣传句、卖点、参数、场景或主体都不得在本页重复出现。"
            )
        page_prompt = "\n\n".join(
            part
            for part in (
                AMAZON_TO_WALMART_PAGE_PROMPT,
                custom_prompt and f"用户补充要求：{custom_prompt}",
                reference_roles,
                f"当前只生成第 {page_index}/4 页，本页职责：{purpose}。",
                "本页是单张 1920×1080 独立页面：禁止四宫格、禁止多页拼贴、禁止把原图多段内容缩略进本页、禁止边框和说明文字。"
                f"本页内容只能来自第 {2 if previous_page is None else 1} 张图的当前内容区域，禁止把其他内容区域的标题、宣传句、卖点、参数、场景或画面搬入本页。"
                "本页内同一标题、宣传句、卖点、参数说明、功能说明和行动语只能出现一次，同一画面中同一视觉元素最多出现一次，不得近义改写后重复表达。"
                "本页文案只能取当前内容区域中尚未在前页出现的部分；若与前页重复则整条省略，并用商品细节、场景或自然留白重新平衡版式，不得编造新句填补。"
                "Brand Logo 可保留，品牌口号不得跨页重复。",
            )
            if part
        )
        page_result = call_openrouter_images_api(
            model=str(job_context.get("model") or NANO_BANANA_MODEL),
            prompt=page_prompt,
            uploaded_files=request_inputs,
            aspect_ratio="16:9",
            resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
        )
        page_images = list(page_result.get("images") or [])
        if not page_images:
            raise RuntimeError(f"沃尔玛 A+ 第 {page_index} 页没有返回图片，请重试。")
        exact_page = resize_image_to_exact_size(
            page_images[0],
            AMAZON_TO_WALMART_PAGE_SIZE[0],
            AMAZON_TO_WALMART_PAGE_SIZE[1],
        )
        output_images.append(exact_page)
        previous_page = image_url_as_uploaded_input(exact_page, f"walmart_a_plus_page_{page_index}.png")
    if job_id:
        set_task_progress(job_id, 88, "正在整理 4 张沃尔玛 A+ 页面")
    return {
        "images": output_images,
        "source_images": [uploaded_input_to_data_url(source)] * AMAZON_TO_WALMART_PAGE_COUNT,
        "captions": [f"沃尔玛 A+ 第 {index}/4 页 · 1920×1080" for index in range(1, 5)],
        "text": (
            "已按原内容顺序生成 4 张 1920×1080 沃尔玛 A+ 页面。"
            "每页均为独立完整构图，并通过统一品牌色、字体气质、光影和边缘过渡保持整组连贯。"
        ),
        "channel": "Images API 原生 4K · 沃尔玛 A+ 四页连续重构",
        "target_size": AMAZON_TO_WALMART_PAGE_SIZE,
        "page_count": AMAZON_TO_WALMART_PAGE_COUNT,
        "source_was_split": source_was_split,
    }
