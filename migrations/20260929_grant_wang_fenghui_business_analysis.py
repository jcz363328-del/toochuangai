"""Grant Wang Fenghui access to business analysis without removing existing users."""

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
        WHEN CHARINDEX(N'王丰慧', ISNULL(YongHu, N'')) > 0 THEN YongHu
        WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN N'王丰慧'
        ELSE RTRIM(YongHu) + N'；王丰慧'
    END,
    QiYong = 1,
    GengXinShiJian = SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng)) = N'business_analysis';

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
    VALUES
        (N'business_analysis', N'王丰慧',
         N'运营一部；运营二部；运营三部；运营六部；运营七部；AI部；总经办',
         N'ai_dept', N'经营分析',
         N'经营分析入口权限；部门负责人仅看本部门，普通员工仅看本人，未命中全量权限时仅展示比例数据。',
         1, SYSDATETIME());
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
    print("wang_fenghui_business_analysis_permission=applied")
