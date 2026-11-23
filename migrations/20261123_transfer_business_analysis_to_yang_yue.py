"""Transfer Ren Zhenmin's personal business-analysis grants to Yang Yue."""

import json
import re
import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


PERMISSIONS = ("business_analysis", "business_analysis_all")
OLD_USER = "任真民"
NEW_USER = "杨悦"


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT ID, GongNeng, YongHu FROM dbo.quanxian WITH (UPDLOCK, HOLDLOCK) "
            "WHERE LTRIM(RTRIM(GongNeng)) IN (%s, %s)",
            PERMISSIONS,
        )
        rows = cursor.fetchall()
        if len(rows) != 2 or {str(row[1]).strip() for row in rows} != set(PERMISSIONS):
            raise ValueError("Expected exactly one entry and one full-access permission")
        changes = []
        for row_id, function_name, original in rows:
            users = [part.strip() for part in re.split(r"[；;,，、\r\n]+", str(original or "")) if part.strip()]
            if OLD_USER not in users:
                if NEW_USER not in users:
                    raise ValueError(f"No source grant found for {function_name}")
                continue
            updated = list(dict.fromkeys(NEW_USER if user == OLD_USER else user for user in users))
            cursor.execute(
                "UPDATE dbo.quanxian SET YongHu=%s, GengXinShiJian=SYSDATETIME() WHERE ID=%s",
                ("；".join(updated), row_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Unexpected update count for {function_name}")
            changes.append({"function": str(function_name).strip(), "before": original, "after": "；".join(updated)})
        connection.commit()
        return changes
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(apply_migration(), ensure_ascii=False))
