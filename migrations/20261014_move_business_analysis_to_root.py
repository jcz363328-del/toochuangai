"""Move business analysis out of the AI department parent card."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE dbo.quanxian
            SET FuJiGongNeng=N'', GengXinShiJian=SYSDATETIME()
            WHERE LTRIM(RTRIM(GongNeng))=N'business_analysis';
        """)
        if not connection.autocommit:
            connection.commit()
        cursor.execute("""
            SELECT GongNeng, FuJiGongNeng, QiYong
            FROM dbo.quanxian
            WHERE LTRIM(RTRIM(GongNeng))=N'business_analysis';
        """)
        return cursor.fetchall()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(f"business_analysis_root={apply_migration()}")
