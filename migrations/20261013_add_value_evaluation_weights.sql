IF OBJECT_ID(N'dbo.JiaZhiGuan_QuanZhong', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.JiaZhiGuan_QuanZhong (
        ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        LeiXing NVARCHAR(20) NOT NULL,
        Jian NVARCHAR(100) NOT NULL,
        QuanZhong DECIMAL(12,4) NOT NULL CONSTRAINT DF_JiaZhiGuan_QuanZhong_QuanZhong DEFAULT (1),
        GengXinShiJian DATETIME NOT NULL CONSTRAINT DF_JiaZhiGuan_QuanZhong_GengXinShiJian DEFAULT (GETDATE()),
        CONSTRAINT UQ_JiaZhiGuan_QuanZhong_LeiXing_Jian UNIQUE (LeiXing, Jian),
        CONSTRAINT CK_JiaZhiGuan_QuanZhong_QuanZhong CHECK (QuanZhong >= 0)
    );
END;
