"""Build model instructions for A+ layouts, generation and editing."""

from __future__ import annotations


def build_main_image_a_plus_canvas_safety_instruction(
    layout,
    request_aspect_ratio,
    *,
    get_main_image_a_plus_native_safe_zones,
) -> str:
    safe_zones = get_main_image_a_plus_native_safe_zones(
        layout,
        request_aspect_ratio=request_aspect_ratio,
    )
    crop_direction_instruction = (
        "后端适配只锁定最终宽度，把原生图按宽度等比缩放；"
        "最终高度由原生图比例自动决定，高于预设画布时直接完整保留。"
        "禁止任何裁切、拉伸、压缩、补边或根据原图边缘生成背景延展。"
    )
    return (
        "画布安全区硬规则：人物关键五官、商品、包装、图片窗口和关键装饰必须完整落在画面内侧；"
        "标题、正文、参数、品牌名、可读 Logo 和包装上的关键可读文字需要进一步向内收拢，并保留明显、均衡的呼吸空间。"
        f"{crop_direction_instruction}"
        "文字排版必须先确定文本框宽度，再选择字号：短标题可以放大，较长标题必须降低一个或多个字号层级，并在自然语义停顿处主动换行；"
        "禁止为了保持单行而让文字超过文本框，禁止把最后一个单词、字母、标点或描边伸向画布边缘。"
        "右对齐文字只能对齐到画面内部的统一文字栏，不能以画布右边缘作为对齐线；左对齐文字同样不得从画布左边缘起排。"
        "品牌字标和 Logo 必须作为不可拆分的完整图形组放置，外侧至少保留一个大写字母宽度的纯背景缓冲；不得把单个字母或 Logo 端点放进外围裁切区域。"
        "任何文字或前景一旦接近画布边缘，必须缩小字号、重新换行、整组等比缩小或向内移动；最终规格适配不裁任何原图像素，也不能依赖后端裁切或补边。"
        "安全区只用于模型内部构图判断。成品中禁止出现安全框、坐标、距离、像素、百分比、标尺、辅助线、箭头或任何制作说明。"
    )


def build_main_image_a_plus_text_edit_prompt(
    point,
    replacement_text,
    font_name,
    *,
    json,
) -> str:
    point_x = max(0, min(1000, int(point[0])))
    point_y = max(0, min(1000, int(point[1])))
    normalized_text = str(replacement_text or "").strip()
    normalized_font = str(font_name or "").strip() or "保持原字体风格"
    if not normalized_text:
        raise RuntimeError("请输入修改后的文字内容。")
    return (
        "你是商业电商 A+ 成品图的精确文字局部编辑器。第 1 张图是唯一成品底图。"
        f"用户点击的目标坐标为归一化坐标 ({point_x}, {point_y})，坐标范围 0 到 1000。"
        "先定位包含该点击位置、或距离该点最近且明显属于同一语义的完整文字块，只允许编辑这一处文字块。"
        f"将目标文字块的内容严格替换为：{json.dumps(normalized_text, ensure_ascii=False)}。"
        f"目标字体为：{json.dumps(normalized_font, ensure_ascii=False)}。"
        "如果目标字体是“保持原字体风格”，必须复刻原文字的字体气质、粗细、大小写规则、字距、行距、"
        "颜色、描边、阴影、渐变和排版方向；否则只把字体改成指定字体或最接近的字体，同时尽量保留原文字的"
        "颜色、字号层级、对齐、特效和视觉权重。必须清除旧文字的全部笔画和残影，并自然恢复文字下方背景后再排入新文字。"
        "新文案必须逐字准确、清晰可读、不能乱码、不能缺字、不能多字。文字较长时允许在原文字区域内等比缩小字号、"
        "调整字距或合理换行，但不得裁切、溢出、贴边或遮挡产品、人物、Logo。"
        "绝对锁定目标文字块以外的全部画面：其他文字、Logo、品牌、产品、包装、人物、五官、肤色肤质、服装、"
        "背景、装饰、光影、颜色、构图、尺寸和画幅均不得发生任何变化。禁止顺带润色、重排版、改写其他文案、"
        "新增元素、删除元素、裁剪、扩图、拉伸或压缩。只输出 1 张完整编辑后的成品图。"
    )


def build_main_image_a_plus_element_replacement_notes(
    layout,
    detected_element_count,
    replacements,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
) -> str:
    target_width, target_height = layout["target_size"]
    selected_names = "、".join(
        f"#{int(item.get('id') or index + 1)} {str(item.get('name') or '元素')}"
        for index, item in enumerate(replacements)
    )
    return (
        f"系统共识别 {detected_element_count} 个可替换元素组，本次已指定 {len(replacements)} 个：{selected_names}。"
        f"最终只生成一张 {target_width}×{target_height}px 完整 A+ 长图，尺寸和版式严格跟随模板。"
        "只替换已上传对应图片的编号；没有上传图片的编号及所有未编号内容必须保持模板原样。"
        "每个编号的替换图只能进入该编号的全部标注区域，不能用于其他编号，不能改变背景、版式或未选元素。"
        "禁止拆段、拼接、多图输出、顺带重绘、扩大修改范围、遗漏同编号的重复出现位置或保留旧元素残影。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
    )


def build_main_image_a_plus_element_replacement_prompt(
    full_prompt,
    layout,
    replacements,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
) -> str:
    target_width, target_height = layout["target_size"]
    mapping_lines: list[str] = []
    for reference_index, replacement in enumerate(replacements, start=2):
        element_id = int(replacement.get("id") or reference_index - 1)
        name = str(replacement.get("name") or f"元素 {element_id}").strip()
        element_type = str(replacement.get("type") or "other").strip()
        regions = list(replacement.get("regions") or [])
        region_text = "、".join(
            f"[{int(box[0])},{int(box[1])},{int(box[2])},{int(box[3])}]"
            for box in regions
            if isinstance(box, (list, tuple)) and len(box) >= 4
        )
        mapping_lines.append(
            f"输入图片第 {reference_index} 张 → 编号 #{element_id}“{name}”（{element_type}），"
            f"只替换归一化区域 {region_text or '按模板识别位置'}。"
        )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "指定元素映射执行指令：输入图片第 1 张是未标注的完整 A+ 模板；后续图片与编号严格一一对应。\n"
        + "\n".join(mapping_lines)
        + f"\n一次生成 1 张完整的 {target_width}×{target_height}px 成品。"
        "坐标采用模板宽高各自 0 到 1000 的归一化范围。只修改上述编号区域，同编号有多个区域时全部替换。"
        "模板中未列出的产品、品牌、Logo、模特、文字、参数、图标、背景、装饰和版式必须保持不变。"
        "禁止把第 2 张之后的素材混用、错位、跨编号扩散或添加到未指定区域。"
        "输出前逐项核对映射，确保选中元素全部替换、未选元素完全未改。只输出这一张完整成品。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
    )


def build_main_image_a_plus_layout_notes(
    layout_key,
    image_count,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    get_main_image_a_plus_layout,
) -> str:
    layout = get_main_image_a_plus_layout(layout_key)
    target_width, target_height = layout["target_size"]
    return (
        f"当前共上传 {image_count} 张商品主图，图片顺序即参考优先级。"
        "第 1 张必须作为核心主图，严格锁定商品身份、品牌、包装、颜色、材质、结构和比例；"
        "第 2 张至最后一张只用于补充商品角度、局部细节、套装内容、使用方式和可用场景。"
        f"当前选择的版式为“{layout['label']}”。"
        f"当前版式以 {target_width}×{target_height}px 作为构图宽度和高度节奏参考；最终成品只锁定宽度 {target_width}px，"
        "高度根据 API 返回图比例等比自适应，即使超出预设高度也完整保留。"
        "画布尺寸只用于内部构图规划，画面中绝不能出现尺寸数字、坐标、距离、辅助线或分段说明。"
        "整张长图从上到下大体形成四个阅读阶段：模特与品牌主视觉、核心卖点与关键细节、"
        "使用场景或工艺表现、套装包装与品牌收尾。"
        "四个阶段只代表信息节奏，不按固定像素、固定距离或等高方框划分，也不要求内容严格待在各自范围内。"
        "首屏必须是完整的商业主视觉，而不是素材陈列区：如果上传参考图中包含多个模特，只挑选一位最清晰、最适合商业展示的模特作为唯一主视觉核心；如果没有模特，则以核心商品为唯一主视觉且不得虚构人物。"
        "选中的唯一模特必须放在整张长图最上方的首屏区域，并处于画面最上层和视觉最前景；保持身份、脸部、发型、姿态与服饰真实一致，禁止再出现第二位模特或在下方重复该模特；商品、文字、Logo、色块、光效和装饰均不得遮挡模特的脸部关键五官和主要头部轮廓。"
        "允许像时尚杂志广告一样让发梢、肩臂或躯干在摄影窗口边缘自然出血，但脸部关键五官、人物身份和动作语义必须完整，裁切必须显然是专业构图而不是误切。"
        "参考图只是可选择的素材池，不要求全部出现在首屏；必须主动取舍素材，使用专业网格、大小对比、前中后景、光影、留白和品牌文字层级完成高级海报式构图。"
        "严禁在首屏中直接堆叠多个产品抠图、重复人物、重复包装、大量小图、标签和文字块；严禁做成拼贴、产品清单、九宫格或把所有参考图平铺进去。"
        "不要绘制分割线、边框、卡片底板、硬切色块或明显的四块拼接结构；四个阶段之间必须使用构图、景深、光影、色彩和视觉动线自然衔接。"
        "人物、商品、包装、场景、光影、色块、纹理、装饰、大标题图形和其他非正文视觉元素允许跨越相邻阶段，"
        "可以自然遮挡、叠压和延伸，形成一个连续整体，但不能变成凌乱的九宫格或多图拼贴。"
        "只允许展示上传图片中真实存在的商品、配件、包装和信息，不得增加无关商品，不得改变品牌与商品外观。"
        "不得编造参数、认证、功效、促销价格或承诺；补充宣传要求与图片冲突时，以主图中的真实商品信息为准。"
        "背景、场景、色块、纹理和装饰必须满版延伸到画布四边，不得生成边框、白边、黑边、模糊边带或可见留白。"
        "标题、卖点、参数、说明文字和可读 Logo 的完整外接框必须充分向画布内侧收拢，四周留出明显且一致的呼吸空间；"
        "这些安全空间只用于内部排版，成品中不得显示辅助线、坐标、距离、像素文字、标尺或箭头。"
        "文字可以跟随整体构图跨越概念阶段，但每一段完整文字都不能被画布边缘切断，不能出现半个字、缺字或被截断的行。"
        "禁止在画布顶部、底部、左侧或右侧放置贴边文字；每个标题、正文、参数、品牌名和可读 Logo 必须完整保留字高、行高与四周呼吸空间，必要时缩小字号、自动换行或向画面内部移动。"
        "最终规格适配只按目标宽度完整等比缩放，高度由原生画面比例自动决定；"
        "禁止裁切、拉伸、压缩、补边或使用原图边缘生成背景延展，商品、包装、文字、Logo、人物脸部关键五官和关键动作必须完整保留。"
        "必须使用原生 4K 高清细节，商品纹理、边缘、Logo、包装字和宣传字必须清晰锐利、可辨认。"
        "严禁乱码、错别字、模糊、虚焦、涂抹、过度柔化、像素化、压缩痕迹、重复主体和明显 AI 伪影。"
        "必须只调用一次整图生成并直接得到一张连续长图，禁止内部拆段、逐段生成、后期拼接或覆盖原图；不要输出绿幕、透明图、草图、线框或多张候选版式。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
    )


def build_main_image_a_plus_free_prompt(
    full_prompt,
    layout,
    has_layout_skeleton,
    style_reference_count,
    source_pool_only,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    A_PLUS_UPLOAD_POOL_LOCK_RULES,
    build_main_image_a_plus_canvas_safety_instruction,
    select_main_image_a_plus_safe_aspect_ratio,
) -> str:
    target_width, target_height = (int(value) for value in layout["target_size"])
    request_aspect_ratio = select_main_image_a_plus_safe_aspect_ratio((target_width, target_height))
    canvas_safety = build_main_image_a_plus_canvas_safety_instruction(
        layout,
        request_aspect_ratio,
    )
    full_bleed_note = (
        f"原生生成使用最接近构图参考的 {request_aspect_ratio} 画幅；后端只把完整返回图按宽度等比缩放到 {target_width}px，"
        f"高度不强制改成 {target_height}px，而是按原生比例自动计算并完整保留；"
        "禁止裁切或拉伸人物、商品、包装、文字、Logo 和图片窗口，也禁止增加白边、米色边、黑边、透明边、纯色空白带、相框或页边距。"
        "画布四条外边的每一个像素都必须由连续背景、场景、色块、纹理或装饰自然铺满。"
        "比例不一致时不生成任何补边区域、模糊边带或低干扰背景延展，原图内容层不裁掉任何一个像素；"
        "所有商品、包装、Logo、完整文字、人物脸部关键五官和关键装饰仍必须提前放在内侧安全区域，不能贴边构图。"
    )
    art_direction_note = (
        "整图艺术指导硬要求：先从真实商品、包装和品牌视觉中提取一套明确的创意概念，再统一决定主色、辅助色、材质语言、光线气质、字体气质和贯穿全图的单一视觉母题。"
        "成品必须像由资深电商艺术总监完成，而不是把素材放进通用模板：使用编辑设计式网格、不对称平衡、强弱明确的尺度对比、前中后景、局部满版特写、克制留白和连续色彩节奏建立高级感。"
        "从上到下形成‘品牌主视觉—核心价值—细节证据—场景或工艺—品牌收尾’的叙事起伏；相邻内容通过同一背景空间、光线、材质、色带或主体轮廓自然衔接，但每一屏仍要有一个清晰焦点。"
        "禁止使用廉价模板感的等宽卡片、平均四等分、连续相同版式、悬浮小图堆叠、密集徽章、无意义圆角框、贴纸标签、随机花朵光斑和大段说明文字。"
        "文字系统最多使用两种字体气质和三级字号，标题、辅助信息与正文必须有明显层级；文字只能落在低干扰留白上，不压人脸、商品、包装 Logo 或复杂纹理。"
        "如果参考素材品质或数量不足，宁可用尺度、裁切、留白、光影和背景材质完成少而精的构图，也不能复制主体或编造内容来填满画布。"
    )
    normalized_style_reference_count = max(int(style_reference_count or 0), 0)
    if source_pool_only:
        reference_role_note = (
            "全部输入图都是本次上传素材池，也是人物、商品、包装、Logo、文字和配件的唯一事实来源；"
            "每张图、每个元素都可以使用或舍弃，上传顺序不代表必须使用，也不要求第 1 张成为主图。"
        )
    elif normalized_style_reference_count and has_layout_skeleton:
        reference_role_note = (
            "输入图片的最后一张是抽象版式骨架，只表示位置、比例、留白和层级；"
            f"骨架之前的 {normalized_style_reference_count} 张是 A++ 风格参考，只允许学习构图语法和设计语言；"
            "其余更前面的图片才是本次真实商品与品牌素材。禁止从骨架或风格参考复制任何商品、人物、品牌、Logo、文字或商业内容。"
        )
    elif normalized_style_reference_count:
        reference_role_note = (
            f"输入图片最后 {normalized_style_reference_count} 张是 A++ 风格参考，只允许学习构图语法、配色关系、字体气质、视觉密度与阅读节奏；"
            "其余更前面的图片才是本次真实商品与品牌素材。严禁从风格参考复制商品、人物、包装、品牌、Logo、文字、参数或背景照片。"
        )
    elif has_layout_skeleton:
        reference_role_note = (
            "输入图片的最后一张是抽象版式骨架，只表示位置、比例、留白和层级，不是商品或品牌素材；"
            "不得识别、复制或绘制其中的色块、边框、占位形状。除最后一张骨架外，其余输入图才是本次真实商品与品牌素材。"
        )
    else:
        reference_role_note = (
            "全部输入参考图都是本次真实商品与品牌素材，并按上传顺序确定参考优先级；"
            "可以根据任务要求主动取舍，不要求覆盖全部素材。"
        )
    source_lock_rules = (
        A_PLUS_UPLOAD_POOL_LOCK_RULES if source_pool_only else A_PLUS_PRODUCT_LOCK_RULES
    )
    content_structure_note = (
        "必须先按真实素材角色组织整图：1 个略占优势的首屏主中心、2 至 4 个分布在中段和下段且可独立停留的次视觉中心，以及 1 个简洁品牌收尾；"
        "次视觉中心不是附属小卡片，每一个都要拥有足够面积、清晰主体、独立明暗或色彩反差和不同构图动作；不得把全部高价值素材集中在顶部。"
        "若上传素材没有足够的完整真实语义组，可以减少次视觉中心数量，但绝不能复制、补画或虚构对象凑数。"
        "各视觉中心可以使用满版摄影、超大商品前景、局部特写窗口、大小错落双图、横向信息带、包装陈列、步骤节奏、跨区色块与前景遮挡，"
        "但每种布局都必须由上传素材中真实存在的内容驱动，缺少对应内容就跳过。"
        "纯布局层可以新建连续背景、渐变、抽象色块、无语义纹理、统一轮廓的裁切窗口、细分隔线、半透明材质面、柔和投影、高光反射、光晕、景深和留白；禁止用新图标、徽章、箭头、编号、标签或假配件制造丰富感。"
        "从这些允许的纯布局元素中选择三至五种形成统一版式语汇，整图重复相同的色彩关系、边缘轮廓、线条粗细、投影和透明度，不得每个区域随机换效果。"
        "在真实素材允许时，至少同时安排一处满版或半满版首屏强视觉、两处位于不同纵向区域的大中型次视觉锚点、一组与主体叠压的特写窗口，以及一处用明暗反差承托商品或包装的视觉落点。"
        "相邻支撑场景不得连续使用相同的白色底、相同尺寸和相同卡片结构；要用明暗切换、尺度反差、色块穿插、局部摄影或景深创造商业广告节奏。"
        "全图至少形成一个超大主中心、两到四个大中型次中心、少量小型辅助信息，并具有背景、中景、前景三层空间关系；内容丰富但不能平均铺满或机械分块。"
        "禁止把同一人物或商品并排克隆、镜像复制或使用完全相同取景机械重复；真实语义组不足时，同一张完整真实素材最多出现两次，一次作完整或大比例视觉锚点，另一次仅作明显不同取景的局部细节，不能改变任何人物、商品、包装或文字事实。"
        if source_pool_only
        else "全图固定为 1 个首屏主视觉、最多 3 个支撑证据模块和 1 个简洁品牌收尾；"
    )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        f"{reference_role_note}"
        "自由创作整图直出执行指令：必须把真实内容参考图理解为同一商品与品牌的素材库，"
        f"在一次模型生成中直接输出 1 张以 {target_width}×{target_height}px 为构图节奏参考的完整 A+ 宣传长图。"
        "禁止把画布拆成四段或多个模块分别生成，禁止调用多次生成后拼接，禁止复制粘贴原图矩形，"
        "禁止出现接缝、断层、重复背景、突然换场、卡片边界、等高分块或四张图上下排列的视觉痕迹。"
        "从顶部到底部必须共享同一套品牌色、统一场景空间、材质、透视、光源、景深、纹理和设计语言，"
        "通过主体跨区、背景连续延伸、光影渐变、前后景叠压和视觉动线，让卖点内容自然融合为一个整体。"
        "四个内容阶段只负责阅读节奏，任何人物、商品、场景、色块和装饰都可以跨越阶段，不能绘制阶段边框或分割线。"
        "首屏必须有商业广告主视觉和清晰焦点，不能把上传图片缩小后平铺、堆叠或做成素材清单。"
        "如果输入是已经排好标题、参数、对比图和商品图的完成广告模块，禁止整张缩小搬运、整块上下堆叠或复制原模块边界。"
        f"必须只提取完整语义组重组，{content_structure_note}主文字组总数不得超过 5 个。"
        "不要为了覆盖全部参考内容而保留重复口号、次要标签、超大环绕文字或整张规格表；宁可选择最强的少量证据，也不能生成拥挤拼贴。"
        "如果上传素材中有多张模特图，只挑选一位最清晰、最适合商业展示的模特，放在整张图最上方的首屏并置于最上层；"
        "禁止出现第二位模特，禁止在中段或底部再次重复同一模特，任何元素都不能遮挡模特的脸部关键五官；"
        "人像摄影可以采用杂志式近景和满版出血，允许发梢、肩臂或躯干在摄影窗口边缘自然裁切；但眼睛、鼻子、嘴部、主要头部轮廓、人物身份和动作语义必须完整。"
        "如果所有上传素材都没有模特，则以核心商品为首屏主视觉，不得凭空生成陌生人物。"
        f"{art_direction_note}"
        "所有标题、正文、参数、品牌名和可读 Logo 必须逐字完整、清晰可读，上下左右四边都要保留完整字高、行高和自然呼吸空间；"
        "禁止半个字、缺字、断行裁切，也禁止商品、包装、Logo 或人物脸部关键五官被画布误切；空间不足时必须缩小字号、换行、缩小主体或向内移动。"
        f"{canvas_safety}"
        f"{full_bleed_note}"
        f"{source_lock_rules}"
        "最终只返回这一张融合完成的商业级 A+ 成品，不返回局部图、过程图、拼接图或候选版本。"
    )


def build_main_image_a_plus_hero_design_prompt(
    full_prompt,
    layout,
    has_layout_skeleton,
    style_reference_count,
    *,
    build_main_image_a_plus_free_prompt,
) -> str:
    free_prompt = build_main_image_a_plus_free_prompt(
        full_prompt,
        layout,
        has_layout_skeleton=has_layout_skeleton,
        style_reference_count=style_reference_count,
    )
    return (
        f"{free_prompt}\n\n"
        "首屏设计感模式最高优先级执行规则：保持自由创作的一张连续 A+ 长图逻辑不变，但必须把开场首屏设计成可直接用于成熟电商品牌投放的商业主视觉，而不是普通商品陈列、素材拼贴或功能说明页。"
        "首屏必须只有一个明确视觉中心和一条清晰阅读动线；主动舍弃不适合首屏的参考素材，不要求把所有上传图片都放入开场。"
        "优先采用高级杂志式的不对称平衡构图：使用明显的大小对比、前中后景、自然景深、专业光影、大面积品牌色或环境氛围、克制装饰和有目的的留白，形成完整海报感；禁止机械左右对半、平均分配、居中堆叠和模板化卡片排版。"
        "如果参考图中有模特，只选择一位模特作为首屏最大视觉主体并置于最上层；核心商品作为第二视觉主体进入前景或视觉动线关键位置，但不能遮挡模特的脸、眼睛、头发轮廓和身体主体。"
        "如果参考图中没有模特，必须以一个核心商品或一组真实套装建立强主视觉，不得凭空添加人物；通过产品尺度、角度、光影、材质和空间层次获得设计感。"
        "首屏文字必须极度克制，本规则高于自由创作中的一般信息完整要求：除商品包装上原本存在且不可删除的文字外，首屏最多只能出现 3 个独立文字区，并优先只保留品牌 Logo、一个主标题和一句可选的极短辅助文案；副标题与卖点标签二选一，禁止同时出现。"
        "主标题最多 2 行、每行尽量不超过 10 个中文字符；辅助文案最多 1 行、尽量不超过 14 个中文字符。禁止长段落、三行以上标题、卖点列表、参数表、多个徽章、多个标签、连续小字、重复标题和文字矩阵。"
        "首屏至少保留 45% 的无文字视觉区域，全部新增文字合计不得占据首屏面积的 20% 以上；不得为了塞入文案而缩小字号、密集换行、层层叠放或挤压人物与商品。"
        "参考图或用户要求中即使包含大量真实文案，也不能全部堆到首屏：只选择一个最重要的信息，其余经核实的卖点放到后续内容阶段或直接省略。没有真实文案时宁可保留自然留白，也不能编造卖点、参数、认证、价格或促销信息。"
        "主标题、品牌、商品和模特必须建立明确主次，不能相互争抢焦点；文字必须放在真实留白或低干扰背景上，完整清晰且远离四边，禁止压在人脸、眼睛、商品 Logo、包装文字或复杂纹理上。"
        "所有装饰只能服务于视觉动线，禁止无意义花朵、光斑、徽章、贴纸、图标、边框和标签堆积；禁止重复人物、重复商品、重复包装和重复 Logo。"
        "首屏不能成为独立硬边界模块，背景、场景、光影、色彩、纹理或主体轮廓必须自然延续到后续内容，让首屏的商业主视觉与整张 A+ 长图保持同一世界、同一光源和同一设计语言。"
        "不得在画面中显示网格、比例、层级说明、安全区、设计注释或任何本规则文字。"
    )


def build_main_image_a_plus_mobile_safe_margin_instruction(elements, mobile_layout) -> str:
    regions = [
        region
        for element in list(elements or [])
        for region in list(element.get("regions") or [])
        if isinstance(region, list) and len(region) >= 4
    ]
    if regions:
        source_note = (
            "电脑端已经识别到贴近边缘的有效元素，手机端重排时必须主动增加内侧缓冲并逐项检查完整性。"
        )
    else:
        source_note = "电脑端元素坐标仅用于逐项核对，不允许据此裁掉任何边缘内容。"
    return (
        f"{source_note}手机端首次生成时，必须根据元素数量和最大外接框动态规划安全边距，"
        "确保每个完整前景元素都位于画面内侧，任何元素外接框都不能触碰或跨越画布边界。"
        "所有标题、正文、参数、品牌名、可读 Logo 与包装上的关键可读文字还要进一步向内收拢，并保留明显、均衡的四周呼吸空间。"
        "安全缓冲区域不是空白边框，必须继续使用与相邻区域一致的背景、渐变或纹理铺满。"
        "如果放不下，必须继续整体等比缩小元素并重新分配纵向位置，禁止裁切、遮罩、overflow 隐藏或贴边截断。"
        "成品中不得出现安全框、坐标、距离、像素、百分比、标尺、辅助线、箭头或任何制作说明。"
    )


def build_main_image_a_plus_mobile_adaptation_prompt(
    element_inventory,
    safe_margin_instruction,
    mobile_layout,
    reference_pair_count,
    *,
    MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT,
    MAIN_IMAGE_A_PLUS_MOBILE_SOURCE_LOCK_RULES,
    get_main_image_a_plus_layout,
) -> str:
    resolved_layout = dict(mobile_layout or get_main_image_a_plus_layout("mobile_equal"))
    target_width, target_height = (int(value) for value in resolved_layout["target_size"])
    screen_count = int(
        resolved_layout.get("mobile_screen_count")
        or max(round(target_height / MAIN_IMAGE_A_PLUS_MOBILE_SCREEN_HEIGHT), 1)
    )
    pair_count = max(int(reference_pair_count or 0), 0)
    reference_note = (
        f"输入图片共包含 1 张任务原稿和 {pair_count} 组版式参考对：第 1 张是本次待适配的电脑版 A+；"
        f"第 2 张起每两张为一组，顺序固定为电脑版示例、对应手机版示例，共 {pair_count} 组。"
        "先比较每组前后变化，学习其重排语法，再只用第 1 张的内容完成当前任务。"
        if pair_count
        else "输入图片第 1 张是本次待适配的电脑版 A+，也是唯一内容源。"
    )
    prompt = (
        f"{reference_note}"
        f"请输出一张完整的 {target_width}×{target_height}px、共 {screen_count} 个约 600×450 阅读屏的手机端 A+ 长图。"
        "这不是缩放或裁长图，而是参照样本完成同款逻辑的移动端艺术指导与响应式重排。"
        "生成前必须从上到下盘点第 1 张中的全部 critical 元素；人物、商品、包装、Logo、标题、正文、卖点、参数、图标、步骤图、效果图和有语义的图片窗口必须保持种类、数量、原文和阅读顺序一一对应。"
        "对这些 critical 内容不得新增、删除、替换、改写、概括、扩写、翻译或重复，也不得编造新卖点、新文案、新商品或新装饰。"
        "flexible_background 只允许在窄屏重构时裁掉无信息的环境边缘、纯背景和连续纹理；不得把人物、商品、文字或品牌装饰当成背景删除。"
        "这不是内容重绘，但必须是一次真正的移动端版式重构：锁定全部内容与品牌设计语言，同时重新建立适合单手纵向浏览的焦点、层级、尺度、留白和节奏；"
        "禁止把电脑端整图直接缩窄、压扁、中心裁切，或把桌面模块机械地逐块竖排。"
        "所有可读文字必须逐字保持原文，只允许在不改变字符内容和阅读顺序的前提下重新换行。"
        "不得根据语义重新撰写相似文案；无法确认某个字符时，必须按电脑端的原始视觉形状保留该文字块，不得猜测、替换或省略。"
        "版式重排必须遵循三组参考对共同体现的语法：首屏继续使用原品牌主视觉并满宽展示；桌面横向双栏或多栏模块按语义拆成一个或两个纵向阅读屏；Before/After、双眼型、步骤图等天然成组内容可在仍清晰可读时保留紧凑双栏；商品盘、长度表、卖点图和教程模块要放大到手机可读尺寸。"
        "每个阅读屏只建立一个主要信息任务，使用满宽主图、明显而均衡的内侧呼吸空间、清楚的标题层级和紧凑但不拥挤的模块间距；上下屏通过原有品牌底色、纹理、撕纸边、胶片边、色带或光影连续衔接。"
        "首屏保留一个最大视觉焦点；后续屏在大图、紧凑信息组、局部特写和商品包装之间形成疏密交替。允许左右交替、上下错位和穿插纯背景留白，但不得遮挡有效内容。"
        "允许把桌面中的一个复合模块按语义拆成若干完整子组后重排，例如把‘产品盘+长度表’、‘Before/After’、‘卖点文字+睫毛结构图’分别组织；禁止拆散单个文字块、Logo、商品、眼睛、步骤动作或图形内部。"
        "摄影窗口可按 photo_recrop_allowed 为手机比例重新取景，但必须完整保留关键脸部、眼睛、人物身份、商品和动作语义；纯背景可以裁，人物、商品、文字、Logo、步骤图和效果图不能裁。"
        "禁止连续使用相同高度的廉价卡片、平均分栏、素材缩略图列表、密集标签和无意义装饰；不得把所有内容统一缩小来换取完整，必须通过模块拆解、主次尺度和疏密节奏同时保证完整与美观。"
        "任何元素之间都不得相互覆盖有效内容；人脸、头发轮廓、肢体、商品主体、包装边缘、Logo、文字、图标和装饰必须完整可见且四周不被截断。"
        "禁止对整张图或任何人物、商品、Logo、文字、图片窗口进行非等比压缩、拉伸、挤扁、增高、变形、镜像、旋转或透视改造。"
        "人物、商品和包装必须与电脑端成品保持同一外观、数量、比例、角度、颜色、材质、纹理和细节，不能重绘或改款。"
        "保持电脑端成品相同的品牌风格、配色、背景、字体气质、核心视觉母题和阅读顺序，把同一套设计系统翻译成更适合手机浏览的构图，而不是复制桌面坐标。"
        "执行原则必须同时满足：full-bleed background + all foreground elements fully visible。"
        f"目标 {target_width}×{target_height} 的背景、渐变、光影和纹理必须无缝铺满四边，不能出现白边、黑边、透明条、纯色留白条或可见空带。"
        "当前请求画布就是唯一成品层；系统只会在本地把这一层归一为所选目标规格，"
        "不会二次扩图、生成背景副本、叠加回贴、拆屏、分别生成或拼接；整张长图必须始终保持一个连续背景、一个统一网格和一条完整阅读动线。"
        "所有 critical 前景的完整外接框必须充分向画面内侧收拢；所有可读文字与 Logo 必须进一步保留明显、均衡的四周呼吸空间。"
        "安全区是硬边界；任何 critical 元素触碰边界时必须重新换行、重排模块、整组等比缩小或向内移动。禁止拉长边缘像素、镜像复制、拖影或条纹化补边。"
        "成品中不得出现安全框、坐标、距离、像素、百分比、标尺、辅助线、箭头或任何制作说明。"
        "只返回这一张手机端适配成品，不返回说明、对比图、过程图、线框图或多个版本。"
        f"{MAIN_IMAGE_A_PLUS_MOBILE_SOURCE_LOCK_RULES}"
    )
    normalized_inventory = str(element_inventory or "").strip()
    if normalized_inventory:
        prompt += (
            f"\n\n{normalized_inventory}\n"
            "生成结果必须逐条满足以上清单：critical 元素的出现次数必须完全一致且不得切割；flexible_background 只能按其 crop_policy 处理；"
            "清单中的 verbatim_text 必须逐字一致，reading_order 必须保持；"
            "全部 critical 元素放置完成，并确认普通前景、文字与可读 Logo 均完整落在画面内侧后才能输出。"
        )
    normalized_safe_margin = str(safe_margin_instruction or "").strip()
    if normalized_safe_margin:
        prompt += f"\n\n手机端安全边距硬规则：{normalized_safe_margin}"
    return prompt


def build_main_image_a_plus_section_prompt(
    full_prompt,
    layout,
    section_index,
    has_previous_section_reference,
    continuity_reference_role,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    MAIN_IMAGE_A_PLUS_SECTION_PURPOSES,
) -> str:
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    section_height = int(section_heights[section_index])
    purpose = MAIN_IMAGE_A_PLUS_SECTION_PURPOSES[section_index]
    hero_design_rules = (
        "首屏商业主视觉专项规则：本段必须以上传参考图中的一位模特为唯一视觉主体，模特占据首屏最主要面积与最高视觉权重；商品、品牌和场景只作为辅助信息。"
        "模特必须位于最上层、最前景，不能被任何商品、包装、文字、Logo、标签、色块、光效、纹理或装饰覆盖；脸部、眼睛、头发轮廓、身体主体和关键服饰必须完整清晰。"
        "如果需要产生遮挡关系，只能由模特遮挡后方的商品、文字或装饰，不能反向遮挡模特。"
        "必须主动筛选参考素材，不要求全部使用；通过专业网格、非对称平衡、主次比例、前中后景、自然遮挡、留白、光影和品牌色建立高级广告海报感。"
        "商品、人物、标题和卖点必须形成清楚的视觉层级，不能彼此争抢焦点。"
        "禁止把多个商品抠图、人物、包装、小图、图标、标签和文字块直接向画面中堆叠；禁止重复主体、素材平铺、拼贴、九宫格、产品清单和拥挤排版。"
        if section_index == 0
        else ""
    )
    if has_previous_section_reference and continuity_reference_role == "style_anchor":
        continuation_rules = (
            "输入图片中的最后一张是已生成的首屏风格锚点，不是当前片段的内容素材。"
            "必须锁定其中的品牌色、字体气质、商品表现、场景材质、光影方向、景深、纹理、装饰语言和整体商业质感，"
            "让当前片段看起来属于同一张连续长图；不要复制首屏构图，不要重复首屏主体，也不要把锚点当成新商品参考。"
            "当前片段顶部和底部都要使用可自然延续的背景、色彩、光影和视觉动线，避免独立卡片感。"
        )
    elif has_previous_section_reference:
        continuation_rules = (
            "输入图片中的最后一张是紧邻当前画面上方的已生成连续片段，只用于衔接参考；其余输入图片仍是商品内容参考图。"
            "必须观察上一片段底部的背景、主体边缘、场景透视、色彩、光影、纹理、装饰和视觉动线，"
            "从当前片段顶部无痕延续下来；如果上一片段有商品、人物、光影、色块或装饰伸向底边，应在当前片段中自然接续，不能突然切断或重新开始。"
            "不要复刻整张上一片段，也不要把上一片段当成新的商品参考。"
        )
    else:
        continuation_rules = (
            "这是整张长图的起始片段，需要为后续内容保留自然向下延伸的场景、光影、色彩和视觉动线。"
            if section_index == 0
            else "当前没有额外连续片段参考，必须严格依照总提示中的品牌色、商品身份、字体气质、光影方向和场景语言完成本段，并让上下边缘保持可自然延续。"
        )
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "连续长图生成执行指令：系统会依次制作连续画面片段并组合为一张长图，片段不是独立卡片或独立版块。"
        f"本次制作第 {section_index + 1} 个连续画面片段，当前信息重点大体为“{purpose}”，但相邻阶段的内容可以进入本片段。"
        f"内部输出尺寸必须为 {target_width}×{section_height}px，并将组成 {target_width}×{target_height}px 的成品；"
        "这些尺寸仅用于系统输出控制，绝不能作为文字、标尺、坐标或说明出现在画面里。"
        f"{hero_design_rules}"
        f"{continuation_rules}"
        "不要绘制上下分界线、边框、独立卡片、硬切背景或明显的模块边界。"
        "人物、商品、场景、光影、色块、纹理、装饰和大图形都可以延伸到片段顶部或底部，以便跨片段形成连续视觉。"
        "画面、背景、色块和场景必须铺满四边，不要白边、黑边或透明边缘。"
        "完整文案、参数与可读 Logo 不要压在实际上下拼接边缘，避免在合成时被切断；画布左右边缘只需保留自然可读空间，不显示距离标记。"
        "保持整张长图统一的商品身份、品牌色、字体风格、光影方向、透视关系和商业质感。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
        "只输出当前连续画面片段，不要输出辅助线、版式说明或候选方案。"
    )


def build_main_image_a_plus_template_notes(
    layout_or_key,
    image_count,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    get_main_image_a_plus_layout,
) -> str:
    layout = (
        dict(layout_or_key)
        if isinstance(layout_or_key, dict)
        else get_main_image_a_plus_layout(layout_or_key)
    )
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    text_margin_x = int(layout.get("text_margin_x") or 0)
    text_margin_y = int(layout.get("text_margin_y") or 0)
    return (
        f"当前套版任务包含 1 张完整成品 A+ 模板和 {image_count} 张内容参考图。"
        "模板图不提供可复用的品牌、人物、产品或文案，只提供版式与设计结构；内容参考图才是新内容的唯一来源。"
        f"当前选择的成品规格为“{layout['label']}”，最终合成长图必须严格为 {target_width}×{target_height}px。"
        f"四段高度依次为 {'、'.join(str(value) + 'px' for value in section_heights)}。"
        "系统会先按这四段高度拆分模板，再逐段执行同位置、同层级、同视觉比例的内容替换。"
        "第一张模板图决定最终原始宽高、每个内容槽位的大小与位置，禁止改尺寸、改比例、改裁切、改分栏或重新排版。"
        "每一处原模特、原产品、原包装、原 Logo、原品牌名、原宣传语、原参数、原标签和原细节照片都必须被替换或删除，不能残留。"
        "内容参考图中的第一张作为核心商品与品牌识别依据，其余图片用于匹配模特、不同角度、细节、效果、包装、文案和规格。"
        "替换后的内容必须一对一完整落在模板原有槽位中，不得移动、增删、合并或拆分槽位，不得改变分栏比例或打乱阅读顺序。"
        "除文案、人物、产品、包装、Logo 与对应产品细节外，模板背景、色块、边框、装饰线和结构元素保持不变。"
        "禁止新增模板中不存在的人物、产品、配件、图标、徽章、标签、光效、装饰或文字模块，禁止重复主体与杂乱堆叠。"
        f"所有可读文字左右至少内缩 {text_margin_x}px，并与所在分段上下边界至少保持 {text_margin_y}px 距离。"
        "背景与装饰仍须满版到边，文字、Logo 和商品关键信息不得被画布边缘或分区边界截断。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
    )


def build_main_image_a_plus_single_test_notes(
    layout_or_key,
    image_count,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    get_main_image_a_plus_layout,
) -> str:
    layout = (
        dict(layout_or_key)
        if isinstance(layout_or_key, dict)
        else get_main_image_a_plus_layout(layout_or_key)
    )
    target_width, target_height = layout["target_size"]
    return (
        f"当前一张测试任务包含 1 张完整成品 A+ 版式模板和 {image_count} 张内容替换参考图。"
        "第 1 张模板只负责锁定整张长图的版式、构图、背景与设计语言，后续参考图负责提供全部新内容。"
        f"最终只生成 1 张完整的 {target_width}×{target_height}px A+ 长图，并严格跟随模板原始宽高比例与画布方向。"
        "必须把模板作为一个不可拆分的整体进行理解和重绘；禁止拆成四段，禁止生成四张局部图，禁止任何上下拼接、图块拼接或后期合成。"
        "整张图只能调用一次生成流程，并在这一次生成中完成所有人物、产品、产品局部、包装、品牌、Logo、文案、参数、标签、图标和细节照片的全量替换。"
        "只保留不带旧商品语义的纯背景，以及模板的整体构图、分区、槽位位置与大小、裁切窗口、叠放层级、对齐、底层色块、结构边框、留白和阅读顺序。"
        "除背景和版式之外的全部内容都必须替换或删除，不能只替换明显的大产品而遗漏小产品、特写、旧品牌、旧模特、角落文字、半透明元素或背景中的旧内容。"
        "模板旧内容必须全部替换或删除；内容参考图中的第一张作为核心商品和品牌依据，其余图片用于匹配模特、角度、细节、效果、包装、文案与规格。"
        "只能替换内容，不能重新设计版式；不得新增、删除、移动、合并或拆分槽位，不得重复人物、商品、Logo 或添加无关装饰。"
        "如果没有对应替换素材，清除模板旧内容并自然补全原背景，不得保留旧产品、旧品牌、旧文案或旧模特，不得编造信息。"
        "输出前逐项复查所有槽位，确保模板旧产品、旧品牌、旧 Logo、旧文案和旧模特残留为零。"
        "最终画面必须完整连贯、清晰锐利，没有接缝、断层、重复区域、贴纸覆盖感、四块拼接感或新旧内容混合。"
        "所有文字与可读 Logo 必须完整清楚并避免被画布边缘截断。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
    )


def build_main_image_a_plus_single_test_prompt(
    full_prompt,
    layout,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
) -> str:
    target_width, target_height = layout["target_size"]
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "一张测试整图执行指令：输入图片中的第 1 张是完整成品 A+ 版式模板，后续图片全部是新内容参考图。"
        f"一次直接生成 1 张完整的 {target_width}×{target_height}px 商业级 A+ 成品长图。"
        "必须以第 1 张模板的整张画布为统一构图基准，在同一张结果图中完成全部内容替换。"
        "禁止拆成四段或任何数量的局部区域分别生成；禁止拼接、分步合成、分屏、九宫格、多张候选图、接缝、断层和重复画面。"
        "输出宽高比例、画布方向、分区位置、元素槽位、纯背景与视觉层级必须与模板一致。"
        "除纯背景和版式结构外，模板中的文案、人物、产品、产品局部、包装、品牌、Logo、参数、标签、图标、效果图与带有旧商品语义的装饰必须全部替换或删除，一个都不能遗漏。"
        "每一处重复出现的旧产品、旧品牌和旧模特都要分别替换；不要只替换首屏或明显主体。"
        "不要保留任何模板旧内容，不要增加模板没有的元素；新内容必须自然融入原槽位，像在同一份专业设计源文件中一次完成。"
        "生成完成前执行全图复查，旧产品、旧品牌、旧 Logo、旧文案、旧参数和旧模特的残留必须为零。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
        "只输出这一张完整成品，不要输出局部图、过程图、辅助线或版式说明。"
    )


def build_main_image_a_plus_template_section_prompt(
    full_prompt,
    layout,
    section_index,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    MAIN_IMAGE_A_PLUS_SECTION_COUNT,
) -> str:
    target_width, target_height = layout["target_size"]
    section_heights = layout["section_heights"]
    section_height = int(section_heights[section_index])
    text_margin_x = int(layout.get("text_margin_x") or 0)
    text_margin_y = int(layout.get("text_margin_y") or 0)
    return (
        f"{str(full_prompt or '').strip()}\n\n"
        "套版分段执行指令：输入图片中的第 1 张是当前分段的版式模板，后续图片全部是要替换进去的新内容参考图。"
        f"本次只处理第 {section_index + 1}/{MAIN_IMAGE_A_PLUS_SECTION_COUNT} 段，"
        f"输出必须严格为 {target_width}×{section_height}px，最终将合成 {target_width}×{target_height}px 长图。"
        "第 1 张模板分段决定本次输出的精确宽高、构图边界和全部元素槽位，输出不得改变画布比例或裁切范围。"
        "先识别模板中所有人物位、产品位、包装位、Logo 位、标题位、正文位、参数位、标签位和细节图位，"
        "再从后续内容参考图中找到语义对应的新内容逐一替换。"
        "必须像素级锁定模板中每个槽位的坐标、宽高、占比、裁切形状、叠放关系、对齐、背景、色彩、边框、装饰、留白和阅读顺序；不要重新设计版式。"
        "只替换文案、人物、产品、包装、Logo 与对应产品细节；背景、色块、边框、分隔线和结构装饰保持原位。"
        "模板原有的品牌、Logo、文案、模特、产品、包装、局部特写、参数和标签都属于待删除内容，绝对不能出现在结果中。"
        "如果后续参考图没有提供某个槽位的替代内容，删除旧内容并延续相邻背景或装饰，不得保留旧内容或编造新信息。"
        "严格一对一替换且保持模板原有元素数量；禁止添加任何模板没有的人物、产品、配件、图标、徽章、标签、花纹、光效、装饰或文字块。"
        "禁止重复人物、重复商品、重复 Logo、跨槽位放大、元素堆叠和杂乱拼贴；替换内容必须自然融入原槽位，不要出现贴纸感、硬边、遮挡残留、双重文字或新旧内容混合。"
        f"所有文字左右至少内缩 {text_margin_x}px，上下至少内缩 {text_margin_y}px，必须完整可读且不能被截断。"
        f"{A_PLUS_PRODUCT_LOCK_RULES}"
        "只输出这一段完成套版替换后的商业级成品图。"
    )


def build_main_image_a_plus_designed_module_section_prompt(
    user_prompt,
    layout,
    section_index,
    section_count,
    section_height,
    source_report,
    retry_instruction,
    style_reference_count,
) -> str:
    target_width, target_height = (int(value) for value in layout["target_size"])
    if section_index == 0:
        section_role = (
            "首屏英雄区：只建立一个最大视觉焦点，优先使用源图中最完整的人物或商品主视觉、品牌标识和最多一个主标题。"
            "不要搬入规格表、重复卖点、次级口号或缩略图列表。"
        )
        content_limit = "最多提取 1 个完整主视觉组和 1 个完整文字组。"
    elif section_index == section_count - 1:
        section_role = (
            "收尾证据区：只选择源图中一个适合横向展示的完整效果图，或一个精简商品证据组，两者只能选一个；如存在完整品牌标识，可用它完成克制收尾。"
            "严禁把纵向长度阶梯、完整参数表、多个规格行或长卡片硬塞进这个横向区段；只保留一个最强证据，其余全部舍弃。"
            "如果源图包含多个长度、尺寸或数量参数，只能选择一个代表性参数，不得把多行参数改成横向后全部保留。"
            "源图没有完整收尾文案时，保持干净的视觉收束，不得编造 Thank you、Shop now、Choose us 或任何新口号。"
        )
        content_limit = "最多提取 1 个完整证据组、1 个完整品牌标识和 1 个完整文字组。"
    else:
        section_role = (
            "核心详情区：从源图中选择最有证明力的一到两个完整内容组，建立大图与简洁说明的清楚层级。"
            "不要重复首屏人物，不要复制整张源图，也不要塞入源图全部小字和标签。"
        )
        content_limit = "最多提取 2 个完整证据组和 1 个完整文字组。"
    crop_note = ""
    if str(source_report.get("status") or "") == "cropped":
        sides = "、".join(str(value) for value in list(source_report.get("cropped_sides") or []))
        crop_note = (
            f"这张源图的 {sides or '部分'} 边缘存在无法可靠补齐的模块截断。"
            "只能采用四周完整闭合、语义完整可见的内容组；任何半截文字、半张卡片、残缺参数、被切商品或包装都必须舍弃，"
            "不得续写、猜测、镜像或补画缺失内容。"
        )
    intentional_crop_note = (
        "源图中的人物发梢、肩臂、眼部或商品微距如果位于内部摄影窗口边缘，属于允许的专业摄影取景；"
        "不要把它擅自扩成全身照或完整商品。"
        if bool(source_report.get("intentional_crop"))
        else ""
    )
    retry_note = (
        f"上一轮整图质检反馈（只修正与本段有关的问题）：{str(retry_instruction).strip()}"
        "如果反馈提到贴边或被切的徽章、规格、参数、卡片、装饰或次要文字，必须把该次要内容整组删除，"
        "不要再次尝试缩放、重排或保留；只有人物关键五官、商品主体和包装主体不得删除。"
        "如果反馈点名品牌字标或 Logo 被切，必须从源图重新提取完整字标，整组缩小并移到更靠内的低干扰区域；"
        "源图本身没有完整字标时，舍弃独立字标，只保留包装上真实可见的品牌信息，绝不能续写或生成近似拼写。"
        if str(retry_instruction or "").strip()
        else ""
    )
    normalized_user_prompt = str(user_prompt or "").strip()
    normalized_style_reference_count = max(int(style_reference_count), 0)
    input_role_instruction = (
        "输入图片按顺序分为两种角色：第 1 张是当前区段唯一的品牌、人物、商品、文字和事实来源；"
        f"后续 {normalized_style_reference_count} 张仅为 A++ 风格参考，只能借鉴构图语法、层次、配色关系、字体气质、装饰语言和阅读节奏。"
        "严禁从风格参考复制或混入模特、商品、包装、品牌、Logo、文字、参数、背景照片和商业内容。"
        if normalized_style_reference_count
        else (
            "输入中只有 1 张图片，它是当前区段唯一的品牌、人物、商品、文字和事实来源；"
            "不是要求照抄的整页模板，也不存在其他可借用内容的图片。"
        )
    )
    return (
        "这是多张已设计广告模块的分区重构任务。"
        f"{input_role_instruction}"
        f"请只生成整张 A+ 中的第 {section_index + 1}/{section_count} 个横向连续区段；"
        "输出画幅由接口参数决定，不得把画布规格、尺寸数字或比例说明呈现在画面中。"
        f"{section_role}{content_limit}"
        "必须先拆解源图，再只选择上述预算内的完整语义组重新构图。严禁把源图整个方形/矩形画布缩小后贴入，"
        "严禁保留源图外框，严禁整块搬运、双栏拼贴、画中画、九宫格、重复人物、重复商品、重复标题或重复证据。"
        "不要用一个大面积白色或纯色矩形容器承载多个旧模块；应拆掉旧容器，把少量被选中的完整内容组自然融入连续背景。"
        "使用专业网格、明确主次、尺度对比、非对称平衡、留白、景深和品牌色建立新的横向商业构图；"
        "本区段必须继承风格参考中的同一套色彩、字体气质、材质、光线和装饰母题，看起来属于同一张连续 A+，不能另起一套独立海报风格。"
        "背景、渐变、纹理与光影必须铺满四边，区段上下边缘保持可自然延续，不能出现白边、黑边、独立卡片边框或明显分割线。"
        "区段最上沿和最下沿都必须保留一条只含连续背景、渐变、纹理或光影的过渡带；任何文字、Logo、商品、人物关键部位、卡片、参数表和图片窗口都不得进入这两条过渡带。"
        "所有文字、Logo、商品、包装、卡片、参数表和脸部关键五官必须完整位于不可见的内部安全区，四周保留明显、均衡、宽裕的呼吸空间。"
        "安全区只是内部构图约束，绝不能把安全区边界、边距数值、像素单位、标尺、辅助线、箭头或尺寸说明画到成品中。"
        "如果空间不足，只能删去低优先级组、重新换行、等比缩小完整组或增加留白；不得裁切、遮挡、压扁、拉伸或贴边。"
        "所有可读文字只能逐字使用源图中清晰完整的原文；看不清、已经截断或无法确认的字符整组不用，严禁改写、翻译或创造近似文案。"
        "源图旧海报中的宣传标题、口号、卖点长句和装饰性大字默认都是可舍弃内容；除非它是完整清晰的品牌 Logo、包装原字或用户明确要求保留的文案，否则宁可不生成文字。"
        "任何可选文字一旦无法一次完整排入安全区，就必须整组删除，绝不能生成残词、近似拼写或把尾字压到画布边缘。"
        "人物身份、商品 SKU、包装、Logo、颜色、材质、数量和结构必须与源图一致，不得融合、换款或根据相似品补全。"
        f"{crop_note}{intentional_crop_note}{retry_note}"
        + (
            f"用户补充要求仅在不违反上述分区、内容预算与安全区规则时执行：{normalized_user_prompt}"
            if normalized_user_prompt
            else ""
        )
        + "只返回当前单个横向区段成品，不返回说明、对比图、标记框或多个版本。"
    )
