"""Store 360 evaluation and VideoClaw permissions in dbo.quanxian."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


ROWS = (
    ("value_evaluation", "360价值评价", "周俊成", "", "ai_dept", "360价值评价任务与本人评价记录。"),
    ("value_evaluation_admin", "360价值评价管理", "周俊成", "", "value_evaluation", "上传评价安排并维护评价项内容。"),
    ("video_claw", "VideoClaw AI视频创作", "", "AI部", "ai_dept", "VideoClaw AI视频创作工作台访问权限。"),
)


UPSERT_SQL = """
IF EXISTS (SELECT 1 FROM dbo.quanxian WHERE LTRIM(RTRIM(GongNeng))=%s)
    UPDATE dbo.quanxian
       SET MingCheng=%s, YongHu=%s, BuMen=%s, FuJiGongNeng=%s, MiaoShu=%s,
           QiYong=1, GengXinShiJian=SYSDATETIME()
     WHERE LTRIM(RTRIM(GongNeng))=%s;
ELSE
    INSERT INTO dbo.quanxian
        (GongNeng, MingCheng, YongHu, BuMen, FuJiGongNeng, MiaoShu, QiYong, GengXinShiJian)
    VALUES (%s, %s, %s, %s, %s, %s, 1, SYSDATETIME());
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        for key, name, users, departments, parent, description in ROWS:
            cursor.execute(
                UPSERT_SQL,
                (key, name, users, departments, parent, description, key,
                 key, name, users, departments, parent, description),
            )
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
    print("value_evaluation_and_video_claw_permissions=ready")
