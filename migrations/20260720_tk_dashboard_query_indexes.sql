SET NOCOUNT ON;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_DingDan')
      AND name = N'IX_TK_DingDan_Dian_DingGouShiJian_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_DingDan_Dian_DingGouShiJian_Dashboard
        ON dbo.TK_DingDan (Dian, DingGouShiJian)
        INCLUDE (
            DanHao, MSKU, ChanPinID, ZhuangTai, TuiKuan, ChanPinJinE,
            MaiJiaShangPinZheKou, XiaoShouShouYi, ShuiFei,
            PingTaiShangPinZheKou, Guo
        );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_BDDingDan')
      AND name = N'IX_TK_BDDingDan_DanHao_SKU_ZhuangTai_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_BDDingDan_DanHao_SKU_ZhuangTai_Dashboard
        ON dbo.TK_BDDingDan (DanHao, SKU, ZhuangTai);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_JieSuan')
      AND name = N'IX_TK_JieSuan_Dian_JieSuanRiQi_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_JieSuan_Dian_JieSuanRiQi_Dashboard
        ON dbo.TK_JieSuan ([店], [结算日期])
        INCLUDE (
            [单号], [销量], [退款量], [佣金], [推荐费], [退款管理费], [交易费],
            [VAT税], [调整费], [平台其他费],
            [销售额], [销售额退款], [促销折扣], [促销折扣退款], [买家支付运费],
            [物流运费], [平台实际运费], [运费折扣], [退货运费], [创作者佣金],
            [联盟伙伴佣金], [广告订单佣金], [闪购服务费], [促销活动费]
        );
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_FeiYong')
      AND name = N'IX_TK_FeiYong_Dian_RiQi_XiangMu_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_FeiYong_Dian_RiQi_XiangMu_Dashboard
        ON dbo.TK_FeiYong (Dian, RiQi, XiangMu)
        INCLUDE (FeiYongE);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_DingDan_ShouHou')
      AND name = N'IX_TK_DingDan_ShouHou_Dian_FaHuoShiJian_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_DingDan_ShouHou_Dian_FaHuoShiJian_Dashboard
        ON dbo.TK_DingDan_ShouHou (Dian, FaHuoShiJian)
        INCLUDE (DingDanLeiXing, BaoGuoZhuangTai, CaiGouChengBen, ShiJiYunFei, ShuLiang, SKU);
END;

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TK_DingDan')
      AND name = N'IX_TK_DingDan_Dian_FaHuoShiJian_Dashboard'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_TK_DingDan_Dian_FaHuoShiJian_Dashboard
        ON dbo.TK_DingDan (Dian, FaHuoShiJian)
        INCLUDE (ShiFouYangPin, SKU, XiaoLiang, YunFei);
END;
