"""List and serve annual event and training media."""

from __future__ import annotations


def _annual_moments_file_size_label(size_bytes):
    try:
        size_value = float(size_bytes or 0)
    except (TypeError, ValueError):
        size_value = 0
    if size_value >= 1024 * 1024 * 1024:
        return f"{size_value / (1024 * 1024 * 1024):.1f} GB"
    if size_value >= 1024 * 1024:
        return f"{size_value / (1024 * 1024):.1f} MB"
    if size_value >= 1024:
        return f"{size_value / 1024:.1f} KB"
    return f"{int(size_value)} B"


def _collect_annual_moment_files(
    folder,
    extensions,
    endpoint,
    *,
    _annual_moments_file_size_label,
    datetime,
    os,
    url_for,
):
    media_files = []
    if not os.path.isdir(folder):
        return media_files

    root_abs = os.path.abspath(folder)
    for current_root, dirs, files in os.walk(root_abs):
        dirs.sort()
        for name in sorted(files):
            file_abs = os.path.abspath(os.path.join(current_root, name))
            ext = os.path.splitext(name)[1].lower()
            if ext not in extensions or not os.path.isfile(file_abs):
                continue
            try:
                stat_info = os.stat(file_abs)
            except OSError:
                continue
            relpath = os.path.relpath(file_abs, root_abs).replace('\\', '/')
            rel_dir = os.path.dirname(relpath).replace('\\', '/')
            media_files.append({
                "name": name,
                "url": url_for(endpoint, relpath=relpath),
                "relpath": relpath,
                "folder_name": rel_dir if rel_dir else "根目录",
                "size": stat_info.st_size,
                "size_label": _annual_moments_file_size_label(stat_info.st_size),
                "modified_at": datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return media_files


def _send_annual_moment_file(
    root_folder,
    relpath,
    allowed_extensions,
    *,
    os,
    redirect,
    send_from_directory,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    raw_rel = str(relpath or '').replace('\\', '/').strip()
    if not raw_rel:
        return "文件不存在", 404
    safe_rel = os.path.normpath(raw_rel).replace('\\', '/')
    if safe_rel in {'.', ''} or safe_rel.startswith('../') or safe_rel.startswith('/'):
        return "文件不存在", 404

    root_abs = os.path.abspath(root_folder)
    file_abs = os.path.abspath(os.path.join(root_abs, safe_rel))
    try:
        if os.path.commonpath([root_abs, file_abs]).lower() != root_abs.lower():
            return "文件不存在", 404
    except ValueError:
        return "文件不存在", 404

    safe_name = os.path.basename(file_abs)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in allowed_extensions:
        return "不支持的文件类型", 400
    if not os.path.isfile(file_abs):
        return "文件不存在", 404
    return send_from_directory(os.path.dirname(file_abs), safe_name, as_attachment=False, conditional=True)


def annual_moments(
    *,
    _ANNUAL_MOMENTS_IMAGE_DIR,
    _ANNUAL_MOMENTS_VIDEO_DIR,
    _IMAGE_EXTENSIONS,
    _VIDEO_EXTENSIONS,
    _collect_annual_moment_files,
    os,
    redirect,
    render_template,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    images = _collect_annual_moment_files(
        _ANNUAL_MOMENTS_IMAGE_DIR,
        _IMAGE_EXTENSIONS,
        'annual_moment_image_file'
    )
    videos = _collect_annual_moment_files(
        _ANNUAL_MOMENTS_VIDEO_DIR,
        _VIDEO_EXTENSIONS,
        'annual_moment_video_file'
    )
    return render_template(
        '培训与活动/annual_moments.html',
        images=images,
        videos=videos,
        image_folder=_ANNUAL_MOMENTS_IMAGE_DIR,
        video_folder=_ANNUAL_MOMENTS_VIDEO_DIR,
        image_folder_exists=os.path.isdir(_ANNUAL_MOMENTS_IMAGE_DIR),
        video_folder_exists=os.path.isdir(_ANNUAL_MOMENTS_VIDEO_DIR),
    )


def annual_moment_image_file(
    relpath,
    *,
    _ANNUAL_MOMENTS_IMAGE_DIR,
    _IMAGE_EXTENSIONS,
    _send_annual_moment_file,
):
    return _send_annual_moment_file(_ANNUAL_MOMENTS_IMAGE_DIR, relpath, _IMAGE_EXTENSIONS)


def annual_moment_video_file(
    relpath,
    *,
    _ANNUAL_MOMENTS_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    _send_annual_moment_file,
):
    return _send_annual_moment_file(_ANNUAL_MOMENTS_VIDEO_DIR, relpath, _VIDEO_EXTENSIONS)


def training_videos(
    *,
    redirect,
    render_template,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    return render_template('培训与活动/training_videos.html')


def chuanshi_training(
    *,
    _CHUANSHI_TRAINING_IMAGE_DIR,
    _CHUANSHI_TRAINING_VIDEO_DIR,
    _IMAGE_EXTENSIONS,
    _VIDEO_EXTENSIONS,
    _collect_annual_moment_files,
    os,
    redirect,
    render_template,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))

    images = _collect_annual_moment_files(
        _CHUANSHI_TRAINING_IMAGE_DIR,
        _IMAGE_EXTENSIONS,
        'chuanshi_training_image_file'
    )
    videos = _collect_annual_moment_files(
        _CHUANSHI_TRAINING_VIDEO_DIR,
        _VIDEO_EXTENSIONS,
        'chuanshi_training_video_file'
    )
    return render_template(
        '培训与活动/annual_moments.html',
        page_title='传世培训',
        page_icon='fa-solid fa-photo-film',
        back_url=url_for('training_videos'),
        back_label='返回培训视频',
        activity_date='2026-07-09',
        images=images,
        videos=videos,
        image_folder=_CHUANSHI_TRAINING_IMAGE_DIR,
        video_folder=_CHUANSHI_TRAINING_VIDEO_DIR,
        image_folder_exists=os.path.isdir(_CHUANSHI_TRAINING_IMAGE_DIR),
        video_folder_exists=os.path.isdir(_CHUANSHI_TRAINING_VIDEO_DIR),
    )


def chuanshi_training_image_file(
    relpath,
    *,
    _CHUANSHI_TRAINING_IMAGE_DIR,
    _IMAGE_EXTENSIONS,
    _send_annual_moment_file,
):
    return _send_annual_moment_file(_CHUANSHI_TRAINING_IMAGE_DIR, relpath, _IMAGE_EXTENSIONS)


def chuanshi_training_video_file(
    relpath,
    *,
    _CHUANSHI_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    _send_annual_moment_file,
):
    return _send_annual_moment_file(_CHUANSHI_TRAINING_VIDEO_DIR, relpath, _VIDEO_EXTENSIONS)


def strategy_training_videos(
    *,
    _STRATEGY_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    redirect,
    render_template,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    folder = _STRATEGY_TRAINING_VIDEO_DIR
    grouped_videos = []
    if os.path.isdir(folder):
        for current_root, dirs, files in os.walk(folder):
            dirs.sort()
            rel_dir = os.path.relpath(current_root, folder)
            videos = []
            for name in sorted(files):
                file_path = os.path.join(current_root, name)
                ext = os.path.splitext(name)[1].lower()
                if not os.path.isfile(file_path) or ext not in _VIDEO_EXTENSIONS:
                    continue
                if rel_dir in {'.', ''}:
                    video_url = url_for('strategy_training_video_file', filename=name)
                    folder_name = '根目录'
                else:
                    rel_file = os.path.join(rel_dir, name).replace('\\', '/')
                    video_url = url_for('strategy_training_video_file_by_path', relpath=rel_file)
                    folder_name = rel_dir.replace('\\', '/')
                videos.append({
                    "name": name,
                    "url": video_url
                })
            if videos:
                grouped_videos.append({
                    "folder_name": folder_name,
                    "videos": videos
                })
    return render_template(
        '培训与活动/strategy_training_videos.html',
        grouped_videos=grouped_videos,
        folder_path=folder
    )


def strategy_training_video_file(
    filename,
    *,
    _STRATEGY_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    redirect,
    send_from_directory,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    file_path = os.path.join(_STRATEGY_TRAINING_VIDEO_DIR, safe_name)
    if not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(_STRATEGY_TRAINING_VIDEO_DIR, safe_name, as_attachment=False)


def strategy_training_video_file_in_folder(
    folder,
    filename,
    *,
    _STRATEGY_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    redirect,
    send_from_directory,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    safe_folder = os.path.basename(str(folder or ""))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_folder or not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    target_dir = os.path.join(_STRATEGY_TRAINING_VIDEO_DIR, safe_folder)
    file_path = os.path.join(target_dir, safe_name)
    if not os.path.isdir(target_dir) or not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(target_dir, safe_name, as_attachment=False)


def strategy_training_video_file_by_path(
    relpath,
    *,
    _STRATEGY_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    redirect,
    send_from_directory,
    session,
    url_for,
):
    user_id = session.get('feishu_user_id')
    if not user_id:
        return redirect(url_for('feishu_auth'))
    raw_rel = str(relpath or '').replace('\\', '/').strip()
    if not raw_rel:
        return "文件不存在", 404
    safe_rel = os.path.normpath(raw_rel).replace('\\', '/')
    if safe_rel in {'.', ''} or safe_rel.startswith('../') or safe_rel.startswith('/'):
        return "文件不存在", 404
    root_abs = os.path.abspath(_STRATEGY_TRAINING_VIDEO_DIR)
    file_abs = os.path.abspath(os.path.join(root_abs, safe_rel))
    try:
        if os.path.commonpath([root_abs, file_abs]).lower() != root_abs.lower():
            return "文件不存在", 404
    except ValueError:
        return "文件不存在", 404
    safe_name = os.path.basename(file_abs)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    if not os.path.isfile(file_abs):
        return "文件不存在", 404
    return send_from_directory(os.path.dirname(file_abs), safe_name, as_attachment=False)


def rococo_training_videos(
    *,
    _ROCOCO_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    render_template,
    url_for,
):
    root_folder = _ROCOCO_TRAINING_VIDEO_DIR
    grouped_videos = []
    if os.path.isdir(root_folder):
        for folder_name in sorted(os.listdir(root_folder)):
            folder_path = os.path.join(root_folder, folder_name)
            if not os.path.isdir(folder_path):
                continue
            videos = []
            for current_dir, dir_names, file_names in os.walk(folder_path):
                dir_names.sort()
                for name in sorted(file_names):
                    file_path = os.path.join(current_dir, name)
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in _VIDEO_EXTENSIONS:
                        continue
                    rel_file = os.path.relpath(file_path, root_folder).replace('\\', '/')
                    display_name = os.path.relpath(file_path, folder_path).replace('\\', ' / ')
                    videos.append({
                        "name": display_name,
                        "url": url_for('rococo_training_video_file_by_path', relpath=rel_file)
                    })
            grouped_videos.append({
                "folder_name": folder_name,
                "videos": videos
            })
    return render_template(
        '培训与活动/rococo_training_videos.html',
        grouped_videos=grouped_videos,
        folder_path=root_folder
    )


def rococo_training_video_file(
    folder,
    filename,
    *,
    _ROCOCO_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    send_from_directory,
):
    safe_folder = os.path.basename(str(folder or ""))
    safe_name = os.path.basename(str(filename or ""))
    if not safe_folder or not safe_name:
        return "文件不存在", 404
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    target_dir = os.path.join(_ROCOCO_TRAINING_VIDEO_DIR, safe_folder)
    file_path = os.path.join(target_dir, safe_name)
    if not os.path.isdir(target_dir) or not os.path.isfile(file_path):
        return "文件不存在", 404
    return send_from_directory(target_dir, safe_name, as_attachment=False)


def rococo_training_video_file_by_path(
    relpath,
    *,
    _ROCOCO_TRAINING_VIDEO_DIR,
    _VIDEO_EXTENSIONS,
    os,
    send_from_directory,
):
    raw_rel = str(relpath or '').replace('\\', '/').strip()
    if not raw_rel:
        return "文件不存在", 404
    safe_rel = os.path.normpath(raw_rel).replace('\\', '/')
    if safe_rel in {'.', ''} or safe_rel.startswith('../') or safe_rel.startswith('/'):
        return "文件不存在", 404
    root_abs = os.path.abspath(_ROCOCO_TRAINING_VIDEO_DIR)
    file_abs = os.path.abspath(os.path.join(root_abs, safe_rel))
    try:
        if os.path.commonpath([root_abs, file_abs]).lower() != root_abs.lower():
            return "文件不存在", 404
    except ValueError:
        return "文件不存在", 404
    safe_name = os.path.basename(file_abs)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in _VIDEO_EXTENSIONS:
        return "不支持的文件类型", 400
    if not os.path.isfile(file_abs):
        return "文件不存在", 404
    return send_from_directory(os.path.dirname(file_abs), safe_name, as_attachment=False)
