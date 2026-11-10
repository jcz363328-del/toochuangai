"""Store the Zhou Juncheng-only historical-sales permission in dbo.quanxian."""

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
SET YongHu=N'周俊成', BuMen=N'', FuJiGongNeng=N'ai_dept',
    MingCheng=N'历史销售曲线', MiaoShu=N'历史销售额同期曲线，仅周俊成可访问。',
    QiYong=1, GengXinShiJian=SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng))=N'historical_sales';

IF @@ROWCOUNT=0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
    VALUES
        (N'historical_sales', N'周俊成', N'', N'ai_dept', N'历史销售曲线',
         N'历史销售额同期曲线，仅周俊成可访问。', 1, SYSDATETIME());
END;
"""


def apply_migration():
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(SQL)
        if not connection.autocommit:
            connection.commit()
        cursor.execute(
            "SELECT YongHu, BuMen, QiYong FROM dbo.quanxian "
            "WHERE LTRIM(RTRIM(GongNeng))=N'historical_sales'"
        )
        return cursor.fetchall()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(f"historical_sales_permission={apply_migration()}")
