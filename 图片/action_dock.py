"""Shared bottom-right positioning for the image workbench action groups."""

ACTION_DOCK_CSS = '''
<style>
:is(.st-key-workbench_action_dock.st-key-workbench_action_dock, .st-key-fusion_action_dock.st-key-fusion_action_dock) {
    position:fixed!important;transform:none!important;
    inset:auto max(20px, env(safe-area-inset-right)) max(20px, env(safe-area-inset-bottom)) auto!important;
    width:min(640px, calc(100vw - 40px))!important;
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
