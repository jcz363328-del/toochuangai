"""Open the dedicated A+ node canvas."""
FEATURE_KEY = "a_plus_canvas"


def render(api, feature, model, aspect_ratio):
    api.st.caption("添加A+功能节点，将素材图片按顺序连入节点；生成结果会返回画布，可继续连接下一步。")
    api.render_replacement_infinite_canvas_feature(feature)
