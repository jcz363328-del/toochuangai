"""Add shared key/accounting ownership to the canvas text streaming route."""

import ast


def patch(source: str) -> str:
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name == "proxy_canvas_text"]
    if len(nodes) != 1:
        raise ValueError("Expected exactly one proxy_canvas_text function")
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    original = "".join(lines[node.lineno - 1:node.end_lineno])
    replacements = [
        (
            "    from 图片.request_limits import get_request_limiter",
            "    from 图片.request_limits import get_request_limiter\n"
            "    from 图片.omnia_service import managed_omnia_context",
        ),
        (
            '    with get_request_limiter().slot("omnia_text"):\n',
            '    with get_request_limiter().slot("omnia_text"), managed_omnia_context(\n'
            '        primary_key=api_key, model=str(payload.get("model") or ""),\n'
            '        api_base=site.OMNIAKEY_API_BASE,\n'
            '    ):\n'
            '        # The managed context pins this request to one pool credential\n'
            '        # until the upstream body is drained and accounting completes.\n'
            '        api_key = site.load_omnia_api_key()\n',
        ),
        (
            '                raise RuntimeError("OmniaKey 流连接中断，远端结果尚未确认，未自动重新提交。") from exc',
            '                raise RuntimeError("OmniaKey 流连接中断，远端结果尚未确认，未自动重新提交。") from exc\n'
            '            if upstream.status_code >= 400:\n'
            '                # Preserve the original error body already sent to the\n'
            '                # browser while recording this call as failed.\n'
            '                raise CanvasRequestError(\n'
            '                    f"OmniaKey 文字请求失败（HTTP {upstream.status_code}）",\n'
            '                    upstream.status_code,\n'
            '                )',
        ),
    ]
    updated = original.replace("\r\n", "\n")
    initial_replacements = [] if "managed_omnia_context" in updated else replacements
    status_replacements = [] if 'record_omnia_provider_status("success")' in updated else [
        (
            "    from 图片.omnia_service import managed_omnia_context",
            "    from 图片.omnia_service import managed_omnia_context, record_omnia_provider_status",
        ),
        (
            '        api_key = site.load_omnia_api_key()\n',
            '        api_key = site.load_omnia_api_key()\n'
            '        record_omnia_provider_status("uncertain")\n',
        ),
        (
            '            if upstream.status_code == 429:\n',
            '            if upstream.status_code == 429:\n'
            '                record_omnia_provider_status("rejected")\n',
        ),
        (
            '            handler.send_response(upstream.status_code)',
            '            if upstream.status_code >= 400:\n'
            '                record_omnia_provider_status("rejected")\n'
            '            handler.send_response(upstream.status_code)',
        ),
        (
            '                    f"OmniaKey 文字请求失败（HTTP {upstream.status_code}）",\n'
            '                    upstream.status_code,\n'
            '                )',
            '                    f"OmniaKey 文字请求失败（HTTP {upstream.status_code}）",\n'
            '                    upstream.status_code,\n'
            '                )\n'
            '            record_omnia_provider_status("success")',
        ),
    ]
    for before, after in initial_replacements + status_replacements:
        if updated.count(before) != 1:
            raise ValueError("Canvas baseline does not match the reviewed integration")
        updated = updated.replace(before, after, 1)
    if "\r\n" in source:
        updated = updated.replace("\n", "\r\n")
    result = "".join(lines[:node.lineno - 1]) + updated + "".join(lines[node.end_lineno:])
    ast.parse(result)
    return result
