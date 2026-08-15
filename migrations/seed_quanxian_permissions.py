"""扩展并初始化 dbo.quanxian；可重复执行，不删除现有权限。"""

from __future__ import annotations

import pytds

from department_permissions import PERMISSION_CONFIG
from permission_seed_data import build_permission_seed_rows
from secret_settings import sql_server_config


SCHEMA_SQL = r"""
IF OBJECT_ID(N'dbo.quanxian', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.quanxian (
        ID INT IDENTITY(1,1) NOT NULL,
        GongNeng NVARCHAR(200) NOT NULL CONSTRAINT DF_QuanXian_GongNeng DEFAULT(N''),
        YongHu NVARCHAR(MAX) NOT NULL CONSTRAINT DF_QuanXian_users DEFAULT(N''),
        BuMen NVARCHAR(MAX) NOT NULL CONSTRAINT DF_QuanXian_departments DEFAULT(N''),
        FuJiGongNeng NVARCHAR(1000) NULL,
        MingCheng NVARCHAR(200) NULL,
        MiaoShu NVARCHAR(1000) NULL,
        QiYong BIT NOT NULL CONSTRAINT DF_QuanXian_QiYong DEFAULT(1),
        GengXinShiJian DATETIME2(0) NOT NULL CONSTRAINT DF_QuanXian_GengXinShiJian DEFAULT(SYSDATETIME()),
        CONSTRAINT PK_QuanXian PRIMARY KEY (ID)
    );
END;

IF COL_LENGTH(N'dbo.quanxian', N'FuJiGongNeng') IS NULL
    ALTER TABLE dbo.quanxian ADD FuJiGongNeng NVARCHAR(1000) NULL;
IF COL_LENGTH(N'dbo.quanxian', N'MingCheng') IS NULL
    ALTER TABLE dbo.quanxian ADD MingCheng NVARCHAR(200) NULL;
IF COL_LENGTH(N'dbo.quanxian', N'MiaoShu') IS NULL
    ALTER TABLE dbo.quanxian ADD MiaoShu NVARCHAR(1000) NULL;
IF COL_LENGTH(N'dbo.quanxian', N'QiYong') IS NULL
    ALTER TABLE dbo.quanxian ADD QiYong BIT NOT NULL CONSTRAINT DF_QuanXian_QiYong DEFAULT(1);
IF COL_LENGTH(N'dbo.quanxian', N'GengXinShiJian') IS NULL
    ALTER TABLE dbo.quanxian ADD GengXinShiJian DATETIME2(0) NOT NULL CONSTRAINT DF_QuanXian_GengXinShiJian DEFAULT(SYSDATETIME());

DECLARE @DefaultConstraint SYSNAME;
DECLARE @DropConstraintSql NVARCHAR(500);

SELECT @DefaultConstraint = dc.name
FROM sys.default_constraints dc
JOIN sys.columns c ON c.default_object_id = dc.object_id
WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'GongNeng';
IF @DefaultConstraint IS NOT NULL
BEGIN
    SET @DropConstraintSql = N'ALTER TABLE dbo.quanxian DROP CONSTRAINT ' + QUOTENAME(@DefaultConstraint);
    EXEC sp_executesql @DropConstraintSql;
END;

SET @DefaultConstraint = NULL;
SELECT @DefaultConstraint = dc.name
FROM sys.default_constraints dc
JOIN sys.columns c ON c.default_object_id = dc.object_id
WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'YongHu';
IF @DefaultConstraint IS NOT NULL
BEGIN
    SET @DropConstraintSql = N'ALTER TABLE dbo.quanxian DROP CONSTRAINT ' + QUOTENAME(@DefaultConstraint);
    EXEC sp_executesql @DropConstraintSql;
END;

SET @DefaultConstraint = NULL;
SELECT @DefaultConstraint = dc.name
FROM sys.default_constraints dc
JOIN sys.columns c ON c.default_object_id = dc.object_id
WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'BuMen';
IF @DefaultConstraint IS NOT NULL
BEGIN
    SET @DropConstraintSql = N'ALTER TABLE dbo.quanxian DROP CONSTRAINT ' + QUOTENAME(@DefaultConstraint);
    EXEC sp_executesql @DropConstraintSql;
END;

ALTER TABLE dbo.quanxian ALTER COLUMN GongNeng NVARCHAR(200) NULL;
ALTER TABLE dbo.quanxian ALTER COLUMN YongHu NVARCHAR(MAX) NULL;
ALTER TABLE dbo.quanxian ALTER COLUMN BuMen NVARCHAR(MAX) NULL;

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    JOIN sys.columns c ON c.default_object_id = dc.object_id
    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'GongNeng'
)
    ALTER TABLE dbo.quanxian ADD CONSTRAINT DF_QuanXian_GongNeng DEFAULT(N'') FOR GongNeng;
IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    JOIN sys.columns c ON c.default_object_id = dc.object_id
    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'YongHu'
)
    ALTER TABLE dbo.quanxian ADD CONSTRAINT DF_QuanXian_users DEFAULT(N'') FOR YongHu;
IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints dc
    JOIN sys.columns c ON c.default_object_id = dc.object_id
    WHERE dc.parent_object_id = OBJECT_ID(N'dbo.quanxian') AND c.name = N'BuMen'
)
    ALTER TABLE dbo.quanxian ADD CONSTRAINT DF_QuanXian_departments DEFAULT(N'') FOR BuMen;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.quanxian') AND name = N'UX_QuanXian_GongNeng'
)
AND NOT EXISTS (
    SELECT LTRIM(RTRIM(GongNeng))
    FROM dbo.quanxian
    WHERE GongNeng IS NOT NULL
    GROUP BY LTRIM(RTRIM(GongNeng))
    HAVING COUNT(*) > 1
)
    CREATE UNIQUE NONCLUSTERED INDEX UX_QuanXian_GongNeng
        ON dbo.quanxian(GongNeng)
        WHERE GongNeng IS NOT NULL;
"""


UPSERT_SQL = r"""
UPDATE dbo.quanxian
SET YongHu=%s,
    BuMen=%s,
    FuJiGongNeng=%s,
    MingCheng=%s,
    MiaoShu=%s,
    QiYong=1,
    GengXinShiJian=SYSDATETIME()
WHERE LTRIM(RTRIM(GongNeng))=%s;

IF @@ROWCOUNT=0
BEGIN
    INSERT INTO dbo.quanxian
        (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
    VALUES
        (%s, %s, %s, %s, %s, %s, 1, SYSDATETIME());
END;
"""


def seed_permissions():
    rows = build_permission_seed_rows(PERMISSION_CONFIG)
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute(SCHEMA_SQL)
        cursor.execute("SELECT GongNeng, YongHu, BuMen FROM dbo.quanxian")
        existing_rows = {}
        for function_name, users, departments in (cursor.fetchall() or []):
            key = str(function_name or "").strip()
            if key:
                existing_rows[key] = {
                    "yonghu": str(users or "").strip(),
                    "bumen": str(departments or "").strip(),
                }
        for row in rows:
            existing = existing_rows.get(row["gongneng"], {})
            # 首次创建时写入盘点数据；后续重跑只更新层级和说明，
            # 不覆盖管理员已在数据库里调整的 YongHu/BuMen。
            merged_users = existing.get("yonghu", row["yonghu"])
            merged_departments = existing.get("bumen", row["bumen"])
            values = (
                merged_users,
                merged_departments,
                row["fujigongneng"],
                row["mingcheng"],
                row["miaoshu"],
                row["gongneng"],
                row["gongneng"],
                merged_users,
                merged_departments,
                row["fujigongneng"],
                row["mingcheng"],
                row["miaoshu"],
            )
            cursor.execute(UPSERT_SQL, values)
        if not connection.autocommit:
            connection.commit()
        return len(rows)
    finally:
        connection.close()
if __name__ == "__main__":
    print(f"seeded={seed_permissions()}")
