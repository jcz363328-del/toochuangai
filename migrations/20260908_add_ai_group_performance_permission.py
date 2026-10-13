"""Add the AI-only group performance permission row."""

from bjc import dui_db


SQL = """
IF EXISTS (SELECT 1 FROM dbo.quanxian WHERE GongNeng = 'ai_group_performance')
    UPDATE dbo.quanxian
       SET MingCheng=N'组别经营数据', YongHu=N'', BuMen=N'AI部',
           FuJiGongNeng=N'ai_dept', MiaoShu=N'按月份和组别查询店铺及站点经营数据，仅允许 AI部访问'
     WHERE GongNeng='ai_group_performance';
ELSE
    INSERT INTO dbo.quanxian (GongNeng,MingCheng,YongHu,BuMen,FuJiGongNeng,MiaoShu)
    VALUES ('ai_group_performance',N'组别经营数据',N'',N'AI部',N'ai_dept',N'按月份和组别查询店铺及站点经营数据，仅允许 AI部访问');
"""


if __name__ == "__main__":
    dui_db(SQL)
    print("ai_group_performance permission is ready")
