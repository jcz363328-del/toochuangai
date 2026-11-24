"""Apply only the Xiaoha balance route to each independent main baseline."""
from __future__ import annotations

import ast
from pathlib import Path


def patch(source: str) -> str:
    newline = "\r\n" if "\r\n" in source else "\n"

    def replace_once(old: str, new: str) -> None:
        nonlocal source
        old, new = old.replace("\n", newline), new.replace("\n", newline)
        count = source.count(old)
        if count != 1:
            raise ValueError(f"Expected one balance-route anchor; found {count}: {old[:100]!r}")
        source = source.replace(old, new, 1)

    replace_once(
        'XIAOHA_DASHBOARD_KEY = "__usage_dashboard__"\n',
        'XIAOHA_DASHBOARD_KEY = "__usage_dashboard__"\nXIAOHA_BALANCE_KEY = "__balance__"\n',
    )
    replace_once(
        "def render_xiaoha_usage_dashboard() -> None:\n",
        "def render_xiaoha_balance_management() -> None:\n"
        "    from 图片.balance_view import render_balance_management\n"
        "    from 图片.balance_provider import load_balance_snapshot\n"
        "\n"
        "    render_balance_management(SimpleNamespace(st=st), load_balance_snapshot)\n"
        "\n"
        "\n"
        "def render_xiaoha_usage_dashboard() -> None:\n",
    )
    replace_once(
        '    groups.append(("状态与数据", [{"key": XIAOHA_DASHBOARD_KEY, "name": "数据看板"}]))\n',
        '    groups.append(("状态与数据", [\n'
        '        {"key": XIAOHA_DASHBOARD_KEY, "name": "数据看板"},\n'
        '        {"key": XIAOHA_BALANCE_KEY, "name": "余额管理"},\n'
        '    ]))\n',
    )
    replace_once(
        "    allowed_page_keys = feature_keys | {XIAOHA_DASHBOARD_KEY}\n",
        "    allowed_page_keys = feature_keys | {XIAOHA_DASHBOARD_KEY, XIAOHA_BALANCE_KEY}\n",
    )
    replace_once(
        "        if st.session_state.selected_feature_key == XIAOHA_DASHBOARD_KEY:\n"
        "            render_xiaoha_usage_dashboard()\n"
        "        elif current_feature is not None:\n",
        "        if st.session_state.selected_feature_key == XIAOHA_DASHBOARD_KEY:\n"
        "            render_xiaoha_usage_dashboard()\n"
        "        elif st.session_state.selected_feature_key == XIAOHA_BALANCE_KEY:\n"
        "            render_xiaoha_balance_management()\n"
        "        elif current_feature is not None:\n",
    )
    ast.parse(source)
    compile(source, "<balance-route-patched>", "exec")
    return source


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for baseline in ("runtime", "image"):
        original = root / f"before-{baseline}.py"
        destination = root / f"{baseline}-patched.py"
        with original.open(encoding="utf-8-sig", newline="") as stream:
            result = patch(stream.read())
        with destination.open("w", encoding="utf-8", newline="") as stream:
            stream.write(result)
        print(f"{destination.name}: patch and AST/compile checks passed")
