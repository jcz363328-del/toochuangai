"""Sync existing menu clicks into dbo.JingYingFenXi without an app restart."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config


MIGRATION_SQL = """
INSERT INTO dbo.JingYingFenXi
    (FeishuUserId, FeishuUserName, UsedAt, AccessPath)
SELECT NULL,
       LTRIM(RTRIM(src.UserName)),
       CAST(src.[Time] AS DATETIME2(0)),
       N'/ai/business-analysis'
FROM dbo.CaiDanShiYongJiLu AS src
WHERE LTRIM(RTRIM(src.Menu)) = N'经营分析'
  AND LTRIM(RTRIM(ISNULL(src.UserName, N''))) <> N''
  AND NOT EXISTS
  (
      SELECT 1
      FROM dbo.JingYingFenXi AS dst
      WHERE dst.FeishuUserName = LTRIM(RTRIM(src.UserName))
        AND dst.UsedAt = CAST(src.[Time] AS DATETIME2(0))
  );

EXEC(N'
CREATE OR ALTER TRIGGER dbo.TR_CaiDanShiYongJiLu_JingYingFenXi
ON dbo.CaiDanShiYongJiLu
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.JingYingFenXi
        (FeishuUserId, FeishuUserName, UsedAt, AccessPath)
    SELECT NULL,
           LTRIM(RTRIM(i.UserName)),
           CAST(i.[Time] AS DATETIME2(0)),
           N''/ai/business-analysis''
    FROM inserted AS i
    WHERE LTRIM(RTRIM(i.Menu)) = N''经营分析''
      AND LTRIM(RTRIM(ISNULL(i.UserName, N''''))) <> N''''
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.JingYingFenXi AS dst
          WHERE dst.FeishuUserName = LTRIM(RTRIM(i.UserName))
            AND dst.UsedAt >= DATEADD(SECOND, -5, CAST(i.[Time] AS DATETIME2(0)))
            AND dst.UsedAt <= DATEADD(SECOND, 5, CAST(i.[Time] AS DATETIME2(0)))
      );
END;
');
"""


def apply_migration() -> tuple[int, tuple | None]:
    connection = pytds.connect(**sql_server_config(), timeout=30)
    try:
        cursor = connection.cursor()
        cursor.execute(MIGRATION_SQL)
        if not connection.autocommit:
            connection.commit()
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.JingYingFenXi")
        count = int(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT TOP (1) FeishuUserName, UsedAt, AccessPath
            FROM dbo.JingYingFenXi
            ORDER BY UsedAt DESC, Id DESC;
            """
        )
        return count, cursor.fetchone()
    except Exception:
        if not connection.autocommit:
            connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    total, latest = apply_migration()
    print({"table": "dbo.JingYingFenXi", "rowCount": total, "latest": latest})
