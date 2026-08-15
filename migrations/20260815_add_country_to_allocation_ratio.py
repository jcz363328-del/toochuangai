"""为店铺费用分摊比例增加国家维度；可重复执行。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from secret_settings import sql_server_config


MIGRATION_SQL = r"""
SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.tk_费用分摊比例', N'U') IS NULL
    THROW 50001, N'缺少表 dbo.tk_费用分摊比例', 1;

IF COL_LENGTH(N'dbo.tk_费用分摊比例', N'国') IS NULL
    ALTER TABLE dbo.tk_费用分摊比例 ADD [国] NVARCHAR(50) NULL;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.tk_费用分摊比例')
      AND name = N'IX_allocation_ratio_country_key'
)
    CREATE NONCLUSTERED INDEX IX_allocation_ratio_country_key
        ON dbo.tk_费用分摊比例 ([年], [月], [国], [地区], [项目], [店铺])
        INCLUDE ([比例]);
"""


def migrate() -> None:
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(MIGRATION_SQL)
        if not connection.autocommit:
            connection.commit()
    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
    print("migration=ok")
