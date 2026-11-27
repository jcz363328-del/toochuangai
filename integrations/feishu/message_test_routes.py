"""Feishu video card test endpoints."""

from __future__ import annotations


def feishu_video_card_test_page(
    *,
    render_template,
    session,
):
    return render_template(
        '流程与AI部/feishu_video_card_test.html',
        current_open_id=str(session.get('feishu_user_id') or '').strip(),
        current_user_name=str(session.get('feishu_user_name') or '当前用户').strip(),
    )


def feishu_video_card_test_chats(
    *,
    _list_feishu_bot_chats,
    jsonify,
):
    chats, error = _list_feishu_bot_chats()
    if error:
        return jsonify({'success': False, 'message': error, 'chats': []}), 502
    return jsonify({'success': True, 'chats': chats})


def feishu_video_card_test_send(
    *,
    FEISHU_NATIVE_VIDEO_MAX_BYTES,
    _feishu_send_message_detail,
    _resolve_feishu_chat_name,
    _upload_feishu_message_video,
    _upload_feishu_video_cover,
    jsonify,
    os,
    request,
    session,
):
    upload = request.files.get('video')
    if not upload or not getattr(upload, 'filename', ''):
        return jsonify({'success': False, 'message': '请选择 MP4 视频文件'}), 400
    filename = str(upload.filename or '').strip()
    if not filename.lower().endswith('.mp4'):
        return jsonify({'success': False, 'message': '当前测试仅支持 MP4 视频'}), 400
    upload.stream.seek(0, os.SEEK_END)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size <= 0:
        return jsonify({'success': False, 'message': '视频文件为空'}), 400
    if size > FEISHU_NATIVE_VIDEO_MAX_BYTES:
        return jsonify({'success': False, 'message': '飞书原生视频消息限制约 30MB，请压缩视频后再发送'}), 413

    receive_id_type = str(request.form.get('receive_id_type') or 'open_id').strip()
    if receive_id_type not in {'open_id', 'chat_id'}:
        return jsonify({'success': False, 'message': '接收人类型无效'}), 400
    receive_id = str(request.form.get('receive_id') or '').strip()
    if receive_id_type == 'chat_id':
        receive_id, resolve_error = _resolve_feishu_chat_name(receive_id)
        if not receive_id:
            return jsonify({'success': False, 'stage': 'resolve_chat', 'message': resolve_error}), 400
    if not receive_id:
        receive_id = str(session.get('feishu_user_id') or '').strip()
        receive_id_type = 'open_id'
    if not receive_id:
        return jsonify({'success': False, 'message': '未找到接收人飞书 ID'}), 400

    uploaded, file_key_or_error, upload_response = _upload_feishu_message_video(upload)
    if not uploaded:
        return jsonify({
            'success': False,
            'stage': 'upload',
            'message': file_key_or_error,
            'feishu_response': upload_response,
        }), 502
    file_key = file_key_or_error
    cover_key = _upload_feishu_video_cover(upload)
    title = str(request.form.get('title') or '视频推送').strip()[:80]
    description = str(request.form.get('description') or '用于验证飞书消息卡片中的视频播放能力。').strip()[:1000]

    # Card 1.0's media element is rendered by Feishu as a fixed small thumbnail
    # and exposes no width/height option. Send the copy first, then use Feishu's
    # native media message so the client renders its standard large player.
    intro = {
        'zh_cn': {
            'title': title,
            'content': [[{'tag': 'text', 'text': description}]],
        }
    }
    intro_ok, intro_response = _feishu_send_message_detail(
        receive_id, receive_id_type, 'post', intro
    )
    media_content = {'file_key': file_key}
    if cover_key:
        media_content['image_key'] = cover_key
    media_ok, media_response = _feishu_send_message_detail(
        receive_id, receive_id_type, 'media', media_content
    )
    if media_ok:
        return jsonify({
            'success': True,
            'mode': 'native_media',
            'message': '已使用飞书原生视频消息发送，视频将以标准大播放器展示',
            'file_key': file_key,
            'message_id': str((media_response.get('data') or {}).get('message_id') or ''),
            'intro_sent': intro_ok,
            'intro_message_id': str((intro_response.get('data') or {}).get('message_id') or ''),
            'cover_key': cover_key,
        })

    card = {
        'config': {'wide_screen_mode': True},
        'header': {
            'template': 'purple',
            'title': {'tag': 'plain_text', 'content': title},
        },
        'elements': [
            {'tag': 'markdown', 'content': description},
            {'tag': 'media', 'file_key': file_key},
            {'tag': 'note', 'elements': [{'tag': 'plain_text', 'content': f'视频文件：{filename}'}]},
        ],
    }
    card_ok, card_response = _feishu_send_message_detail(receive_id, receive_id_type, 'interactive', card)
    if card_ok:
        return jsonify({
            'success': True,
            'mode': 'interactive',
            'message': '互动消息卡片已发送，请在飞书中检查视频是否可播放',
            'file_key': file_key,
            'message_id': str((card_response.get('data') or {}).get('message_id') or ''),
        })

    post = {
        'zh_cn': {
            'title': title,
            'content': [
                [{'tag': 'text', 'text': description}],
                [{'tag': 'media', 'file_key': file_key}],
                [{'tag': 'text', 'text': f'视频文件：{filename}'}],
            ],
        }
    }
    post_ok, post_response = _feishu_send_message_detail(receive_id, receive_id_type, 'post', post)
    if post_ok:
        return jsonify({
            'success': True,
            'mode': 'post_fallback',
            'message': '互动卡片视频组件未通过，已使用飞书官方富文本视频组件发送',
            'file_key': file_key,
            'interactive_error': card_response,
            'message_id': str((post_response.get('data') or {}).get('message_id') or ''),
        })
    return jsonify({
        'success': False,
        'stage': 'send',
        'message': '视频上传成功，但互动卡片和富文本视频均发送失败',
        'file_key': file_key,
        'interactive_error': card_response,
        'post_error': post_response,
    }), 502
