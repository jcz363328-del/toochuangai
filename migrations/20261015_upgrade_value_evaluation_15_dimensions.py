"""Upgrade the live 360 evaluation to the 15-dimension scoring workbook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytds
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from secret_settings import sql_server_config
from value_evaluation import DIMENSION_RELATIONSHIP_WEIGHTS, RELATIONSHIP_GROUPS


DEFAULT_WORKBOOK = Path(r"C:\Users\admin\Desktop\26 【图创】干部360度评估问卷及计分表 20261015.xlsx")
QUESTION_ROWS = (8, 9, 10, 11, 12, 15, 16, 17, 18, 19, 22, 23, 24, 27, 28)
MODULES = (
    ("品德素养", 1, 5),
    ("作风行为", 6, 10),
    ("使命担当", 11, 13),
    ("责任履行", 14, 15),
)


def _module_for(index: int) -> str:
    return next(name for name, start, end in MODULES if start <= index <= end)


def read_dimensions(path: Path) -> list[tuple[str, str, str, str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[2]
        dimensions = []
        for index, row_number in enumerate(QUESTION_ROWS, start=1):
            raw_name = str(sheet.cell(row_number, 2).value or "").strip()
            name_parts = [part.strip() for part in raw_name.splitlines() if part.strip()]
            item_name = name_parts[0]
            base = " · ".join(name_parts)
            score_lines = []
            for score, column in zip((5, 4, 3, 2, 1), range(3, 8)):
                description = str(sheet.cell(row_number, column).value or "").strip()
                score_lines.append(f"{score} 分：{description}")
            dimensions.append(
                (f"1-{index:02d}", _module_for(index), item_name, "\n".join([base] + score_lines))
            )
        return dimensions
    finally:
        workbook.close()


def apply_migration(path: Path) -> dict:
    dimensions = read_dimensions(path)
    if len(dimensions) != 15:
        raise RuntimeError(f"预期15个维度，实际读取到{len(dimensions)}个")
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute("ALTER TABLE JiaZhiGuan_NeiRong ALTER COLUMN DaiHao NVARCHAR(10) NULL")
        cursor.execute("ALTER TABLE JiaZhiGuan_NeiRong ALTER COLUMN NeiRong NVARCHAR(2000) NULL")
        cursor.execute("ALTER TABLE JiaZhiGuan_QuanZhong ALTER COLUMN LeiXing NVARCHAR(50) NOT NULL")
        cursor.execute("DELETE FROM JiaZhiGuan_NeiRong WHERE DaiHao LIKE N'1-%%'")
        cursor.executemany(
            "INSERT INTO JiaZhiGuan_NeiRong (DaiHao,DaXiang,XiaoXiang,NeiRong) VALUES (%s,%s,%s,%s)",
            dimensions,
        )
        cursor.execute(
            "DELETE FROM JiaZhiGuan_QuanZhong "
            "WHERE LeiXing IN (N'criterion',N'criterion_relationship')"
        )
        criterion_rows = [("criterion", code, 1) for code, _, _, _ in dimensions]
        matrix_rows = [
            ("criterion_relationship", f"{code}|{group}", weight)
            for code, weights in DIMENSION_RELATIONSHIP_WEIGHTS.items()
            for group, weight in weights.items()
        ]
        cursor.executemany(
            "INSERT INTO JiaZhiGuan_QuanZhong (LeiXing,Jian,QuanZhong,GengXinShiJian) "
            "VALUES (%s,%s,%s,GETDATE())",
            criterion_rows + matrix_rows,
        )
        connection.commit()
        return {"criteria": len(dimensions), "matrixWeights": len(matrix_rows)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify() -> dict:
    connection = pytds.connect(**sql_server_config())
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM JiaZhiGuan_NeiRong WHERE DaiHao LIKE N'1-%%'")
        criteria = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM JiaZhiGuan_QuanZhong WHERE LeiXing=N'criterion_relationship'"
        )
        matrix_weights = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM JiaZhiGuan_QuanZhong "
            "WHERE LeiXing=N'criterion_relationship' AND Jian LIKE N'%%|自评' AND QuanZhong=0"
        )
        zero_self_weights = int(cursor.fetchone()[0])
        return {
            "criteria": criteria,
            "matrixWeights": matrix_weights,
            "zeroSelfWeights": zero_self_weights,
        }
    finally:
        connection.close()


if __name__ == "__main__":
    workbook_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKBOOK
    print(apply_migration(workbook_path))
    print(verify())
