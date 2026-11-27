"""Handle session navigation and the portal file entry points."""

from __future__ import annotations


def _is_mobile_request(
    *,
    is_mobile_user_agent,
    request,
):
    return is_mobile_user_agent(request.headers.get('User-Agent'))


def _is_feishu_request(*, request):
    ua = (request.headers.get('User-Agent') or '').lower()
    if any(k in ua for k in ('lark', 'feishu', 'larkoffice')):
        return True
    return any(
        request.headers.get(header)
        for header in (
            'X-Lark-User-Id',
            'X-Lark-Open-Id',
            'X-Lark-Union-Id',
            'X-Lark-User-Access-Token',
            'X-Plugin-Token',
            'X-User-Plugin-Token',
        )
    )


def _normalize_feishu_user_name(
    raw_name,
    fallback,
    *,
    re,
):
    name = str(raw_name or '').strip()
    if not name:
        return str(fallback or '用户')
    # 去掉“姓名（部门）/ 姓名(部门)”后缀，保留纯姓名
    name = re.sub(r'\s*[（(][^（）()]{1,40}[）)]\s*$', '', name).strip()
    if not name:
        return str(fallback or '用户')
    return name


def _xiaotu_is_invalid_feishu_name(
    raw_name,
    *,
    re,
):
    name = str(raw_name or "").strip()
    if not name:
        return True
    low = name.lower()
    if low in {"用户", "飞书用户", "lark user", "匿名用户", "unknown", "unknown user"}:
        return True
    if re.match(r"^(ou_|on_|od_|u-|union_|cli_)", name, flags=re.I):
        return True
    if re.match(r"^[a-z0-9][a-z0-9_\-]{10,}$", name, flags=re.I) and "_" in name:
        return True
    return False


def uploaded_file(
    filename,
    *,
    INNOVATION_APP_CONFIG,
    _safe_debug_print,
    send_from_directory,
):
    """提供上传文件的访问"""
    try:
        # 安全检查：防止路径遍历攻击
        if '..' in filename or filename.startswith('/'):
            return "Invalid filename", 400

        return send_from_directory(INNOVATION_APP_CONFIG['upload_folder'], filename)
    except Exception as e:
        _safe_debug_print(f"文件访问错误: {e}")
        return "File not found", 404


def public_download_apr16_video(
    *,
    _PUBLIC_DOWNLOAD_APR16_VIDEO,
    os,
    send_file,
):
    """固定公开下载链接：4月16日视频"""
    file_path = _PUBLIC_DOWNLOAD_APR16_VIDEO
    if not os.path.isfile(file_path):
        return "File not found", 404
    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path),
        mimetype='video/mp4'
    )


def serve_static_html_files(
    filename,
    *,
    _safe_debug_print,
    send_from_directory,
):
    """处理根目录下的HTML文件"""
    try:
        html_filename = f"{filename}.html"
        return send_from_directory('.', html_filename)
    except Exception as e:
        _safe_debug_print(f"静态HTML文件访问错误: {e}")
        return "File not found", 404


def login(
    *,
    _safe_debug_print,
    redirect,
    request,
    url_for,
):
    """登录页面路由"""
    _safe_debug_print(f"\n=== 登录页面访问 ===")

    # 检查是否为本地开发环境
    is_local_dev = request.host.startswith('127.0.0.1') or request.host.startswith('localhost')
    _safe_debug_print(f"🏠 本地开发环境: {is_local_dev}")

    if is_local_dev:
        # 本地开发环境，重定向到开发者登录
        _safe_debug_print(f"🔧 重定向到开发者登录")
        return redirect(url_for('dev_login', user_type='bd'))
    else:
        # 生产环境，重定向到飞书授权
        _safe_debug_print(f"🚀 重定向到飞书授权")
        return redirect(url_for('feishu_auth'))


def logout(
    *,
    _clear_feishu_user_access_token,
    redirect,
    session,
    url_for,
):
    """退出登录"""
    _clear_feishu_user_access_token()
    session.clear()
    return redirect(url_for('dashboard'))


def reauth(
    *,
    _clear_feishu_user_access_token,
    _safe_debug_print,
    permission_manager,
    redirect,
    session,
    url_for,
):
    """重新授权 - 用于解决open_id cross app错误"""
    _safe_debug_print(f"\n=== 用户重新授权处理 ===")
    _safe_debug_print(f"👤 当前用户ID: {session.get('feishu_open_id', '未知')}")
    _safe_debug_print(f"👤 当前用户名: {session.get('feishu_user_name', '未知')}")
    _safe_debug_print(f"🧹 清除session和缓存...")
    
    # 清除用户缓存
    user_id = session.get('feishu_open_id')
    if user_id:
        permission_manager.clear_cache(user_id)
        _safe_debug_print(f"✅ 已清除用户 {user_id} 的缓存")
    
    # 清除session，但保留强制重授权标记
    _clear_feishu_user_access_token()
    session.clear()
    session['force_feishu_reauth'] = '1'
    _safe_debug_print(f"✅ 已清除session")
    _safe_debug_print(f"🔄 重定向到飞书授权页面...")
    _safe_debug_print("========================\n")
    
    # 重定向到飞书授权
    return redirect(url_for('feishu_auth', force='1'))
