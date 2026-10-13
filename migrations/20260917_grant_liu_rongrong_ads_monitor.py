"""Grant Liu Rongrong access to MAGIC AD without removing existing users."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


SQL = """
UPDATE dbo.quanxian
SET YongHu = CASE
        WHEN CHARINDEX(N'刘蓉蓉', ISNULL(YongHu, N'')) > 0 THEN YongHu
        WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN N'刘蓉蓉'
        ELSE RTRIM(YongHu) + N'；刘蓉蓉'
    END,
    QiYong = 1,
    GengXinShiJian = SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng)) = N'ads_monitor';

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
    VALUES
        (N'ads_monitor', N'刘蓉蓉', N'', N'ai_dept', N'MAGIC AD 广告监控',
         N'MAGIC AD 广告监控页面、静态资源与诊断接口权限。', 1, SYSDATETIME());
END;
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(SQL)
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print("liu_rongrong_ads_monitor_permission=applied")
