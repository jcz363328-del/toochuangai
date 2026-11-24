"""A+ workspace: reuse the canvas and existing A+ workflows."""

FEATURE_KEY = "a_plus_canvas"


def render(api, feature, model, aspect_ratio):
    st = api.st
    keys = next((keys for name, keys in api.SIDE_MENU_FEATURE_GROUPS if name == "A+"), ())
    tools = {key: api.get_feature_by_key(key) for key in keys if key != FEATURE_KEY}
    tools = {key: item for key, item in tools.items() if item and not item.get("hidden")}
    st.subheader("A+画布")
    st.caption("在画布中整理素材、编排画面；通过下方工具切换使用 A+ 创作功能。")
    selected = st.selectbox(
        "A+工作区", ["canvas", *tools],
        format_func=lambda key: "画布 · 素材与画面编排" if key == "canvas" else str(tools[key]["name"]),
        key="a_plus_canvas_tool",
    )
    if selected == "canvas":
        api.render_replacement_infinite_canvas_feature(feature)
    else:
        api.render_openrouter_feature(tools[selected], model=model, aspect_ratio=aspect_ratio)
