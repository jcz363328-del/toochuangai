"""Open 360 evaluation to all users and limit its admin to Han Yajun and AI department."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


ROWS = (
    ("value_evaluation", "360价值评价", "", "all", "ai_dept", "全体已登录用户可访问360价值评价任务与本人评价记录。"),
    ("value_evaluation_admin", "360价值评价管理", "韩雅俊", "AI部", "value_evaluation", "仅韩雅俊和AI部成员可上传评价安排并维护评价项内容。"),
)


UPDATE_SQL = """
UPDATE dbo.quanxian
   SET MingCheng=%s, YongHu=%s, BuMen=%s, FuJiGongNeng=%s, MiaoShu=%s,
       QiYong=1, GengXinShiJian=SYSDATETIME()
 WHERE LTRIM(RTRIM(GongNeng))=%s;
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        for key, name, users, departments, parent, description in ROWS:
            cursor.execute(UPDATE_SQL, (name, users, departments, parent, description, key))
            if cursor.rowcount == 0:
                raise RuntimeError(f"Permission row does not exist: {key}")
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
    print("value_evaluation_permissions=updated")
