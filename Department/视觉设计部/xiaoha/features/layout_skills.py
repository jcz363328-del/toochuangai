"""Store, resolve and render the structure of A+ layout skills."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any


def normalize_a_plus_layout_skill_analysis(
    payload,
    case_inputs,
    *,
    A_PLUS_SKILL_SCHEMA_VERSION,
    Any,
    _layout_skill_string_list,
    _layout_skill_text,
    _normalize_layout_skill_common,
    _normalize_layout_skill_elements,
    _normalize_layout_skill_hero,
    _normalize_layout_skill_sections,
    get_uploaded_input_dimensions,
) -> dict[str, Any]:
    raw_cases = list(payload.get("cases") or [])
    cases: list[dict[str, Any]] = []
    for index, case_input in enumerate(case_inputs):
        raw_case = raw_cases[index] if index < len(raw_cases) and isinstance(raw_cases[index], dict) else {}
        width, height = get_uploaded_input_dimensions(case_input)
        cases.append(
            {
                "case_index": index + 1,
                "canvas": {
                    "width": width,
                    "height": height,
                    "aspect_ratio": f"{width}:{height}",
                },
                "style": _layout_skill_text(raw_case.get("style"), 120),
                "design_strengths": _layout_skill_string_list(raw_case.get("design_strengths")),
                "hero": _normalize_layout_skill_hero(raw_case.get("hero")),
                "sections": _normalize_layout_skill_sections(raw_case.get("sections")),
                "typography": _normalize_layout_skill_common(
                    {"typography": raw_case.get("typography")}
                )["typography"],
                "background": _normalize_layout_skill_common(
                    {"background": raw_case.get("background")}
                )["background"],
                "reading_flow": _layout_skill_string_list(raw_case.get("reading_flow")),
                "cross_section_elements": _normalize_layout_skill_elements(
                    raw_case.get("cross_section_elements")
                ),
                "product_regions": _normalize_layout_skill_elements(
                    raw_case.get("product_regions")
                ),
            }
        )
    common = _normalize_layout_skill_common(payload.get("common"))
    return {
        "schema_version": A_PLUS_SKILL_SCHEMA_VERSION,
        "case_count": len(cases),
        "cases": cases,
        "common": common,
    }


def build_a_plus_layout_skill_prompt(
    analysis,
    *,
    A_PLUS_PRODUCT_LOCK_RULES,
    _layout_skill_string_list,
) -> str:
    common = dict(analysis.get("common") or {})
    hero = dict(common.get("hero") or {})
    typography = dict(common.get("typography") or {})
    background = dict(common.get("background") or {})
    section_lines = [
        (
            f"{index + 1}. {str(section.get('type') or 'content')}：高度占比约 "
            f"{float(section.get('height_ratio') or 0) * 100:.1f}%，"
            f"对齐={str(section.get('alignment') or '自然')}，"
            f"留白占比约 {float(section.get('whitespace_ratio') or 0) * 100:.1f}%"
        )
        for index, section in enumerate(list(common.get("sections") or []))
    ]
    strengths = "；".join(_layout_skill_string_list(common.get("design_strengths"))) or "保持清晰主次与连续阅读节奏"
    reading_flow = " → ".join(_layout_skill_string_list(common.get("reading_flow"))) or "首屏主视觉 → 卖点 → 细节 → 包装收尾"
    cross_rules = "；".join(_layout_skill_string_list(common.get("cross_section_rules"))) or "背景与视觉动线自然跨区"
    product_rules = "；".join(_layout_skill_string_list(common.get("product_placement_rules"))) or "产品完整、清晰且不被文案遮挡"
    anti_patterns = "；".join(_layout_skill_string_list(common.get("anti_patterns"))) or "素材堆叠、硬分割、文字拥挤"
    device_rules = "；".join(_layout_skill_string_list(common.get("device_rules"), 16))
    layout_rules = "；".join(_layout_skill_string_list(common.get("layout_rules"), 16))
    palette = "、".join(list(background.get("palette") or [])) or "跟随商品与品牌素材"
    preset_rules = ""
    if device_rules:
        preset_rules += f"\n端型适配规则：{device_rules}。"
    if layout_rules:
        preset_rules += f"\n模块编排规则：{layout_rules}。"
    return (
        "A+ 案例版式技能（只允许学习设计结构，禁止复制案例内容）：\n"
        f"共同设计风格：{str(common.get('style') or '专业电商 A+')}。\n"
        f"已验证的共同优点：{strengths}。\n"
        f"首屏高度占比约 {float(hero.get('height_ratio') or 0.3) * 100:.1f}%，"
        f"视觉中心={hero.get('visual_center') or [500, 250]}，产品位置={str(hero.get('product_position') or '主视觉区域')}，"
        f"模特位置={str(hero.get('model_position') or '与产品形成主次')}，文字区不超过 {int(hero.get('text_blocks') or 3)} 个，"
        f"文字面积约占首屏 {float(hero.get('text_area_ratio') or 0.15) * 100:.1f}%。\n"
        "内容阶段：\n" + "\n".join(section_lines) + "\n"
        f"字体层级：{' → '.join(list(typography.get('hierarchy') or [])) or '品牌 → 主标题 → 辅助文案'}；"
        f"密度={str(typography.get('density') or '低')}；对齐={str(typography.get('alignment') or '服从视觉动线')}；"
        f"主标题最多 {int(typography.get('max_title_lines') or 2)} 行。\n"
        f"背景配色={palette}；光影={str(background.get('lighting') or '统一光源')}；"
        f"装饰语言={str(background.get('decorative_language') or '克制')}；"
        f"空间层次={str(background.get('depth') or '前中后景清楚')}；"
        f"连续性={str(background.get('continuity') or '背景跨区连续')}。\n"
        f"阅读动线：{reading_flow}。\n跨区规则：{cross_rules}。\n产品布局原则：{product_rules}。\n"
        f"必须避免：{anti_patterns}。\n"
        f"{preset_rules}\n"
        "如果请求附带版式骨架图，它只表达抽象位置、比例、留白和层级；不得把骨架色块、边框或占位形状直接画进成品。"
        "绝对禁止识别、复用、模仿或输出优秀案例中的旧产品、旧人物、旧品牌、旧 Logo、旧文案、旧参数和旧价格。"
        "所有真实内容只能来自本次用户上传的商品与品牌素材。\n"
        + A_PLUS_PRODUCT_LOCK_RULES
    )


def build_a_plus_layout_skeleton_image(
    analysis,
    *,
    Image,
    ImageDraw,
    _layout_skill_bbox,
    io,
) -> bytes:
    cases = list(analysis.get("cases") or [])
    canvas_info = dict((cases[0] if cases else {}).get("canvas") or {})
    source_width = max(int(canvas_info.get("width") or 600), 1)
    source_height = max(int(canvas_info.get("height") or 1800), 1)
    scale = min(720 / source_width, 1600 / source_height)
    width = max(320, int(round(source_width * scale)))
    height = max(640, int(round(source_height * scale)))
    common = dict(analysis.get("common") or {})
    background = dict(common.get("background") or {})
    palette = list(background.get("palette") or [])
    base_color = palette[0] if palette else "#F4F0E8"
    try:
        image = Image.new("RGB", (width, height), base_color)
    except Exception:
        image = Image.new("RGB", (width, height), "#F4F0E8")
    draw = ImageDraw.Draw(image, "RGBA")
    section_colors = [
        (88, 117, 255, 34),
        (109, 208, 171, 34),
        (255, 184, 77, 34),
        (206, 112, 255, 34),
        (255, 112, 139, 34),
    ]
    element_colors = {
        "model": (82, 128, 255, 108),
        "product": (255, 132, 82, 132),
        "logo": (245, 198, 66, 132),
        "title": (121, 222, 183, 120),
        "selling_point": (171, 111, 255, 110),
        "detail": (72, 190, 218, 105),
        "package": (255, 97, 145, 112),
        "decoration": (150, 160, 180, 72),
        "other": (150, 160, 180, 72),
    }
    sections = list(common.get("sections") or [])
    current_y = 0
    for index, section in enumerate(sections):
        bbox = _layout_skill_bbox(section.get("bbox"))
        if bbox:
            left = round(bbox[0] / 1000 * width)
            top = round(bbox[1] / 1000 * height)
            right = round(bbox[2] / 1000 * width)
            bottom = round(bbox[3] / 1000 * height)
        else:
            section_height = round(float(section.get("height_ratio") or 0) * height)
            left, top, right, bottom = 0, current_y, width, min(height, current_y + section_height)
            current_y = bottom
        draw.rectangle((left, top, right, bottom), fill=section_colors[index % len(section_colors)])
        if index > 0:
            draw.line((0, top, width, top), fill=(255, 255, 255, 72), width=2)
        for element in list(section.get("elements") or []):
            element_bbox = _layout_skill_bbox(element.get("bbox"))
            if not element_bbox:
                continue
            element_type = str(element.get("type") or "other").lower()
            color = element_colors.get(element_type, element_colors["other"])
            box = (
                round(element_bbox[0] / 1000 * width),
                round(element_bbox[1] / 1000 * height),
                round(element_bbox[2] / 1000 * width),
                round(element_bbox[3] / 1000 * height),
            )
            draw.rounded_rectangle(box, radius=max(6, width // 60), fill=color, outline=(255, 255, 255, 150), width=2)
    for element in list(dict(common.get("hero") or {}).get("elements") or []):
        bbox = _layout_skill_bbox(element.get("bbox"))
        if not bbox:
            continue
        element_type = str(element.get("type") or "other").lower()
        color = element_colors.get(element_type, element_colors["other"])
        box = (
            round(bbox[0] / 1000 * width),
            round(bbox[1] / 1000 * height),
            round(bbox[2] / 1000 * width),
            round(bbox[3] / 1000 * height),
        )
        draw.rounded_rectangle(box, radius=max(6, width // 60), fill=color, outline=(255, 255, 255, 180), width=3)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def normalize_a_plus_layout_skill_account(account_name) -> str:
    return str(account_name or "admin").strip() or "admin"


def list_builtin_a_plus_layout_skills(
    *,
    A_PLUS_SHOP_STYLE_SKILL_CATALOG,
    A_PLUS_SKILL_DB_TYPE,
    A_PLUS_SKILL_MAX_CASES,
    A_PLUS_SKILL_SCHEMA_VERSION,
    Any,
    _layout_skill_string_list,
    _layout_skill_text,
    build_a_plus_layout_skill_prompt,
    json,
) -> list[dict[str, Any]]:
    if not A_PLUS_SHOP_STYLE_SKILL_CATALOG.is_file():
        return []
    try:
        catalog = json.loads(A_PLUS_SHOP_STYLE_SKILL_CATALOG.read_text(encoding="utf-8"))
    except Exception:
        return []
    if int(catalog.get("schema_version") or 0) != A_PLUS_SKILL_SCHEMA_VERSION:
        return []
    raw_stores = catalog.get("stores")
    if not isinstance(raw_stores, dict):
        return []
    skills: list[dict[str, Any]] = []
    for store_key in ("3", "15", "28"):
        for raw_skill in list(raw_stores.get(store_key) or []):
            if not isinstance(raw_skill, dict):
                continue
            skill_id = _layout_skill_text(raw_skill.get("skill_id"), 120)
            analysis = dict(raw_skill.get("analysis") or {})
            common = dict(analysis.get("common") or {})
            if not skill_id or not common:
                continue
            device = _layout_skill_text(raw_skill.get("device"), 24)
            target_size = (600, 1800) if device == "mobile" else (1464, 2400)
            skills.append(
                {
                    "schema_version": A_PLUS_SKILL_SCHEMA_VERSION,
                    "type": A_PLUS_SKILL_DB_TYPE,
                    "skill_id": skill_id,
                    "title": _layout_skill_text(raw_skill.get("title") or "店铺预置 A+ 风格", 120),
                    "created_at": "",
                    "created_by": "system",
                    "store_key": store_key,
                    "device": device,
                    "target_size": target_size,
                    "is_builtin": True,
                    "source_examples": _layout_skill_string_list(
                        raw_skill.get("source_examples"),
                        A_PLUS_SKILL_MAX_CASES,
                    ),
                    "analysis": analysis,
                    "common": common,
                    "skill_prompt": build_a_plus_layout_skill_prompt(analysis),
                }
            )
    return skills


def get_a_plus_layout_skill_user_pointer_path(
    account_name,
    *,
    A_PLUS_SKILL_ROOT,
    hashlib,
    normalize_a_plus_layout_skill_account,
) -> Path:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    account_hash = hashlib.sha1(normalized_account.casefold().encode("utf-8")).hexdigest()[:12]
    return A_PLUS_SKILL_ROOT / f"current_{account_hash}.json"


def register_a_plus_layout_skill_in_db(
    created_at,
    account_name,
    *,
    A_PLUS_SKILL_DB_TYPE,
    A_PLUS_SKILL_ROOT,
    execute_db_non_query,
    normalize_a_plus_layout_skill_account,
) -> None:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    execute_db_non_query(
        "INSERT INTO [AI_skills] ([Type], [LuJin], [YongHu], [RiQi]) VALUES (%s, %s, %s, %s)",
        (
            A_PLUS_SKILL_DB_TYPE,
            str(A_PLUS_SKILL_ROOT),
            normalized_account,
            created_at.date(),
        ),
    )


def list_a_plus_layout_skills(
    account_name,
    *,
    A_PLUS_SKILL_DB_TYPE,
    A_PLUS_SKILL_ROOT,
    Any,
    json,
    normalize_a_plus_layout_skill_account,
) -> list[dict[str, Any]]:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    root = A_PLUS_SKILL_ROOT
    if not root.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for manifest_path in root.glob("*/manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("type") or "") != A_PLUS_SKILL_DB_TYPE:
            continue
        owner = normalize_a_plus_layout_skill_account(str(payload.get("created_by") or ""))
        if owner.casefold() != normalized_account.casefold():
            continue
        payload["manifest_path"] = str(manifest_path)
        manifests.append(payload)
    manifests.sort(
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("skill_id") or "")),
        reverse=True,
    )
    return manifests


def list_available_a_plus_layout_skills(
    account_name,
    *,
    list_a_plus_layout_skills,
    list_builtin_a_plus_layout_skills,
) -> list[dict[str, Any]]:
    return [
        *list_builtin_a_plus_layout_skills(),
        *list_a_plus_layout_skills(account_name),
    ]


def load_latest_a_plus_layout_skill(
    account_name,
    *,
    list_a_plus_layout_skills,
) -> dict[str, Any]:
    skills = list_a_plus_layout_skills(account_name)
    return dict(skills[0]) if skills else {}


def load_a_plus_layout_skill(
    account_name,
    skill_id,
    *,
    list_a_plus_layout_skills,
    list_builtin_a_plus_layout_skills,
) -> dict[str, Any]:
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        return {}
    builtin_skill = next(
        (
            dict(skill)
            for skill in list_builtin_a_plus_layout_skills()
            if str(skill.get("skill_id") or "") == normalized_skill_id
        ),
        {},
    )
    if builtin_skill:
        return builtin_skill
    return next(
        (
            dict(skill)
            for skill in list_a_plus_layout_skills(account_name)
            if str(skill.get("skill_id") or "") == normalized_skill_id
        ),
        {},
    )


def parse_a_plus_layout_skill_created_date(
    manifest,
    *,
    Path,
    datetime,
) -> date:
    created_at_text = str(manifest.get("created_at") or "").strip()
    if created_at_text:
        try:
            return datetime.fromisoformat(created_at_text).date()
        except ValueError:
            pass
    manifest_path = Path(str(manifest.get("manifest_path") or ""))
    if manifest_path.exists():
        return datetime.fromtimestamp(manifest_path.stat().st_mtime).date()
    return datetime.now().date()


def update_a_plus_layout_skill_user_pointer(
    account_name,
    *,
    datetime,
    get_a_plus_layout_skill_user_pointer_path,
    json,
    load_latest_a_plus_layout_skill,
    normalize_a_plus_layout_skill_account,
) -> None:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    pointer_path = get_a_plus_layout_skill_user_pointer_path(normalized_account)
    latest_skill = load_latest_a_plus_layout_skill(normalized_account)
    if not latest_skill:
        pointer_path.unlink(missing_ok=True)
        return
    pointer_path.write_text(
        json.dumps(
            {
                "skill_id": str(latest_skill.get("skill_id") or ""),
                "created_by": normalized_account,
                "manifest_path": str(latest_skill.get("manifest_path") or ""),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def delete_a_plus_layout_skill(
    account_name,
    skill_id,
    *,
    A_PLUS_SKILL_DB_TYPE,
    A_PLUS_SKILL_ROOT,
    Path,
    execute_db_non_query,
    load_a_plus_layout_skill,
    normalize_a_plus_layout_skill_account,
    parse_a_plus_layout_skill_created_date,
    shutil,
    update_a_plus_layout_skill_user_pointer,
    uuid4,
) -> dict[str, Any]:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    normalized_skill_id = str(skill_id or "").strip()
    if not normalized_skill_id:
        raise RuntimeError("请选择要删除的 A+ 版式 Skill。")

    manifest = load_a_plus_layout_skill(normalized_account, normalized_skill_id)
    if not manifest:
        raise RuntimeError("未找到属于当前账号的 A+ 版式 Skill，无法删除。")
    if bool(manifest.get("is_builtin")):
        raise RuntimeError("店铺预置 A+ 版式 Skill 不能删除。")
    owner = normalize_a_plus_layout_skill_account(str(manifest.get("created_by") or ""))
    if owner.casefold() != normalized_account.casefold():
        raise RuntimeError("只能删除当前账号自己创建的 A+ 版式 Skill。")

    root = A_PLUS_SKILL_ROOT.resolve()
    manifest_path = Path(str(manifest.get("manifest_path") or "")).resolve()
    skill_dir = manifest_path.parent
    if (
        manifest_path.name != "manifest.json"
        or skill_dir.parent != root
        or skill_dir.name != normalized_skill_id
        or not manifest_path.is_file()
    ):
        raise RuntimeError("A+ 版式 Skill 路径校验失败，已阻止删除。")

    trash_root = root / ".delete_staging"
    trash_root.mkdir(parents=True, exist_ok=True)
    staged_dir = trash_root / f"{normalized_skill_id}_{uuid4().hex}"
    skill_dir.rename(staged_dir)
    created_date = parse_a_plus_layout_skill_created_date(manifest)
    try:
        execute_db_non_query(
            "DELETE TOP (1) FROM [AI_skills] "
            "WHERE [Type] = %s AND [LuJin] = %s AND [YongHu] = %s "
            "AND CAST([RiQi] AS date) = %s",
            (
                A_PLUS_SKILL_DB_TYPE,
                str(A_PLUS_SKILL_ROOT),
                normalized_account,
                created_date,
            ),
        )
    except Exception:
        staged_dir.rename(skill_dir)
        raise

    cleanup_warning = ""
    try:
        shutil.rmtree(staged_dir)
    except OSError as exc:
        cleanup_warning = f"Skill 已从列表删除，但暂存文件清理失败：{exc}"
    update_a_plus_layout_skill_user_pointer(normalized_account)
    return {
        "skill_id": normalized_skill_id,
        "title": str(manifest.get("title") or "A+ 版式技能"),
        "created_by": normalized_account,
        "cleanup_warning": cleanup_warning,
    }


def save_a_plus_layout_skill(
    case_inputs,
    analysis,
    title,
    account_name,
    *,
    A_PLUS_SKILL_DB_TYPE,
    A_PLUS_SKILL_MAX_CASES,
    A_PLUS_SKILL_ROOT,
    A_PLUS_SKILL_SCHEMA_VERSION,
    Any,
    Path,
    _layout_skill_text,
    build_a_plus_layout_skeleton_image,
    build_a_plus_layout_skill_prompt,
    datetime,
    get_a_plus_layout_skill_user_pointer_path,
    get_uploaded_file_bytes,
    get_uploaded_file_name,
    hashlib,
    json,
    load_latest_a_plus_layout_skill,
    normalize_a_plus_layout_skill_account,
    register_a_plus_layout_skill_in_db,
    sanitize_file_name,
) -> dict[str, Any]:
    normalized_inputs = list(case_inputs or [])[:A_PLUS_SKILL_MAX_CASES]
    if not normalized_inputs:
        raise RuntimeError("没有可保存的优秀 A+ 案例。")
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    created_at = datetime.now()
    A_PLUS_SKILL_ROOT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(
        b"".join(get_uploaded_file_bytes(item) for item in normalized_inputs)
    ).hexdigest()[:10]
    safe_title = sanitize_file_name(title or "a_plus_layout_skill")
    skill_id = f"{created_at.strftime('%Y%m%d_%H%M%S_%f')}_{safe_title}_{digest}"
    skill_dir = A_PLUS_SKILL_ROOT / skill_id
    cases_dir = skill_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=False)
    source_files: list[dict[str, Any]] = []
    for index, case_input in enumerate(normalized_inputs, start=1):
        original_name = Path(get_uploaded_file_name(case_input) or f"case_{index}.png").name
        safe_name = sanitize_file_name(original_name)
        if not Path(safe_name).suffix:
            safe_name += ".png"
        saved_name = f"{index:02d}_{safe_name}"
        saved_path = cases_dir / saved_name
        source_bytes = get_uploaded_file_bytes(case_input)
        saved_path.write_bytes(source_bytes)
        source_files.append(
            {
                "index": index,
                "file": str(saved_path),
                "sha1": hashlib.sha1(source_bytes).hexdigest(),
            }
        )
    skeleton_path = skill_dir / "layout_skeleton.png"
    skeleton_path.write_bytes(build_a_plus_layout_skeleton_image(analysis))
    skill_prompt = build_a_plus_layout_skill_prompt(analysis)
    skill_prompt_path = skill_dir / "A_PLUS_LAYOUT_SKILL.md"
    skill_prompt_path.write_text(skill_prompt, encoding="utf-8")
    previous_skill = load_latest_a_plus_layout_skill(normalized_account)
    manifest_path = skill_dir / "manifest.json"
    manifest = {
        "schema_version": A_PLUS_SKILL_SCHEMA_VERSION,
        "type": A_PLUS_SKILL_DB_TYPE,
        "skill_id": skill_id,
        "title": _layout_skill_text(title or "A+ 优秀案例版式技能", 120),
        "created_at": created_at.isoformat(timespec="seconds"),
        "created_by": normalized_account,
        "root_path": str(A_PLUS_SKILL_ROOT),
        "manifest_path": str(manifest_path),
        "skeleton_path": str(skeleton_path),
        "skill_prompt_path": str(skill_prompt_path),
        "parent_skill_id": str(previous_skill.get("skill_id") or ""),
        "source_files": source_files,
        "analysis": analysis,
        "common": dict(analysis.get("common") or {}),
        "skill_prompt": skill_prompt,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    register_a_plus_layout_skill_in_db(created_at, normalized_account)
    get_a_plus_layout_skill_user_pointer_path(normalized_account).write_text(
        json.dumps(
            {
                "skill_id": skill_id,
                "created_by": normalized_account,
                "manifest_path": str(manifest_path),
                "updated_at": created_at.isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def create_a_plus_layout_skill(
    case_inputs,
    title,
    account_name,
    *,
    analyze_a_plus_layout_cases,
    load_latest_a_plus_layout_skill,
    normalize_a_plus_layout_skill_account,
    save_a_plus_layout_skill,
) -> dict[str, Any]:
    normalized_account = normalize_a_plus_layout_skill_account(account_name)
    previous_skill = load_latest_a_plus_layout_skill(normalized_account)
    previous_common = (
        dict(previous_skill.get("common") or {})
        if isinstance(previous_skill.get("common"), dict)
        else {}
    )
    analysis = analyze_a_plus_layout_cases(case_inputs, previous_common=previous_common)
    return save_a_plus_layout_skill(
        case_inputs,
        analysis,
        title=title,
        account_name=normalized_account,
    )


def get_active_a_plus_layout_skill_context(
    account_name,
    selected_skill_id,
    *,
    Any,
    Path,
    build_a_plus_layout_skeleton_image,
    load_a_plus_layout_skill,
    load_latest_a_plus_layout_skill,
) -> dict[str, Any]:
    if selected_skill_id is not None and not str(selected_skill_id or "").strip():
        return {}
    manifest = (
        load_a_plus_layout_skill(account_name, str(selected_skill_id or ""))
        if selected_skill_id is not None
        else load_latest_a_plus_layout_skill(account_name)
    )
    if not manifest:
        return {}
    prompt = str(manifest.get("skill_prompt") or "").strip()
    is_builtin = bool(manifest.get("is_builtin"))
    if is_builtin:
        skeleton_analysis = dict(manifest.get("analysis") or {})
        skeleton_cases = [dict(item) for item in list(skeleton_analysis.get("cases") or [])]
        target_size = tuple(manifest.get("target_size") or ())
        if skeleton_cases and len(target_size) == 2:
            target_width, target_height = (max(int(value), 1) for value in target_size)
            skeleton_cases[0]["canvas"] = {
                "width": target_width,
                "height": target_height,
                "aspect_ratio": f"{target_width}:{target_height}",
            }
            skeleton_analysis["cases"] = skeleton_cases
        skeleton: Path | dict[str, Any] | None = {
            "name": f"{str(manifest.get('skill_id') or 'shop_style')}_layout_skeleton.png",
            "type": "image/png",
            "data": build_a_plus_layout_skeleton_image(skeleton_analysis),
        }
    else:
        skeleton_path = Path(str(manifest.get("skeleton_path") or ""))
        skeleton = skeleton_path if skeleton_path.exists() and skeleton_path.is_file() else None
    return {
        "skill_id": str(manifest.get("skill_id") or ""),
        "title": str(manifest.get("title") or "A+ 版式技能"),
        "created_at": str(manifest.get("created_at") or ""),
        "created_by": str(manifest.get("created_by") or ""),
        "store_key": str(manifest.get("store_key") or ""),
        "device": str(manifest.get("device") or ""),
        "target_size": tuple(manifest.get("target_size") or ()),
        "is_builtin": is_builtin,
        "prompt": prompt,
        "skeleton": skeleton,
        "common": dict(manifest.get("common") or {}),
    }


def resolve_a_plus_layout_skill_context_for_layout(
    context,
    layout,
    *,
    account_name,
    get_active_a_plus_layout_skill_context,
    get_main_image_a_plus_layout_device,
    list_builtin_a_plus_layout_skills,
) -> dict[str, Any]:
    """Keep an explicit style choice, but automatically use its matching device variant."""
    resolved_context = dict(context or {})
    if not resolved_context:
        return {}
    target_device = get_main_image_a_plus_layout_device(layout)
    context_device = str(resolved_context.get("device") or "").strip().lower()
    if not target_device or not context_device or context_device == target_device:
        return resolved_context
    if not bool(resolved_context.get("is_builtin")):
        return {}
    store_key = str(resolved_context.get("store_key") or "").strip()
    matching_skill = next(
        (
            skill
            for skill in list_builtin_a_plus_layout_skills()
            if str(skill.get("store_key") or "") == store_key
            and str(skill.get("device") or "").strip().lower() == target_device
        ),
        None,
    )
    if not matching_skill:
        return {}
    return get_active_a_plus_layout_skill_context(
        account_name,
        str(matching_skill.get("skill_id") or ""),
    )
