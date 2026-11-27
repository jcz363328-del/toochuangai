"""Feishu authentication and event callback handlers."""


def feishu_auth(
    get_feishu_auth_url,
    redirect,
    request,
    session,
):
    """飞书授权页面"""
    next_path = str(request.args.get('next') or '').strip()
    if next_path.startswith('/'):
        session['post_auth_redirect'] = next_path
    force_reauth = str(request.args.get('force') or '').strip().lower() in {'1', 'true', 'yes'}
    if force_reauth:
        session['force_feishu_reauth'] = '1'
    auth_url = get_feishu_auth_url()
    return redirect(auth_url)


def feishu_callback(
    FEISHU_CONFIG,
    _bind_feishu_session,
    _clear_feishu_identity_session,
    _event_mentions_bot,
    _extract_all_text,
    _feishu_extract_cloud_doc_url_from_event,
    _feishu_find_cloud_doc_url_any,
    _feishu_recent_events,
    _feishu_recent_events_limit,
    _feishu_try_decrypt_callback_data,
    _handle_feishu_cloud_doc_mention_event,
    _safe_debug_print,
    _xiaotu_handle_report_card_action,
    datetime,
    handle_feishu_event,
    handle_feishu_message_event,
    jsonify,
    permission_manager,
    re,
    redirect,
    request,
    session,
    url_for,
):
    """飞书授权回调"""
    _safe_debug_print(f"\n=== 飞书授权回调处理 ===")
    _safe_debug_print(f"请求方法: {request.method}")
    _safe_debug_print(
        f"请求来源: host={request.host}, user_agent={str(request.user_agent)[:160]}"
    )

    # 如果是POST请求，可能是飞书的事件回调或URL验证
    if request.method == 'POST':
        _safe_debug_print(f"🔐 检测到POST请求，处理飞书回调...")

        try:
            data = request.get_json()
            data = _feishu_try_decrypt_callback_data(data)
            _safe_debug_print(f"收到飞书回调请求: {data}")
            try:
                event_type_preview = (
                    (data or {}).get("event", {}).get("type")
                    or (data or {}).get("header", {}).get("event_type")
                    or (data or {}).get("type")
                )
                _feishu_recent_events.append({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "stage": "callback_received",
                    "type": event_type_preview,
                    "has_encrypt": bool((request.get_json(silent=True) or {}).get("encrypt")),
                    "schema": (data or {}).get("schema"),
                })
                if len(_feishu_recent_events) > _feishu_recent_events_limit:
                    del _feishu_recent_events[:len(_feishu_recent_events) - _feishu_recent_events_limit]
            except Exception:
                pass

            # 处理 URL 校验
            if data and data.get('type') == 'url_verification':
                challenge = data.get('challenge')
                _safe_debug_print(f"URL验证请求，返回challenge: {challenge}")
                return jsonify({"challenge": challenge})

            # 校验 token（可选）
            token = data.get('token')
            if token and token != FEISHU_CONFIG.get('verification_token'):
                _safe_debug_print("Token验证失败")
                return jsonify({"msg": "verification token mismatch"}), 403

            # 处理事件
            event = data.get('event', {})
            _safe_debug_print(f"收到事件: {event}")

            event_type = (event or {}).get('type') or (data or {}).get('header', {}).get('event_type') or (data or {}).get('type')
            if event_type in ('im.message.receive_v1', 'message_receive_v1'):
                return handle_feishu_message_event(data)
            if event_type in ('card.action.trigger', 'im.message.action_v1', 'message_action_v1'):
                return _xiaotu_handle_report_card_action(data)

            try:
                if _event_mentions_bot(event):
                    payload_text = _extract_all_text(event, max_chars=12000)
                    event_doc_url = _feishu_extract_cloud_doc_url_from_event(event)
                    maybe_doc = bool(_feishu_find_cloud_doc_url_any(payload_text) or event_doc_url) or bool(re.search(r"(doxcn[a-zA-Z0-9]+|doccn[a-zA-Z0-9]+)", payload_text))
                    if maybe_doc:
                        return _handle_feishu_cloud_doc_mention_event(data)
            except Exception:
                pass

            return handle_feishu_event(data)

        except Exception as e:
            _safe_debug_print(f"❌ 处理POST回调异常: {e}")
            import traceback
            _safe_debug_print(f"🔍 错误详情: {traceback.format_exc()}")
            return jsonify({'error': '处理回调失败'}), 500

    # GET请求处理授权回调
    code = request.args.get('code')
    state = request.args.get('state')

    _safe_debug_print(f"📝 授权码已收到: {bool(code)}")
    _safe_debug_print(f"🔐 状态码: {state}")

    # 如果没有授权码，可能是直接访问回调地址，返回友好提示
    if not code:
        _safe_debug_print(f"❌ 未获取到授权码")
        _safe_debug_print("========================\n")
        return jsonify({
            'error': '此接口用于飞书回调，请通过飞书授权流程访问',
            'message': '如需测试，请访问 /test/challenge 页面',
            'status': 'callback_endpoint'
        }), 200  # 改为200状态码，避免飞书认为接口异常

    if not str(state or '').startswith('tuchuang_ai_system'):
        _safe_debug_print(f"❌ 状态验证失败: {state}")
        _safe_debug_print("========================\n")
        return jsonify({'error': '授权失败，状态验证失败'}), 400

    try:
        _safe_debug_print(f"🔄 使用授权码获取用户信息...")
        # 通过授权码获取用户信息
        user_info = permission_manager.get_user_info_by_code(code)

        if not user_info:
            _safe_debug_print(f"❌ 获取用户信息失败")
            # OAuth authorization codes are single-use. If a browser restores or
            # refreshes an old callback URL, start a fresh authorization flow
            # instead of leaving the user on a 500 page.
            _clear_feishu_identity_session()
            session['force_feishu_reauth'] = '1'
            _safe_debug_print("========================\n")
            return redirect(url_for('feishu_auth', force='1'))

        _safe_debug_print(
            "✅ 成功获取用户信息: "
            f"name={user_info.get('name')}, "
            f"open_id={user_info.get('open_id') or user_info.get('user_id')}"
        )

        # 统一绑定为当前应用下的用户身份
        _clear_feishu_identity_session()
        _bind_feishu_session(user_info, str(user_info.get('user_access_token') or ''))

        _safe_debug_print(f"✅ 用户授权成功: {user_info.get('name')} ({user_info.get('user_id')})")
        _safe_debug_print(f"📝 用户信息已保存到Session")
        session.pop('force_feishu_reauth', None)

        # 后台预加载用户部门信息和权限数据
        user_id = user_info.get('open_id') or user_info.get('user_id')
        _safe_debug_print(f"🚀 开始后台预加载用户数据: {user_id}")
        try:
            # 预加载部门信息（这会触发缓存）
            departments = permission_manager.get_user_departments(user_id)
            _safe_debug_print(f"✅ 预加载部门信息完成，部门数量: {len(departments)}")

            # 预加载权限信息（这会触发缓存）
            accessible_functions = permission_manager.get_user_accessible_functions(user_id)
            _safe_debug_print(f"✅ 预加载权限信息完成，可访问功能数量: {len(accessible_functions)}")

            # 将预加载的数据存储到session中，进一步提升响应速度
            session.pop('preloaded_departments', None)
            session.pop('preloaded_functions', None)
            session.pop('preload_time', None)

            _safe_debug_print(f"🎯 后台预加载完成，Dashboard访问将实现秒开")
        except Exception as e:
            _safe_debug_print(f"⚠️ 后台预加载失败: {e}，但不影响正常登录")

        to_path = str(session.pop('post_auth_redirect', '') or '').strip()
        if not to_path.startswith('/'):
            to_path = url_for('dashboard')
        _safe_debug_print(f"🔄 重定向到: {to_path}")
        _safe_debug_print("========================\n")
        return redirect(to_path)

    except Exception as e:
        _safe_debug_print(f"❌ 处理飞书授权回调异常: {e}")
        import traceback
        _safe_debug_print(f"🔍 错误详情: {traceback.format_exc()}")
        _safe_debug_print("========================\n")
        return jsonify({'error': f'授权处理失败: {str(e)}'}), 500
