SET XACT_ABORT ON;

IF OBJECT_ID(N'dbo.FeiShu_JiaGou', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.FeiShu_JiaGou (
        JiLuId BIGINT IDENTITY(1, 1) NOT NULL
            CONSTRAINT PK_FeiShu_JiaGou PRIMARY KEY,
        FeiShuBuMenId NVARCHAR(100) NOT NULL,
        FeiShuNeiBuBuMenId NVARCHAR(100) NULL,
        BuMenMingCheng NVARCHAR(200) NOT NULL,
        FuJiBuMenId NVARCHAR(100) NULL,
        FuJiBuMenMingCheng NVARCHAR(200) NULL,
        BuMenLuJing NVARCHAR(2000) NOT NULL,
        CengJi INT NOT NULL,
        PaiXu BIGINT NULL,
        FuZeRenYongHuId NVARCHAR(100) NULL,
        BuMenQunLiaoId NVARCHAR(100) NULL,
        ChengYuanShuLiang INT NULL,
        BuMenRenYuanMingCheng NVARCHAR(MAX) NULL,
        BuMenRenYuanXinXi NVARCHAR(MAX) NULL,
        DanWeiIdLieBiao NVARCHAR(MAX) NULL,
        ShiFouYouZiBuMen BIT NOT NULL
            CONSTRAINT DF_FeiShu_JiaGou_ShiFouYouZiBuMen DEFAULT (0),
        ShiFouYiShanChu BIT NOT NULL
            CONSTRAINT DF_FeiShu_JiaGou_ShiFouYiShanChu DEFAULT (0),
        TongBuShiJian DATETIME2(0) NOT NULL
            CONSTRAINT DF_FeiShu_JiaGou_TongBuShiJian DEFAULT (SYSDATETIME()),
        YuanShiShuJu NVARCHAR(MAX) NULL
    );
END;

IF COL_LENGTH(N'dbo.FeiShu_JiaGou', N'BuMenRenYuanMingCheng') IS NULL
    ALTER TABLE dbo.FeiShu_JiaGou ADD BuMenRenYuanMingCheng NVARCHAR(MAX) NULL;

IF COL_LENGTH(N'dbo.FeiShu_JiaGou', N'BuMenRenYuanXinXi') IS NULL
    ALTER TABLE dbo.FeiShu_JiaGou ADD BuMenRenYuanXinXi NVARCHAR(MAX) NULL;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.FeiShu_JiaGou')
      AND name = N'UQ_FeiShu_JiaGou_FeiShuBuMenId'
)
BEGIN
    CREATE UNIQUE INDEX UQ_FeiShu_JiaGou_FeiShuBuMenId
        ON dbo.FeiShu_JiaGou (FeiShuBuMenId);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.FeiShu_JiaGou')
      AND name = N'IX_FeiShu_JiaGou_FuJiBuMenId'
)
BEGIN
    CREATE INDEX IX_FeiShu_JiaGou_FuJiBuMenId
        ON dbo.FeiShu_JiaGou (FuJiBuMenId);
END;

IF EXISTS (
    SELECT 1
    FROM sys.extended_properties
    WHERE major_id = OBJECT_ID(N'dbo.FeiShu_JiaGou')
      AND minor_id = 0
      AND name = N'MS_Description'
)
    EXEC sys.sp_updateextendedproperty
        @name=N'MS_Description', @value=N'飞书通讯录部门组织架构，每行代表一个部门；数据来源企业自建应用：图创AI（App ID：cli_a824cfdcd32ed00c）',
        @level0type=N'SCHEMA', @level0name=N'dbo',
        @level1type=N'TABLE', @level1name=N'FeiShu_JiaGou';
ELSE
    EXEC sys.sp_addextendedproperty
        @name=N'MS_Description', @value=N'飞书通讯录部门组织架构，每行代表一个部门；数据来源企业自建应用：图创AI（App ID：cli_a824cfdcd32ed00c）',
        @level0type=N'SCHEMA', @level0name=N'dbo',
        @level1type=N'TABLE', @level1name=N'FeiShu_JiaGou';

DECLARE @ZiDuanShuoMing TABLE (
    ZiDuanMingCheng SYSNAME NOT NULL,
    ZiDuanJieShi NVARCHAR(4000) NOT NULL
);

INSERT INTO @ZiDuanShuoMing (ZiDuanMingCheng, ZiDuanJieShi)
VALUES
    (N'JiLuId', N'数据库自增主键'),
    (N'FeiShuBuMenId', N'飞书开放部门ID，作为部门唯一标识'),
    (N'FeiShuNeiBuBuMenId', N'飞书内部部门ID'),
    (N'BuMenMingCheng', N'部门名称'),
    (N'FuJiBuMenId', N'父级部门的飞书部门ID，0表示企业根组织'),
    (N'FuJiBuMenMingCheng', N'父级部门名称'),
    (N'BuMenLuJing', N'从顶级部门到当前部门的完整中文路径'),
    (N'CengJi', N'部门在组织架构中的层级，顶级部门为1'),
    (N'PaiXu', N'飞书通讯录中的部门排序值'),
    (N'FuZeRenYongHuId', N'部门负责人飞书用户ID'),
    (N'BuMenQunLiaoId', N'部门关联群聊ID'),
    (N'ChengYuanShuLiang', N'部门成员数量'),
    (N'BuMenRenYuanMingCheng', N'部门直属人员姓名，使用顿号分隔'),
    (N'BuMenRenYuanXinXi', N'部门直属人员明细，使用JSON保存，包含姓名、飞书用户Open ID、飞书内部用户ID、工号、职位和离职状态'),
    (N'DanWeiIdLieBiao', N'飞书单位ID列表，使用JSON保存'),
    (N'ShiFouYouZiBuMen', N'是否存在子部门：1是，0否'),
    (N'ShiFouYiShanChu', N'飞书部门是否已删除：1是，0否'),
    (N'TongBuShiJian', N'本条组织架构数据最近同步时间'),
    (N'YuanShiShuJu', N'飞书接口返回的部门原始JSON数据');

DECLARE @ZiDuanMingCheng SYSNAME;
DECLARE @ZiDuanJieShi NVARCHAR(4000);
DECLARE ZiDuanShuoMingYouBiao CURSOR LOCAL FAST_FORWARD FOR
    SELECT ZiDuanMingCheng, ZiDuanJieShi FROM @ZiDuanShuoMing;

OPEN ZiDuanShuoMingYouBiao;
FETCH NEXT FROM ZiDuanShuoMingYouBiao INTO @ZiDuanMingCheng, @ZiDuanJieShi;
WHILE @@FETCH_STATUS = 0
BEGIN
    IF EXISTS (
        SELECT 1
        FROM sys.extended_properties ep
        INNER JOIN sys.columns c
            ON c.object_id = ep.major_id
           AND c.column_id = ep.minor_id
        WHERE ep.major_id = OBJECT_ID(N'dbo.FeiShu_JiaGou')
          AND ep.name = N'MS_Description'
          AND c.name = @ZiDuanMingCheng
    )
        EXEC sys.sp_updateextendedproperty
            @name=N'MS_Description', @value=@ZiDuanJieShi,
            @level0type=N'SCHEMA', @level0name=N'dbo',
            @level1type=N'TABLE', @level1name=N'FeiShu_JiaGou',
            @level2type=N'COLUMN', @level2name=@ZiDuanMingCheng;
    ELSE
        EXEC sys.sp_addextendedproperty
            @name=N'MS_Description', @value=@ZiDuanJieShi,
            @level0type=N'SCHEMA', @level0name=N'dbo',
            @level1type=N'TABLE', @level1name=N'FeiShu_JiaGou',
            @level2type=N'COLUMN', @level2name=@ZiDuanMingCheng;

    FETCH NEXT FROM ZiDuanShuoMingYouBiao INTO @ZiDuanMingCheng, @ZiDuanJieShi;
END;
CLOSE ZiDuanShuoMingYouBiao;
DEALLOCATE ZiDuanShuoMingYouBiao;
