"""Grant Cai Jing access to 360 value evaluation administration."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


FUNCTION_KEY = "value_evaluation_admin"
TARGET_USER = "蔡晶"


def split_users(value):
    return [
        item.strip()
        for item in re.split(r"[；;,，、\r\n]+", str(value or ""))
        if item.strip()
    ]


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT ID, YongHu FROM dbo.quanxian WHERE LTRIM(RTRIM(GongNeng))=%s",
            (FUNCTION_KEY,),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError(f"Permission row does not exist: {FUNCTION_KEY}")
        row_id, raw_users = row
        users = split_users(raw_users)
        if TARGET_USER not in users:
            users.append(TARGET_USER)
            cursor.execute(
                """
                UPDATE dbo.quanxian
                   SET YongHu=%s, GengXinShiJian=SYSDATETIME()
                 WHERE ID=%s
                """,
                ("；".join(users), row_id),
            )
        if not connection.autocommit:
            connection.commit()
        return users
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    permission_users = apply_migration()
    print(f"{FUNCTION_KEY}={'；'.join(permission_users)}")
