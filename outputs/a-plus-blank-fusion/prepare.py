import ast,difflib
from pathlib import Path
root=Path('outputs/a-plus-blank-fusion')
replacement=(root/'replacement_functions.py').read_text(encoding='utf-8')
def functions(text):
 lines=text.splitlines(True)
 return {n.name:''.join(lines[n.lineno-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
new=functions(replacement)
def rewrite(source):
 old=functions(source)
 for name,code in new.items():
  if name=='find_first_screen_safe_region':continue
  assert source.count(old[name])==1,name
  source=source.replace(old[name],code)
 anchor=new['build_first_screen_fill_mask']
 source=source.replace(anchor,anchor+'\n\n\n'+new['find_first_screen_safe_region'])
 tree=ast.parse(source)
 features=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='FEATURES' for t in n.targets))
 node=next(n for n in features.elts if isinstance(n,ast.Dict) and any(isinstance(v,ast.Name) and v.id=='A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY' for v in n.values))
 old_feature=ast.get_source_segment(source,node)
 feature='''{
        "key": A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY,
        "name": "A+首屏卖点融合",
        "summary": "底稿元素原样保留，只在空白区自然加入完整卖点",
        "mode": "openrouter",
        "output_mode": "image",
        "min_images": 2,
        "max_input_images": 10,
        "max_output_images": 1,
        "target_size": (1464, 2400),
        "target_size_text": "",
        "description": "第一张底稿的所有已有元素保持不变且不受遮挡；只在安全空白区域加入完整、合适的卖点素材，放不下则省略，不裁切、不强行填满。尺寸和比例跟随底稿。",
        "default_prompt": (
            "第1张图是不可修改的完整A+底稿，所有人物、商品、文字、Logo、背景装饰、侧边和页脚均原样保留，不得重绘、移动、调色、删改、裁切、重排或遮挡任何已有元素。"
            "只在第1张图真实空白且能完整容纳元素的区域，选择性加入后续卖点素材，不要求用完全部素材。"
            "被采用的元素和必要信息必须完整，不裁切、不截断、不遮挡、不拉伸；只能合理等比缩小，若太大、比例不适合或缩小后难以辨认，则整体省略。"
            "新增元素与底稿统一色彩、光影、字体气质及视觉层级，保持适当间距和自然留白，不强行填满、不做机械拼贴、不与原有设计冲突。"
            "只使用真实可见的卖点和文案，不编造信息、不重复已有内容。补充要求仅适用于新增素材，不能改变底稿保护规则。"
            "最终画布沿用第1张图的原始像素尺寸和宽高比例，不扩图、不裁图，输出一张自然协调的完整A+。"
        ),
    }'''
 source=source.replace(old_feature,feature)
 replacements={
  '无法自动确认下方填充区域，请填写“首屏保留高度”，指定从哪里开始填充；背景不限颜色。':'未检测到足够的安全填充区域，请使用留白更充足的底稿；不会自动覆盖已有元素。',
  '首屏保留高度（px，0 为自动识别）':'填充起始高度（px，0 为自动识别）',
  '自动识别不准时，填写原图中首屏结束的位置；该位置以上保持不变。':'仅允许在此高度以下的安全空白区域加入素材；原图任何已有元素仍保持不变，不会因设置高度而被覆盖。',
  '只在下方连续纯色留白内自由组合卖点，保持底稿原始尺寸、原始首屏位置和边界。':'只在确认安全的空白区域选择性加入完整卖点，保持整张底稿尺寸、位置和已有元素。',
  '允许对卖点进行自由编排，但不编造信息，不重复卖点，不改变首屏任何人物、文字、商品、色彩或布局。':'素材必须完整不裁切、不遮挡；太大或放不下则省略，允许少放和留白，不编造或重复信息，不改变底稿任何元素。',
  '最终硬性规则：第1张底稿首屏已有内容完全不变，任何补充要求不得覆盖此规则。':'最终硬性规则：第1张底稿的所有已有元素完全不变且不受遮挡，任何补充要求不得覆盖此规则。',
 }
 for a,b in replacements.items():
  assert source.count(a)==1,(a,source.count(a))
  source=source.replace(a,b)
 a='            if supports_a_plus_first_screen_selling_points:\n                if a_plus_first_screen_workflow_stage == "hero":'
 start=source.index(a)
 end=source.index('            if supports_remove_eyelashes:',start)
 source=source[:start]+'''            if supports_a_plus_first_screen_selling_points:
                feature_for_request["default_prompt"] = feature["default_prompt"]
'''+source[end:]
 # No historical workflow stage may bypass the immutable-base compositor.
 a='if (feature_key == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY\n            and job_context.get("a_plus_first_screen_workflow_stage") != "hero"):'
 assert source.count(a)==1
 source=source.replace(a,'if feature_key == A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY:')
 # Put the product contract beside the actual input controls.
 a='        elif supports_a_plus_first_screen_selling_points:\n            hero_upload_key ='
 assert source.count(a)==1
 source=source.replace(a,'''        elif supports_a_plus_first_screen_selling_points:
            st.caption("底稿已有元素不变、不遮挡；只在空白区域加入完整卖点，放不下的素材会省略，不强行填满。")
            hero_upload_key =''')
 ast.parse(source)
 return source
for label,path in [('local',Path('图片/openrouter_image_site.py')),('runtime',root/'runtime-patched.py'),('image',root/'image-patched.py')]:
 before=(root/f'before-{label}.py').read_text(encoding='utf-8-sig')
 after=rewrite(before)
 path.write_text(after,encoding='utf-8',newline='\n')
 (root/f'{label}.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=f'before-{label}.py',tofile=path.name)),encoding='utf-8')
 print(label,'patched',len(after))
