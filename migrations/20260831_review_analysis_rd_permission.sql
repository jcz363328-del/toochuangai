SET NOCOUNT ON;

UPDATE dbo.quanxian
SET BuMen = CASE
    WHEN NULLIF(LTRIM(RTRIM(ISNULL(BuMen, N''))), N'') IS NULL THEN N'研发部'
    ELSE LTRIM(RTRIM(BuMen)) + N'；研发部'
END
WHERE GongNeng = N'review_analysis'
  AND CHARINDEX(N'研发部', ISNULL(BuMen, N'')) = 0;
