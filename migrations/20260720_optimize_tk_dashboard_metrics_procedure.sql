SET NOCOUNT ON;

DECLARE @ProcedureDefinition NVARCHAR(MAX) = OBJECT_DEFINITION(OBJECT_ID(N'dbo.sp_TK_Dashboard_GetMetrics'));

IF @ProcedureDefinition IS NOT NULL
   AND CHARINDEX(N'FROM v_TK_FeiYong WITH (NOLOCK)', @ProcedureDefinition) > 0
BEGIN
    SET @ProcedureDefinition = REPLACE(
        @ProcedureDefinition,
        N'FROM v_TK_FeiYong WITH (NOLOCK)',
        N'FROM TK_FeiYong WITH (NOLOCK)'
    );
    SET @ProcedureDefinition = STUFF(
        @ProcedureDefinition,
        CHARINDEX(N'CREATE PROCEDURE', UPPER(@ProcedureDefinition)),
        LEN(N'CREATE PROCEDURE'),
        N'ALTER PROCEDURE'
    );
    EXEC sys.sp_executesql @ProcedureDefinition;
END;
