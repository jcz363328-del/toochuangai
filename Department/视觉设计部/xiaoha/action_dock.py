"""Shared bottom-right positioning for the image workbench action groups."""

ACTION_DOCK_CSS = '''
<style>
:is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) {
    position:fixed!important;transform:none!important;
    inset:auto max(20px, env(safe-area-inset-right)) max(20px, env(safe-area-inset-bottom)) auto!important;
    width:min(960px, calc(100vw - 40px))!important;
    max-width:calc(100vw - 40px)!important;
    max-height:45dvh;overflow-y:auto;
    z-index:1000!important;
    margin:0!important;padding:12px 16px!important;
    background:rgba(12,20,40,.98)!important;
    border:1px solid #3c4169!important;border-radius:14px!important;
    box-shadow:0 8px 32px #0006;
}
:root body:has(:is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock)) .block-container {
    padding-bottom:220px!important;
}
@media(min-width:768px) {
    body:has([data-testid="stSidebar"][aria-expanded="true"]) :is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) {
        max-width:calc(100vw - 340px)!important;
    }
}
@media(max-width:767px) {
    :is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) {
        inset:auto max(12px, env(safe-area-inset-right)) max(12px, env(safe-area-inset-bottom)) auto!important;
        width:calc(100vw - 24px)!important;max-width:calc(100vw - 24px)!important;
        padding:10px 12px!important;
    }
    :is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) [data-testid="stHorizontalBlock"] {
        flex-wrap:wrap!important;gap:8px!important;
    }
    :is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) [data-testid="stColumn"] {
        width:auto!important;min-width:0!important;flex:1 1 100%!important;
    }
}
</style>
'''


def inject_action_dock_styles(st):
    st.markdown(ACTION_DOCK_CSS, unsafe_allow_html=True)
    import json
    from pathlib import Path
    import streamlit.components.v1 as components
    script = Path(__file__).with_name("action_dock_menu.js").read_text(encoding="utf-8")
    components.html('<script>const s=window.parent.document.createElement("script");'
                    + 's.textContent=' + json.dumps(script).replace('</', r'<\/')
                    + ';window.parent.document.head.appendChild(s);s.remove();</script>', height=0)


def generation_action_column(st, dock):
    """Place model and resolution immediately to the left of processing actions."""
    from .generation_settings import IMAGE_MODELS, DEFAULT_IMAGE_MODEL, resolution_options
    feature_key = str(st.session_state.get("selected_feature_key") or "")
    if feature_key in {"image_resize", "image_smart_analysis", "jimeng_hd_upscale", "prepress_check"}:
        return dock
    choices = st.session_state.setdefault("generation_choices", {})
    saved = choices.get(feature_key, {})
    with dock:
        model_col, resolution_col, action_col = st.columns([2.2, 1, 2], gap="small", vertical_alignment="bottom")
        with model_col:
            model_key = "generation_model_" + feature_key
            if st.session_state.get(model_key) not in IMAGE_MODELS:
                previous = saved.get("model", DEFAULT_IMAGE_MODEL)
                st.session_state[model_key] = previous if previous in IMAGE_MODELS else DEFAULT_IMAGE_MODEL
            model = st.selectbox("模型", list(IMAGE_MODELS), format_func=IMAGE_MODELS.get, key=model_key)
        with resolution_col:
            options = resolution_options(model)
            size_key = "generation_resolution_" + feature_key
            if st.session_state.get(size_key) not in options:
                st.session_state[size_key] = saved.get("resolution", "2K") if saved.get("resolution", "2K") in options else "2K"
            resolution = st.selectbox("分辨率", options, key=size_key,
                                      help="GPT 档位预设：1K 为 1024×1024，2K 为 2048×2048，4K 方图为 2880×2880；16:9 的 4K 为 3840×2160。" if model.startswith("gpt-image-") else None)
        choices[feature_key] = {"model": model, "resolution": resolution}
    return action_col
