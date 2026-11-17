/* 创新专项存储。可重复执行。 */
IF OBJECT_ID(N'dbo.chuangxin_zhuanxiang', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.chuangxin_zhuanxiang (
        zhuanxiang_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        zhuanxiang_bianhao NVARCHAR(50) NOT NULL,
        biaoti NVARCHAR(200) NOT NULL,
        nanti_miaoshu NVARCHAR(MAX) NOT NULL,
        fabu_user_id NVARCHAR(100) NOT NULL,
        fabu_user_name NVARCHAR(100) NOT NULL,
        fabu_bumen NVARCHAR(100) NULL,
        chengjie_bumen NVARCHAR(100) NULL,
        zhuangtai VARCHAR(20) NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_zhuangtai DEFAULT 'caogao',
        jiangli_jifen INT NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_jiangli DEFAULT 0,
        jiangli_mingxi NVARCHAR(MAX) NULL,
        fabu_shijian DATETIME2 NULL,
        chuangjian_shijian DATETIME2 NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_created DEFAULT SYSDATETIME(),
        gengxin_shijian DATETIME2 NOT NULL CONSTRAINT DF_chuangxin_zhuanxiang_updated DEFAULT SYSDATETIME()
    )
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.chuangxin_zhuanxiang')
      AND name = N'UX_chuangxin_zhuanxiang_bianhao'
)
    CREATE UNIQUE INDEX UX_chuangxin_zhuanxiang_bianhao
    ON dbo.chuangxin_zhuanxiang(zhuanxiang_bianhao)
GO

IF EXISTS (
    SELECT 1
    FROM dbo.chuangxin_zhuanxiang
    WHERE zhuanxiang_bianhao LIKE N'%[^0-9]%'
)
BEGIN
    UPDATE dbo.chuangxin_zhuanxiang
    SET zhuanxiang_bianhao = N'LEGACY-' + CONVERT(NVARCHAR(20), zhuanxiang_id)
    WHERE zhuanxiang_bianhao LIKE N'%[^0-9]%'

    DECLARE @next_special_no INT = ISNULL((
        SELECT MAX(CASE WHEN zhuanxiang_bianhao NOT LIKE N'%[^0-9]%'
                        THEN CONVERT(INT, zhuanxiang_bianhao) END)
        FROM dbo.chuangxin_zhuanxiang
    ), 0) + 1

    ;WITH legacy_rows AS (
        SELECT zhuanxiang_id,
               ROW_NUMBER() OVER (ORDER BY zhuanxiang_id) AS row_no
        FROM dbo.chuangxin_zhuanxiang
        WHERE zhuanxiang_bianhao LIKE N'LEGACY-%'
    )
    UPDATE z
    SET zhuanxiang_bianhao = RIGHT(N'000' + CONVERT(NVARCHAR(20), @next_special_no + legacy_rows.row_no - 1), 3)
    FROM dbo.chuangxin_zhuanxiang z
    INNER JOIN legacy_rows ON legacy_rows.zhuanxiang_id = z.zhuanxiang_id
END
GO

IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_id') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_id BIGINT NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_zhuanxiang', N'chengjie_bumen') IS NULL
    ALTER TABLE dbo.chuangxin_zhuanxiang ADD chengjie_bumen NVARCHAR(100) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'tijiao_user_id') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD tijiao_user_id NVARCHAR(100) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'tijiao_user_avatar') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD tijiao_user_avatar NVARCHAR(500) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'xiangfa_zhuangtai') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD xiangfa_zhuangtai VARCHAR(20) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_pingfen') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_pingfen DECIMAL(5,2) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_pingyu') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_pingyu NVARCHAR(MAX) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'caina_user_id') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD caina_user_id NVARCHAR(100) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'caina_shijian') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD caina_shijian DATETIME2 NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_fafang_jifen') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_fafang_jifen INT NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_fafang_biaoshi') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_fafang_biaoshi BIT NOT NULL CONSTRAINT DF_chuangxin_tibao1_special_points DEFAULT 0
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_tongzhi_zhuangtai') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_tongzhi_zhuangtai VARCHAR(20) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_tibao1', N'zhuanxiang_tongzhi_shijian') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD zhuanxiang_tongzhi_shijian DATETIME2 NULL
GO

IF COL_LENGTH(N'dbo.chuangxin_liuzhuan1', N'zhuanxiang_id') IS NULL
    ALTER TABLE dbo.chuangxin_liuzhuan1 ADD zhuanxiang_id BIGINT NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_liuzhuan1', N'liuzhuan_leixing') IS NULL
    ALTER TABLE dbo.chuangxin_liuzhuan1 ADD liuzhuan_leixing VARCHAR(20) NULL
GO
IF COL_LENGTH(N'dbo.chuangxin_liuzhuan1', N'caozuo_user_id') IS NULL
    ALTER TABLE dbo.chuangxin_liuzhuan1 ADD caozuo_user_id NVARCHAR(100) NULL
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.chuangxin_tibao1')
      AND name = N'IX_chuangxin_tibao1_zhuanxiang'
)
    CREATE INDEX IX_chuangxin_tibao1_zhuanxiang
    ON dbo.chuangxin_tibao1(zhuanxiang_id, xiangfa_zhuangtai, 发起时间)
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.chuangxin_liuzhuan1')
      AND name = N'IX_chuangxin_liuzhuan1_zhuanxiang'
)
    CREATE INDEX IX_chuangxin_liuzhuan1_zhuanxiang
    ON dbo.chuangxin_liuzhuan1(zhuanxiang_id, 项目编号, 流转时间)
GO

IF OBJECT_ID(N'dbo.quanxian', N'U') IS NOT NULL
BEGIN
    UPDATE dbo.quanxian
    SET YongHu = N'',
        BuMen = N'人力资源与行政部；流程与AI部',
        FuJiGongNeng = N'innovation_proposals',
        MingCheng = N'创新专项管理',
        MiaoShu = N'人力资源与行政部和流程与AI部创建、发布和维护创新专项。',
        QiYong = 1,
        GengXinShiJian = SYSDATETIME()
    WHERE LTRIM(RTRIM(GongNeng)) = N'innovation_special_manage'

    IF @@ROWCOUNT = 0
        INSERT INTO dbo.quanxian
            (GongNeng, YongHu, BuMen, FuJiGongNeng, MingCheng, MiaoShu, QiYong, GengXinShiJian)
        VALUES
            (N'innovation_special_manage', N'', N'人力资源与行政部；流程与AI部',
             N'innovation_proposals', N'创新专项管理',
             N'人力资源与行政部和流程与AI部创建、发布和维护创新专项。', 1, SYSDATETIME())
END
GO


-- 专项附件与旧流转表兼容字段
IF COL_LENGTH('dbo.chuangxin_zhuanxiang', 'tupian_lujing') IS NULL
    ALTER TABLE dbo.chuangxin_zhuanxiang ADD tupian_lujing NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.chuangxin_zhuanxiang', 'shipin_lujing') IS NULL
    ALTER TABLE dbo.chuangxin_zhuanxiang ADD shipin_lujing NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.chuangxin_tibao1', N'图片详情') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD 图片详情 NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.chuangxin_tibao1', N'视频详情') IS NULL
    ALTER TABLE dbo.chuangxin_tibao1 ADD 视频详情 NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.chuangxin_liuzhuan1', N'流转备注') IS NULL
    ALTER TABLE dbo.chuangxin_liuzhuan1 ADD 流转备注 NVARCHAR(MAX) NULL;
GO
