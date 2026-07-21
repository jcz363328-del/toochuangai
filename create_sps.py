
import bjc

def create_stored_procedures():
    # 1. Drop existing SPs if they exist
    drop_sql = """
    IF OBJECT_ID('sp_TK_Dashboard_GetMetrics', 'P') IS NOT NULL DROP PROCEDURE sp_TK_Dashboard_GetMetrics;
    IF OBJECT_ID('sp_TK_Dashboard_GetTargets', 'P') IS NOT NULL DROP PROCEDURE sp_TK_Dashboard_GetTargets;
    """
    try:
        bjc.dui_db(drop_sql, show_result=True)
        print("Dropped existing procedures.")
    except Exception as e:
        print(f"Error dropping procedures: {e}")

    # 2. Create sp_TK_Dashboard_GetMetrics
    # Note: Using dynamic SQL because passing array/list of shops is tricky without table types
    sp_metrics_sql = """
    CREATE PROCEDURE sp_TK_Dashboard_GetMetrics
        @StartDate VARCHAR(20),
        @EndDate VARCHAR(20),
        @ShopList NVARCHAR(MAX),
        @Year INT,
        @Month INT
    AS
    BEGIN
        SET NOCOUNT ON;
        DECLARE @Sql NVARCHAR(MAX);
        DECLARE @Yesterday VARCHAR(20);

        SET @Yesterday = CONVERT(VARCHAR(10), DATEADD(DAY, -1, GETDATE()), 120);

        SET @Sql = N'
        SELECT 
            j.platform_commission,
            j.vat_tax,
            j.adjustment_fee,
            j.other_platform_fee,
            j.monthly_sales,
            j.logistics_fee,
            j.influencer_commission,
            j.activity_service_fee,
            f.tax_fee,
            f.storage_fee,
            f.other_costs,
            f.ad_fee,
            r.qd_wage,
            r.sz_wage,
            r.qd_rent,
            r.sz_rent,
            (SELECT ISNULL(SUM(d.xiaoliang * zd.caigoujia),0)/6.5 FROM v_TK_JieSuan j WITH (NOLOCK) INNER JOIN TK_DingDan d WITH (NOLOCK) ON d.danhao = j.单号 INNER JOIN zidian zd WITH (NOLOCK) ON zd.sku = d.sku WHERE j.结算日期 >= ''' + @StartDate + ''' AND j.结算日期 <= ''' + @EndDate + ''' AND j.店 IN (' + @ShopList + ') AND j.销量 > 0 AND d.sku IS NOT NULL),
            (
                SELECT
                    ISNULL(SUM(d.xiaoliang * zd.TouCheng), 0) / 6.5
                FROM v_TK_JieSuan j WITH (NOLOCK)
                INNER JOIN TK_DingDan d WITH (NOLOCK) ON d.danhao = j.单号
                INNER JOIN zidian_toucheng zd WITH (NOLOCK) ON zd.sku = d.sku
                WHERE j.结算日期 >= ''' + @StartDate + '''
                  AND j.结算日期 <= ''' + @EndDate + '''
                  AND j.店 IN (' + @ShopList + ')
                  AND zd.Guo = ''美国''
                  AND j.销量 > 0
                  AND d.sku IS NOT NULL
            )
            + (
                SELECT
                    ISNULL(SUM(TKDD.xiaoliang * zd.TouCheng), 0) / 6.5
                FROM tk_dingdan AS TKDD WITH (NOLOCK)
                INNER JOIN zidian_toucheng AS zd WITH (NOLOCK) ON zd.sku = TKDD.sku
                INNER JOIN zidian AS zdd WITH (NOLOCK) ON zdd.sku = TKDD.sku
                WHERE TKDD.fahuoshijian >= ''' + @StartDate + '''
                  AND TKDD.fahuoshijian <= ''' + @EndDate + '''
                  AND TKDD.shifouyangpin = ''是''
                  AND zdd.dian IN (' + @ShopList + ')
                  AND zd.Guo = ''美国''
            )
            + (
                SELECT
                    ISNULL(SUM(sh.shuliang * zd.TouCheng), 0) / 6.5
                FROM tk_dingdan_shouhou AS sh WITH (NOLOCK)
                INNER JOIN zidian_toucheng AS zd WITH (NOLOCK) ON zd.sku = sh.sku
                INNER JOIN zidian AS zdd WITH (NOLOCK) ON zdd.sku = sh.sku
                WHERE sh.fahuoshijian >= ''' + @StartDate + '''
                  AND sh.fahuoshijian <= ''' + @EndDate + '''
                  AND sh.dian IN (' + @ShopList + ')
                  AND zd.Guo = ''美国''
            ),
            (SELECT ISNULL(SUM(ISNULL(销量,0)) - SUM(ISNULL(退款量,0)),0) FROM v_TK_JieSuan WITH (NOLOCK) WHERE 店 IN (' + @ShopList + ') AND 结算日期 >= ''' + @StartDate + ''' AND 结算日期 <= ''' + @EndDate + ''' ),
            y.infl_count,
            y.video_count,
            o.op_qd,
            o.op_sz,
            r.rijun_total,
            ys.yesterday_sales
        FROM
            (
                SELECT
                    ISNULL(SUM(平台佣金),0) AS platform_commission,
                    ISNULL(SUM(-VAT税),0) AS vat_tax,
                    ISNULL(SUM(调整费),0) AS adjustment_fee,
                    ISNULL(SUM(平台其他费),0) AS other_platform_fee,
                    ISNULL(SUM(考核销售额),0) AS monthly_sales,
                    ISNULL(SUM(-ISNULL(物流运费,0) - ISNULL(平台实际运费,0) - ISNULL(运费折扣,0) - ISNULL(退货运费,0)),0)
                    + ISNULL((
                        SELECT SUM(shijiyunfei)
                        FROM TK_DingDan_ShouHou WITH (NOLOCK)
                        WHERE baoguozhuangtai <> ''已作废''
                          AND dian IN (' + @ShopList + ')
                          AND fahuoshijian >= ''' + @StartDate + '''
                          AND fahuoshijian <= ''' + @EndDate + '''
                    ), 0)
                    + ISNULL((
                        SELECT -SUM(yunfei * xiaoliang)
                        FROM tk_dingdan WITH (NOLOCK)
                        WHERE shifouyangpin = ''是''
                          AND fahuoshijian >= ''' + @StartDate + '''
                          AND fahuoshijian <= ''' + @EndDate + '''
                          AND dian IN (' + @ShopList + ')
                    ), 0) AS logistics_fee,
                    ISNULL(SUM(达人佣金),0) AS influencer_commission,
                    ISNULL(SUM(活动服务费),0) AS activity_service_fee
                FROM v_TK_JieSuan WITH (NOLOCK)
                WHERE 结算日期 >= ''' + @StartDate + ''' AND 结算日期 <= ''' + @EndDate + ''' AND 店 IN (' + @ShopList + ')
            ) AS j,
            (
                SELECT
                    ISNULL(SUM(CASE WHEN xiangmu=''税金'' THEN feiyonge ELSE 0 END),0)/6.5 AS tax_fee,
                    ISNULL(SUM(CASE WHEN xiangmu IN (''入库费'',''仓储费'',''退货费'') THEN feiyonge ELSE 0 END),0) AS storage_fee,
                    ISNULL(SUM(CASE WHEN xiangmu IN (''刷单费'',''售后'',''网红坑位费'',''给网红购买产品费'') THEN feiyonge ELSE 0 END),0) AS other_costs,
                    ISNULL(SUM(CASE WHEN xiangmu=''广告'' THEN feiyonge ELSE 0 END),0) AS ad_fee
                FROM TK_FeiYong WITH (NOLOCK)
                WHERE riqi >= ''' + @StartDate + ''' AND riqi <= ''' + @EndDate + ''' AND dian IN (' + @ShopList + ')
            ) AS f,
            (
                SELECT
                    ISNULL(SUM(青岛工资日均),0) * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''青岛'' AND 项目 = ''工资'' AND 店铺 IN (' + @ShopList + ')), 0) AS qd_wage,
                    ISNULL(SUM(深圳工资日均),0) * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''深圳'' AND 项目 = ''工资'' AND 店铺 IN (' + @ShopList + ')), 0) AS sz_wage,
                    ISNULL(SUM(青岛房租日均),0) * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''青岛'' AND 项目 = ''房租'' AND 店铺 IN (' + @ShopList + ')), 0) AS qd_rent,
                    ISNULL(SUM(深圳房租日均),0) * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''深圳'' AND 项目 = ''房租'' AND 店铺 IN (' + @ShopList + ')), 0) AS sz_rent,
                    ISNULL(SUM(青岛房租日均 + 深圳房租日均 + 青岛工资日均 + 深圳工资日均),0) AS rijun_total
                FROM v_TK_RiJunFeiYong WITH (NOLOCK)
                WHERE riqi >= ''' + @StartDate + ''' AND riqi <= ''' + @EndDate + '''
            ) AS r,
            (
                SELECT
                    ISNULL(COUNT(DISTINCT 网红名),0) AS infl_count,
                    ISNULL((
                        SELECT COUNT(*) 
                        FROM v_TK_HeZuoShiPin WITH (NOLOCK)
                        WHERE faburiqi >= ''' + @StartDate + '''
                          AND faburiqi <= ''' + @EndDate + '''
                          AND dian IN (' + @ShopList + ')
                    ),0) AS video_count
                FROM v_tk_yibiaopan WITH (NOLOCK)
                WHERE 最新发货日期 >= ''' + @StartDate + ''' AND 最新发货日期 <= ''' + @EndDate + ''' AND 店铺 IN (' + @ShopList + ')
            ) AS y,
            (
                SELECT
                    ISNULL(SUM(CASE WHEN 项目 = ''TK项目'' THEN 贷方 ELSE 0 END),0)/6.5 * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''青岛'' AND 项目 = ''经营管理费'' AND 店铺 IN (' + @ShopList + ')), 0) AS op_qd,
                    ISNULL(SUM(CASE WHEN 项目 = ''深圳TK'' THEN 贷方 ELSE 0 END),0)/6.5 * ISNULL((SELECT 比例 FROM tk_费用分摊比例 WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 地区 = ''深圳'' AND 项目 = ''经营管理费'' AND 店铺 IN (' + @ShopList + ')), 0) AS op_sz
                FROM 财务_费用明细 WITH (NOLOCK)
                WHERE 日期 >= ''' + @StartDate + ''' AND 日期 <= ''' + @EndDate + '''
            ) AS o,
            (
                SELECT
                    ISNULL(SUM(考核销售额),0) AS yesterday_sales
                FROM v_TK_JieSuan WITH (NOLOCK)
                WHERE 结算日期 = ''' + @Yesterday + ''' AND 店 IN (' + @ShopList + ')
            ) AS ys
        ';

        EXEC sp_executesql @Sql;
    END
    """
    try:
        bjc.dui_db(sp_metrics_sql, show_result=True)
        print("Created sp_TK_Dashboard_GetMetrics.")
    except Exception as e:
        print(f"Error creating sp_TK_Dashboard_GetMetrics: {e}")

    # 3. Create sp_TK_Dashboard_GetTargets
    sp_targets_sql = """
    CREATE PROCEDURE sp_TK_Dashboard_GetTargets
        @Year INT,
        @Month INT,
        @ShopList NVARCHAR(MAX)
    AS
    BEGIN
        SET NOCOUNT ON;
        DECLARE @Sql NVARCHAR(MAX);

        SET @Sql = N'
        SELECT 
            ISNULL(SUM(CASE WHEN ISNUMERIC(实时保本额) = 1 THEN CONVERT(DECIMAL(18,2), 实时保本额) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(销售量) = 1 THEN CONVERT(DECIMAL(18,2), 销售量) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(销售额) = 1 THEN CONVERT(DECIMAL(18,2), 销售额) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(净利润) = 1 THEN CONVERT(DECIMAL(18,2), 净利润) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(毛利润) = 1 THEN CONVERT(DECIMAL(18,2), 毛利润) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(达人佣金) = 1 THEN CONVERT(DECIMAL(18,2), 达人佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(达人数) = 1 THEN CONVERT(DECIMAL(18,2), 达人数) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(达人视频费) = 1 THEN CONVERT(DECIMAL(18,2), 达人视频费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(视频数) = 1 THEN CONVERT(DECIMAL(18,2), 视频数) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(活动服务费) = 1 THEN CONVERT(DECIMAL(18,2), 活动服务费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(广告费) = 1 THEN CONVERT(DECIMAL(18,2), 广告费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(平台佣金) = 1 THEN CONVERT(DECIMAL(18,2), 平台佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(VAT) = 1 THEN CONVERT(DECIMAL(18,2), VAT) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(调整费) = 1 THEN CONVERT(DECIMAL(18,2), 调整费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(其他) = 1 THEN CONVERT(DECIMAL(18,2), 其他) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(经营管理费青岛) = 1 THEN CONVERT(DECIMAL(18,2), 经营管理费青岛) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(经营管理费深圳) = 1 THEN CONVERT(DECIMAL(18,2), 经营管理费深圳) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(产品成本) = 1 THEN CONVERT(DECIMAL(18,2), 产品成本) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(头程费用) = 1 THEN CONVERT(DECIMAL(18,2), 头程费用) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(尾程项目) = 1 THEN CONVERT(DECIMAL(18,2), 尾程项目) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(项目尾程仓储费入库费) = 1 THEN CONVERT(DECIMAL(18,2), 项目尾程仓储费入库费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(工资青岛) = 1 THEN CONVERT(DECIMAL(18,2), 工资青岛) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(工资深圳) = 1 THEN CONVERT(DECIMAL(18,2), 工资深圳) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(房租青岛) = 1 THEN CONVERT(DECIMAL(18,2), 房租青岛) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(房租深圳) = 1 THEN CONVERT(DECIMAL(18,2), 房租深圳) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(创作者佣金) = 1 THEN CONVERT(DECIMAL(18,2), 创作者佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(联盟伙伴佣金) = 1 THEN CONVERT(DECIMAL(18,2), 联盟伙伴佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(广告订单佣金) = 1 THEN CONVERT(DECIMAL(18,2), 广告订单佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(达人渠道号佣金) = 1 THEN CONVERT(DECIMAL(18,2), 达人渠道号佣金) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(刷单费) = 1 THEN CONVERT(DECIMAL(18,2), 刷单费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(售后) = 1 THEN CONVERT(DECIMAL(18,2), 售后) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(网红坑位费) = 1 THEN CONVERT(DECIMAL(18,2), 网红坑位费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(给网红购买产品费) = 1 THEN CONVERT(DECIMAL(18,2), 给网红购买产品费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(达人礼品费) = 1 THEN CONVERT(DECIMAL(18,2), 达人礼品费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(入库费) = 1 THEN CONVERT(DECIMAL(18,2), 入库费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(仓储费) = 1 THEN CONVERT(DECIMAL(18,2), 仓储费) ELSE 0 END),0),
            ISNULL(SUM(CASE WHEN ISNUMERIC(退货费) = 1 THEN CONVERT(DECIMAL(18,2), 退货费) ELSE 0 END),0)
        FROM tk_yuedumubiao 
        WHERE 年 = ' + CAST(@Year AS NVARCHAR) + ' AND 月 = ' + CAST(@Month AS NVARCHAR) + ' AND 店 IN (' + @ShopList + ')
        ';

        EXEC sp_executesql @Sql;
    END
    """
    try:
        bjc.dui_db(sp_targets_sql, show_result=True)
        print("Created sp_TK_Dashboard_GetTargets.")
    except Exception as e:
        print(f"Error creating sp_TK_Dashboard_GetTargets: {e}")

if __name__ == "__main__":
    create_stored_procedures()
