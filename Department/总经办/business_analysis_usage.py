"""Best-effort usage logging for the business-analysis page."""

from __future__ import annotations

import pytds

from secret_settings import sql_server_config


INSERT_USAGE_SQL = """
INSERT INTO dbo.JingYingFenXi
    (FeishuUserId, FeishuUserName, AccessPath, ClientIp, UserAgent, UsedAt)
SELECT %s, %s, %s, %s, %s, SYSDATETIME()
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.JingYingFenXi
    WHERE FeishuUserName = %s
      AND UsedAt >= DATEADD(SECOND, -5, SYSDATETIME())
);
"""


def record_business_analysis_usage(
    *,
    user_id: str,
    user_name: str,
    access_path: str,
    client_ip: str,
    user_agent: str,
) -> None:
    """Insert one successful page-entry event into SQL Server."""
    connection = pytds.connect(**sql_server_config(), timeout=5)
    try:
        cursor = connection.cursor()
        cursor.execute(
            INSERT_USAGE_SQL,
            (
                str(user_id or "").strip()[:128] or None,
                str(user_name or "").strip()[:200] or "未知用户",
                str(access_path or "").strip()[:500] or None,
                str(client_ip or "").strip()[:64] or None,
                str(user_agent or "").strip()[:1000] or None,
                str(user_name or "").strip()[:200] or "未知用户",
            ),
        )
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()
