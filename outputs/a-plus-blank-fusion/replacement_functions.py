def build_first_screen_fill_mask(source: Image.Image, manual_start: int = 0) -> Image.Image:
    """Only connected, low-detail background is editable, including below the hero."""
    if manual_start and not 0 < manual_start < source.height:
        raise RuntimeError("填充起始高度必须小于底稿总高度。")
    start, end = detect_first_screen_fill_bounds(source)
    rgb = source.convert('RGB')
    margin = max(1, source.width // 10)
    background = ImageStat.Stat(rgb.crop((margin, start, source.width-margin, end))).median
    channels = rgb.split()
    distances = [ImageChops.difference(channel, Image.new('L', rgb.size, round(color)))
                 for channel, color in zip(channels, background)]
    distance = ImageChops.lighter(ImageChops.lighter(distances[0], distances[1]), distances[2])
    eligible = distance.point(lambda value: 255 if value <= 24 else 0)
    # Low-contrast type and thin decorations also count as original content.
    ranges = [ImageChops.subtract(channel.filter(ImageFilter.MaxFilter(5)),
                                 channel.filter(ImageFilter.MinFilter(5))) for channel in channels]
    detail = ImageChops.lighter(ImageChops.lighter(ranges[0], ranges[1]), ranges[2])
    eligible = ImageChops.multiply(eligible, detail.point(lambda value: 255 if value <= 1 else 0))
    draw = ImageDraw.Draw(eligible)
    draw.rectangle((0, 0, source.width-1, max(0, int(source.height*.08)-1)), fill=0)
    if end < source.height:
        draw.rectangle((0, end, source.width-1, source.height-1), fill=0)
    # An enclosed, flat foreground can resemble the background. Seed from the
    # outer perimeter, never from its center, and require the component to span
    # the candidate background bounds. Ambiguous disconnected patches stay locked.
    candidate_bounds = eligible.getbbox()
    if candidate_bounds is None:
        raise RuntimeError("未检测到可以安全添加卖点的空白区域，请使用留白更充足的底稿。")
    x0, y0, x1, y1 = candidate_bounds
    # Tie the background to the original detection band, not to the surviving
    # eligible pixels: a flat object on a textured/gradient background is not blank.
    if (x0 > margin or x1 < source.width-margin
            or y0 > start+3 or y1 < end-3):
        raise RuntimeError("无法确认足够连续的安全空白区域，请使用留白更充足的底稿；已有元素不会被覆盖。")
    pixels = eligible.load()
    perimeter = [(x, y0) for x in range(x0, x1)]
    perimeter += [(x, y1-1) for x in range(x0, x1)]
    perimeter += [(x0, y) for y in range(y0+1, y1-1)]
    perimeter += [(x1-1, y) for y in range(y0+1, y1-1)]
    mask = None
    components_checked = 0
    for seed in perimeter:
        if pixels[seed] != 255:
            continue
        components_checked += 1
        if components_checked > 16:
            break
        ImageDraw.floodfill(eligible, seed, 128, thresh=0)
        component = eligible.point(lambda value: 255 if value == 128 else 0)
        if component.getbbox() == candidate_bounds:
            mask = component
            break
        # Visited components cannot be considered a second time.
        eligible = eligible.point(lambda value: 0 if value == 128 else value)
        pixels = eligible.load()
    if mask is None:
        raise RuntimeError("无法确认连续安全的空白区域，请使用留白更充足的底稿；已有元素不会被覆盖。")
    # Add breathing room around every original element, including side/footer art.
    padding = max(2, min(16, round(source.width*.005)))
    mask = mask.filter(ImageFilter.MinFilter(padding*2+1))
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 0, source.width-1, padding-1), fill=0)
    draw.rectangle((0, source.height-padding, source.width-1, source.height-1), fill=0)
    draw.rectangle((0, 0, padding-1, source.height-1), fill=0)
    draw.rectangle((source.width-padding, 0, source.width-1, source.height-1), fill=0)
    # A manual height can only restrict the detected safe area, never unlock art.
    if manual_start:
        draw.rectangle((0, 0, source.width-1, manual_start-1), fill=0)
    return mask


def find_first_screen_safe_region(mask: Image.Image) -> tuple[int, int, int, int]:
    """Largest usable all-white rectangle; never clip generated elements with a mask."""
    width, height = mask.size
    min_width = max(16, round(width*.15))
    min_height = max(16, round(height*.08))
    rows = memoryview(mask.convert('L').tobytes())
    heights = [0] * (width+1)
    best_area, best = 0, None
    for y in range(height):
        stack = []
        for x in range(width+1):
            heights[x] = heights[x]+1 if x < width and rows[y*width+x] == 255 else 0
            while stack and heights[stack[-1]] > heights[x]:
                rectangle_height = heights[stack.pop()]
                left = stack[-1]+1 if stack else 0
                rectangle_width = x-left
                # Avoid tiny slivers even when their total area looks large.
                usable_width = min(rectangle_width, rectangle_height*6)
                usable_height = min(rectangle_height, rectangle_width*6)
                area = usable_width*usable_height
                if usable_width >= min_width and usable_height >= min_height and area > best_area:
                    best_area = area
                    inset = (rectangle_width-usable_width)//2
                    best = (left+inset, y+1-usable_height, left+inset+usable_width, y+1)
            stack.append(x)
    if best is None:
        raise RuntimeError("底稿没有足够完整的空白区域容纳卖点素材；请使用留白更充足的底稿，原有元素不会被覆盖。")
    return best


def fit_selling_points_region(image: Image.Image, size: tuple[int, int], background) -> Image.Image:
    """Contain the entire generated design; keep the original background in any padding."""
    image = ImageOps.exif_transpose(image).convert('RGBA')
    fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
    if isinstance(background, Image.Image):
        canvas = background.convert('RGBA').copy()
        if canvas.size != size:
            raise ValueError("卖点背景尺寸必须与安全区域一致。")
    else:
        canvas = Image.new('RGBA', size, tuple(background) + (255,))
    canvas.alpha_composite(fitted, ((size[0]-fitted.width)//2, (size[1]-fitted.height)//2))
    return canvas


def preserve_first_screen_pixels(image_url: str, uploaded_input: Any) -> str:
    """Keep the same original-content lock for legacy callers."""
    with Image.open(io.BytesIO(get_uploaded_file_bytes(uploaded_input))) as image:
        source = ImageOps.exif_transpose(image).convert('RGBA')
    bounds = find_first_screen_safe_region(build_first_screen_fill_mask(source))
    data, _mime = load_image_bytes_from_url(image_url)
    with Image.open(io.BytesIO(data)) as image:
        # Legacy input is an entire design, so contain it instead of cropping it.
        designed = fit_selling_points_region(image, (bounds[2]-bounds[0], bounds[3]-bounds[1]), source.crop(bounds))
    canvas = source.copy()
    canvas.paste(designed, bounds[:2])
    output = io.BytesIO()
    canvas.save(output, format='PNG')
    return image_bytes_to_data_url(output.getvalue(), 'image/png')


def request_selling_points_layout(model, prompt, inputs, size, background):
    # Sparse layouts are valid. Never request another paid generation to fill space.
    result = call_openrouter_images_api(
        model=model, prompt=prompt, uploaded_files=inputs,
        aspect_ratio=select_closest_aspect_ratio(size),
        resolution=AMAZON_A_PLUS_NATIVE_IMAGE_SIZE,
    )
    if not result.get('images'):
        raise RuntimeError("卖点区域未返回图片。")
    return result


def run_first_screen_selling_points_job(job_context: dict[str, Any]) -> dict[str, Any]:
    """Add a complete design inside confirmed blank space; leave the base intact."""
    files = list(job_context.get('uploaded_files') or [])
    if len(files) < 2:
        raise RuntimeError("请上传首屏底稿和至少一张卖点素材图。")
    with Image.open(io.BytesIO(get_uploaded_file_bytes(files[0]))) as image:
        source = ImageOps.exif_transpose(image).convert('RGBA')
    manual_start = int(job_context.get('a_plus_first_screen_keep_height') or 0)
    fill_mask = build_first_screen_fill_mask(source, manual_start)
    bounds = find_first_screen_safe_region(fill_mask)
    left, top, right, bottom = bounds
    region_size = (right-left, bottom-top)
    background = source.crop(bounds)
    guide_bytes = io.BytesIO()
    background.save(guide_bytes, format='PNG')
    guide_input = {'data': guide_bytes.getvalue(), 'name': 'fill-area-guide.png', 'type': 'image/png'}
    margin = max(4, round(min(region_size)*.04))
    prompt = (
        f"任务：在一张 {source.width}×{source.height} 的 A+ 底稿空白区域中自然加入合适的卖点元素。"
        f"本次只输出 {region_size[0]}×{region_size[1]} 的局部卖点画布，对应底稿 x={left}..{right}、y={top}..{bottom} 的空白位置，不输出或重画整张底稿。"
        "第1张是不可修改的完整底稿，仅用于理解现有内容与品牌风格。其任何人物、商品、包装、文字、Logo、边框、装饰、侧边和页脚都必须原样保留；禁止修改、移动、重绘或遮挡任何原有元素。"
        "第2张是允许添加内容的空白区域原始背景，须延续其背景颜色、渐变和纹理，四边与原底稿自然衔接；不得画边框、拼接线、卡片底板或突兀色块。"
        "第3张起是可选卖点素材库。先判断完整元素的比例、信息价值和可用空间，只选适合此区域且不与原图冲突的元素；不要求用完所有素材。"
        "被选中的商品、人物、眼部对比、文字、Logo、图标及完整信息组合必须完整保留，不裁切、不截断、不遮挡、不拉伸、不变形。"
        "允许将完整元素等比缩小并调整新增元素之间的位置，但必须保持细节和文字可读；太大、比例不合适、缩小后不清楚或无法完整放下的元素，整项省略，不要截取局部，不要挤塞。"
        f"关键安全区：所有新增元素与四边至少保留 {margin} 像素呼吸空间，元素之间互不重叠遮挡，禁止出血、贴边和跨出区域。"
        "新增内容的色彩、字体气质、光影和视觉层级与第1张协调，主体优先，布局克制、自然，保留合理留白；可以少放，不必填满，不追求素材数量和覆盖率。"
        "只使用素材中真实可见的信息，不编造卖点、参数、认证、功效或文案；相同商品视角、元素、文案和卖点在整张图中只能出现一次，底稿已有的信息不再重复。"
        "可去掉素材原海报的纯背景以独立使用完整元素，但不能切掉元素本体、文字或其必要信息；无法完整分离的组合应整体保留或整体不采用。"
        "输出前检查完整性和留白：宁可减少元素，也不能为了填空间损坏素材，最终是一张无冲突、自然融合的 A+。\n"
        + build_a_plus_first_screen_user_override(str(job_context.get('a_plus_first_screen_requirements') or ''))
    )
    result = request_selling_points_layout(
        str(job_context['model']), prompt, [files[0], guide_input, *files[1:]], region_size, background,
    )
    outputs = []
    for url in result.get('images') or []:
        data, _ = load_image_bytes_from_url(url)
        with Image.open(io.BytesIO(data)) as image:
            designed = fit_selling_points_region(image, region_size, background)
        canvas = source.copy()
        # The whole rectangle is blank. No irregular mask can cut through a new element.
        canvas.paste(designed, (left, top))
        buffer = io.BytesIO()
        canvas.save(buffer, format='PNG')
        outputs.append(image_bytes_to_data_url(buffer.getvalue(), 'image/png'))
    if not outputs:
        raise RuntimeError("卖点区域未返回图片。")
    result['images'] = outputs
    result['target_size'] = list(source.size)
    result['first_screen_fill_bounds'] = list(bounds)
    return result


def build_a_plus_first_screen_user_override(custom_prompt: str) -> str:
    """Scope optional instructions to new material while retaining the immutable base."""
    normalized = str(custom_prompt or '').strip()
    if not normalized:
        return ''
    return '\n'.join([
        '【新增卖点补充要求】以下要求仅适用于空白区域中新加入的素材及布局：',
        normalized,
        '【底稿保护优先】补充要求不得修改、删除、重绘或遮挡第1张底稿任何已有元素；去文字、改色、重排等要求只能作用于新增卖点素材。无法满足时省略对应新增元素，不能突破完整保留、禁止裁切和空间限制。',
    ])
