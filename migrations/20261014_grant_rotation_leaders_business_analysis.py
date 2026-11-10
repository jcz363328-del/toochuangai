"""Grant rotation leaders business-analysis entry permission in dbo.quanxian."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


USERS = ("郭婷", "王淑雯", "柳琳", "刘星辰", "张彦微")

UPDATE_SQL = """
UPDATE dbo.quanxian
SET YongHu = CASE
        WHEN CHARINDEX(N'；' + %s + N'；', N'；' + REPLACE(REPLACE(ISNULL(YongHu, N''), N',', N'；'), N'，', N'；') + N'；') > 0
            THEN YongHu
        WHEN LTRIM(RTRIM(ISNULL(YongHu, N''))) = N'' THEN %s
        ELSE RTRIM(YongHu) + N'；' + %s
    END,
    QiYong = 1,
    GengXinShiJian = SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng)) = N'business_analysis';
"""

INSERT_SQL = """
INSERT INTO dbo.quanxian
    (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
VALUES
    (N'business_analysis', %s,
     N'运营一部；运营二部；运营三部；运营六部；运营七部；AI部；总经办',
     N'ai_dept', N'经营分析',
     N'经营分析入口权限；部门负责人及轮岗负责人查看所负责部门，普通员工仅看本人。',
     1, SYSDATETIME());
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(1) FROM dbo.quanxian WHERE LTRIM(RTRIM(GongNeng))=N'business_analysis'"
        )
        if int(cursor.fetchone()[0] or 0) > 0:
            for user in USERS:
                cursor.execute(UPDATE_SQL, (user, user, user))
        else:
            cursor.execute(INSERT_SQL, ("；".join(USERS),))
        if not connection.autocommit:
            connection.commit()
        cursor.execute(
            "SELECT YongHu, QiYong FROM dbo.quanxian "
            "WHERE LTRIM(RTRIM(GongNeng))=N'business_analysis'"
        )
        rows = cursor.fetchall()
        return {
            user: any(bool(row[1]) and user in str(row[0] or "") for row in rows)
            for user in USERS
        }
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(f"rotation_leaders_business_analysis_permission={apply_migration()}")
