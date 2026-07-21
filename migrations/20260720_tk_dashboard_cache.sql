SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.TK_KanBan_HuanCun', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TK_KanBan_HuanCun (
        HuanCunJian NVARCHAR(400) NOT NULL
            CONSTRAINT PK_TK_KanBan_HuanCun PRIMARY KEY,
        ShuJu NVARCHAR(MAX) NOT NULL,
        GengXinShiJian DATETIME2(0) NOT NULL,
        GuoQiShiJian DATETIME2(0) NOT NULL
    );

    CREATE INDEX IX_TK_KanBan_HuanCun_GuoQiShiJian
        ON dbo.TK_KanBan_HuanCun (GuoQiShiJian);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.extended_properties
    WHERE major_id = OBJECT_ID(N'dbo.TK_KanBan_HuanCun')
      AND minor_id = 0
      AND name = N'MS_Description'
)
BEGIN
    EXEC sys.sp_addextendedproperty
        @name=N'MS_Description', @value=N'TK看板预计算结果缓存，用于页面秒开和后台刷新',
        @level0type=N'SCHEMA', @level0name=N'dbo',
        @level1type=N'TABLE', @level1name=N'TK_KanBan_HuanCun';
END;
