from pathlib import Path
p=Path('图片/openrouter_image_site.py');s=p.read_text(encoding='utf-8')
# All native upload call sites, including replacements, use the same frame.
s=s.replace('st.file_uploader(', 'render_frame_uploader(')
anchor='def render_single_image_uploader(\n'
helper='''def render_frame_uploader(label: str, **kwargs):
    from 图片.upload_frames import render_file_frame
    return render_file_frame(SimpleNamespace(**globals()), label, **kwargs)


'''
s=s.replace(anchor,helper+anchor,1)
start=s.index('    with st.container(height=400, border=False):',s.index('def render_single_image_uploader'))
end=s.index('    st.caption("支持 Ctrl+V',start)
s=s[:start]+'''    uploaded = render_frame_uploader(
        label, type=["png", "jpg", "jpeg", "webp"],
        key=get_uploader_widget_key(key), preview_files=cached_files, frame_height=350,
        help=help_text or None, label_visibility="collapsed",
    )
    if uploaded is not None:
        consume_pending_upload_replacement(key)
        save_upload_cache(key, [uploaded])
        reset_upload_widget(key)
        st.rerun()
    if active_uploaded is not None:
        with st.popover("放大查看"):
            render_zoomable_image_gallery([uploaded_input_to_data_url(active_uploaded)], columns=1,
                thumb_height=500, component_key=f"single_preview_{key}", fit_mode="contain", max_width_percent=100)
    if st.button("清空上传", key=f"clear_upload_{key}", type="secondary"):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

'''+s[end:]
start=s.index('    if active_uploaded is not None:\n        render_zoomable_image_gallery(',s.index('def render_compact_element_image_uploader'))
end=s.index('    uploaded = render_frame_uploader(',start)
s=s[:start]+s[end:]
pos=s.index('def render_compact_element_image_uploader')
end=s.index('\ndef render_first_screen_material_uploader',pos)
part=s[pos:end].replace('        key=get_uploader_widget_key(key),','        key=get_uploader_widget_key(key), preview_files=cached_files, frame_height=220,',1)
s=s[:pos]+part+s[end:]
# Empty multi-image view is the drop frame itself; keep gallery only when populated.
start=s.index('    # Reserve the same space',s.index('def render_multi_image_uploader'))
end=s.index('        if uploaded_files:',start)
s=s[:start]+'''    if active_uploaded_files:
        preview_area_height = preview_area_height or (560 if preview_renderer is not None else 420)
        with st.container(height=preview_area_height, border=False):
            render_uploaded_gallery(active_uploaded_files, key, preview_renderer=preview_renderer,
                                    slot_count=preview_slot_count, allow_reorder=allow_reorder)
    uploaded_files = render_frame_uploader(
        label, type=["png", "jpg", "jpeg", "webp"], key=get_uploader_widget_key(key),
        help=help_text or None, label_visibility="collapsed", accept_multiple_files=True,
        frame_height=200 if active_uploaded_files else 350,
    ) or []
    if True:
'''+s[end:]
# Remove the old two-column control scope but retain the actual cache/append logic.
start=s.index('    with action_right:',s.index('def render_multi_image_uploader'))
end=s.index('    st.caption("支持 Ctrl+V',start)
s=s[:start]+'''    if st.button("清空上传", key=f"clear_upload_{key}", type="secondary"):
        clear_upload_cache(key)
        reset_upload_widget(key)
        st.rerun()

'''+s[end:]
# Reference slots need one image frame, instead of a preview and a tiny upload button.
start=s.index('            if active_uploaded is not None:',s.index('def render_reference_slot_uploaders'))
end=s.index('            uploaded = render_frame_uploader(',start)
s=s[:start]+'''            if active_uploaded is not None:
                uploaded_files.append(active_uploaded)

'''+s[end:]
pos=s.index('def render_reference_slot_uploaders');end=s.index('\ndef build_result_download_sources',pos)
part=s[pos:end].replace('                key=get_uploader_widget_key(slot_key),','                key=get_uploader_widget_key(slot_key), preview_files=cached_files, frame_height=220,',1)
s=s[:pos]+part+s[end:]
p.write_text(s,encoding='utf-8')
# Poster fusion uses the same primitive so all upload frames stay consistent.
p=Path('图片/poster_fusion.py');s=p.read_text(encoding='utf-8');start=s.index('def render_image_slot(');end=s.index('\ndef render(api, feature):',start)
s=s[:start]+'''def render_image_slot(api, label, key, height=320):
    from 图片.upload_frames import render_file_frame
    return render_file_frame(api, label, key=key, type=["jpg", "jpeg", "png", "webp"], frame_height=height)

'''+s[end:];p.write_text(s,encoding='utf-8')
