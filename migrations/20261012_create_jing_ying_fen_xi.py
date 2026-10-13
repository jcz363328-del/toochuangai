"""Create dbo.JingYingFenXi for business-analysis usage events."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


MIGRATION_SQL = """
IF OBJECT_ID(N'dbo.JingYingFenXi', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.JingYingFenXi
    (
        Id BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_JingYingFenXi PRIMARY KEY,
        FeishuUserId NVARCHAR(128) NULL,
        FeishuUserName NVARCHAR(200) NOT NULL,
        UsedAt DATETIME2(0) NOT NULL
            CONSTRAINT DF_JingYingFenXi_UsedAt DEFAULT SYSDATETIME(),
        AccessPath NVARCHAR(500) NULL,
        ClientIp NVARCHAR(64) NULL,
        UserAgent NVARCHAR(1000) NULL
    );

    CREATE INDEX IX_JingYingFenXi_UsedAt
        ON dbo.JingYingFenXi (UsedAt DESC);

    CREATE INDEX IX_JingYingFenXi_UserName_UsedAt
        ON dbo.JingYingFenXi (FeishuUserName, UsedAt DESC);
END;
"""


def apply_migration() -> None:
    connection = pytds.connect(**sql_server_config(), timeout=30)
    try:
        cursor = connection.cursor()
        cursor.execute(MIGRATION_SQL)
        if not connection.autocommit:
            connection.commit()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


def inspect_table() -> list[tuple[str, str, int]]:
    connection = pytds.connect(**sql_server_config(), timeout=30)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT c.name, TYPE_NAME(c.user_type_id), c.max_length
            FROM sys.columns AS c
            WHERE c.object_id = OBJECT_ID(N'dbo.JingYingFenXi', N'U')
            ORDER BY c.column_id;
            """
        )
        return [(str(row[0]), str(row[1]), int(row[2])) for row in cursor.fetchall()]
    finally:
        connection.close()


if __name__ == "__main__":
    apply_migration()
    print({"table": "dbo.JingYingFenXi", "columns": inspect_table()})
