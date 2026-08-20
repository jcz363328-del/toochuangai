"""落地 2026-08-19 跨任务迁移：ABA 导入权限、权限覆盖表、创新星鉴关联字段。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytds


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


def _sync_aba_import_permission():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            MERGE dbo.quanxian AS target
            USING (SELECT %s AS GongNeng) AS source
            ON LTRIM(RTRIM(target.GongNeng))=source.GongNeng
            WHEN MATCHED THEN UPDATE SET
                YongHu=%s, BuMen=%s, MingCheng=%s, MiaoShu=%s,
                QiYong=1, GengXinShiJian=SYSDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
                VALUES (source.GongNeng, %s, %s, N'', %s, %s, 1, SYSDATETIME());
            """,
            (
                "listing_agent_aba_import",
                "",
                "AI部",
                "ABA 看板导入",
                "仅允许 AI 部在 ABA 排名看板内导入或覆盖排名数据。",
                "",
                "AI部",
                "ABA 看板导入",
                "仅允许 AI 部在 ABA 排名看板内导入或覆盖排名数据。",
            ),
        )
        if not connection.autocommit:
            connection.commit()
    finally:
        connection.close()


def apply():
    _sync_aba_import_permission()

    from department_permissions import permission_manager

    permission_manager._ensure_permission_override_storage()

    # innovation_blueprint 会先配置 innovation 模块的兼容导入路径。
    import innovation_blueprint  # noqa: F401
    from innovation import web_app as innovation_web_app

    innovation_web_app._ensure_chuangxinxing_proposal_storage()
    return {
        "aba_import_permission": "AI部",
        "permission_override_storage": "ready",
        "innovation_proposal_storage": "ready",
    }


if __name__ == "__main__":
    print(apply())
