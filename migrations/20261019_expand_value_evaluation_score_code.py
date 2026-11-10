"""Expand score criterion codes for the 15-dimension 360 evaluation format."""

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
        cursor.execute(
            """
            IF EXISTS (
                SELECT 1
                  FROM INFORMATION_SCHEMA.COLUMNS
                 WHERE TABLE_NAME=N'JiaZhiGuan_DeFen'
                   AND COLUMN_NAME=N'DaiHao'
                   AND CHARACTER_MAXIMUM_LENGTH < 20
            )
                ALTER TABLE dbo.JiaZhiGuan_DeFen ALTER COLUMN DaiHao NVARCHAR(20) NULL;
            """
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
    print("value_evaluation_score_code=expanded")
