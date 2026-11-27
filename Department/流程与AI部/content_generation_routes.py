"""Generate scripts and images from the portal creator pages."""

from __future__ import annotations


def script_generator(*, render_template):
    """脚本生成器页面"""
    return render_template('流程与AI部/script_generator.html')


def generate_script(
    *,
    _safe_debug_print,
    call_ai_api,
    concurrent,
    jsonify,
    request,
):
    """生成脚本API（并发优化版）"""

    try:
        data = request.get_json()
        product_name = data.get('product_name', '').strip()
        features = data.get('features', [])
        quantity = int(data.get('quantity', 1))

        if not product_name or not features:
            return jsonify({
                'success': False,
                'message': '请提供完整的产品信息'
            })

        # 使用并发处理来加速脚本生成
        def generate_single_script(script_number):
            try:
                script = call_ai_api(product_name, features, script_number)
                return {
                    'number': script_number,
                    'content': script
                }
            except Exception as script_error:
                _safe_debug_print(f"生成第{script_number}个脚本时出错: {str(script_error)}")
                return {
                    'number': script_number,
                    'content': f"脚本生成失败: {str(script_error)}"
                }

        # 使用线程池并发生成脚本
        script_numbers = list(range(1, quantity + 1))
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, quantity)) as executor:
            future_to_script = {executor.submit(generate_single_script, num): num for num in script_numbers}
            scripts = []

            for future in concurrent.futures.as_completed(future_to_script):
                script_result = future.result()
                scripts.append(script_result)

        # 按脚本编号排序
        scripts.sort(key=lambda x: x['number'])

        return jsonify({
            'success': True,
            'scripts': scripts
        })

    except Exception as e:
        _safe_debug_print(f"生成脚本API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'生成脚本时发生错误: {str(e)}'
        })


def generate_cache_key(
    product_name,
    features,
    script_number,
):
    """生成缓存键"""
    features_str = "|".join(sorted(features))
    return f"{product_name}_{features_str}_{script_number}"


def call_ai_api(
    product_name,
    product_features,
    script_number,
    *,
    _OPENAI_TEXT_MODEL_CANDIDATES,
    _ai_chat_complete,
    _safe_debug_print,
    cache_lock,
    generate_cache_key,
    script_cache,
):
    """调用AI API生成脚本（带缓存）"""
    try:
        # 检查缓存
        cache_key = generate_cache_key(product_name, product_features, script_number)
        with cache_lock:
            if cache_key in script_cache:
                _safe_debug_print(f"使用缓存脚本: {cache_key}")
                return script_cache[cache_key]

        features_text = "、".join(product_features)

        style_variations = [
            "充满激情和感染力",
            "更加生动活泼",
            "富有创意和想象力",
            "更具说服力",
            "更加幽默风趣"
        ]

        current_style = style_variations[(script_number - 1) % len(style_variations)]

        prompt = f"""
你是一位专业的美国TIKTOk短视频脚本撰写专家。请为以下假睫毛产品创作一个吸引人的口播脚本：

产品名称：{product_name}
产品特征：{features_text}

要求：
1. 脚本要适合TIKTOK美国达人的风格，{current_style}要沉浸式
2. 突出产品的独特卖点和优势
3. 语言要生动有趣，能够吸引观众注意力
4. 包含产品使用效果的描述
5. 脚本长度控制在30-60秒的口播时间
6. 使用英文撰写，符合美国观众的语言习惯
7. 包含适当的情感渲染和互动元素
8. 这是第{script_number}个版本，请确保与之前的版本有所不同

请生成一个完整的口播脚本：
"""

        messages = [
            {
                "role": "system",
                "content": "You are a professional script writer for TikTok, specializing in creating engaging and passionate product presentations for eyelash products."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        script_content = _ai_chat_complete(
            messages,
            max_tokens=800,
            temperature=0.8,
            model_candidates=_OPENAI_TEXT_MODEL_CANDIDATES
        )

        # 缓存结果
        with cache_lock:
            script_cache[cache_key] = script_content
            # 限制缓存大小
            if len(script_cache) > 100:
                # 删除最旧的缓存项
                oldest_key = next(iter(script_cache))
                del script_cache[oldest_key]

        return script_content

    except Exception as e:
        _safe_debug_print(f"AI API调用错误: {str(e)}")
        # 返回一个默认的脚本模板
        return f"""
Hey TikTok fam! 🔥 Let me tell you about these AMAZING {product_name}! 

These lashes are absolutely STUNNING and will transform your entire look! ✨ 
{', '.join(product_features)} - can you believe it?!

I'm literally obsessed with how natural yet dramatic they look! 
Your eyes will POP and everyone will be asking where you got them! 💫

Trust me, once you try these, you'll never go back to your old lashes! 
Who's ready to level up your lash game? Drop a 💕 if you want the link!

#FalseLashes #BeautyTips #LashGoals #MakeupHacks
"""


def image_generator(*, render_template):
    """图像生成器页面"""
    return render_template('流程与AI部/image_generator.html')


def generate_image(
    *,
    client,
    jsonify,
    request,
):
    """生成图像API"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        size = data.get('size', '1024x1024')
        quality = data.get('quality', 'standard')

        if not prompt:
            return jsonify({
                'success': False,
                'message': '请提供图像描述'
            })

        # 调用DALL-E 3 API生成图像
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size=size,
            quality=quality
        )

        image_url = response.data[0].url

        return jsonify({
            'success': True,
            'image_url': image_url,
            'prompt': prompt,
            'size': size,
            'quality': quality
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'生成图像时发生错误: {str(e)}'
        })
