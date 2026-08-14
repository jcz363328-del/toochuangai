SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ProcedureDefinition NVARCHAR(MAX) =
    OBJECT_DEFINITION(OBJECT_ID(N'dbo.sp_TK_Dashboard_GetMetrics'));

IF @ProcedureDefinition IS NULL
    THROW 50001, N'缺少存储过程 dbo.sp_TK_Dashboard_GetMetrics', 1;

DECLARE @ScalarRatioLookup NVARCHAR(MAX) =
    N'(SELECT 比例 FROM tk_费用分摊比例';
DECLARE @AggregatedRatioLookup NVARCHAR(MAX) =
    N'(SELECT SUM(CASE WHEN ISNUMERIC(比例) = 1 THEN CONVERT(DECIMAL(18,6), 比例) ELSE 0 END) FROM tk_费用分摊比例';

IF CHARINDEX(@ScalarRatioLookup, @ProcedureDefinition) > 0
BEGIN
    SET @ProcedureDefinition = REPLACE(
        @ProcedureDefinition,
        @ScalarRatioLookup,
        @AggregatedRatioLookup
    );
    SET @ProcedureDefinition = STUFF(
        @ProcedureDefinition,
        CHARINDEX(N'CREATE PROCEDURE', UPPER(@ProcedureDefinition)),
        LEN(N'CREATE PROCEDURE'),
        N'ALTER PROCEDURE'
    );
    EXEC sys.sp_executesql @ProcedureDefinition;
END;

IF CHARINDEX(
    @ScalarRatioLookup,
    OBJECT_DEFINITION(OBJECT_ID(N'dbo.sp_TK_Dashboard_GetMetrics'))
) > 0
    THROW 50002, N'多店铺分摊比例子查询修复失败', 1;
