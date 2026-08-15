from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinanceAllocationCountryTests(unittest.TestCase):
    def test_allocation_import_requires_and_persists_country(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        route = source.split("def import_allocation_ratio():", 1)[1].split(
            "def import_wage_rent():", 1
        )[0]

        self.assertIn("required = ['年','月','国','地区','项目','店铺','比例']", route)
        self.assertIn("guo = esc(row.get(cols['国']))", route)
        self.assertIn("f\"国 = '{guo}'\"", route)
        self.assertIn("(国 IS NULL OR LTRIM(RTRIM(国)) = '')", route)
        self.assertIn("SET 国 = '{guo}', 比例 = {bili}", route)
        self.assertIn("(年, 月, 国, 地区, 项目, 店铺, 比例)", route)

    def test_allocation_import_ui_documents_country_column(self):
        template = (ROOT / "templates" / "finance_modules.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("年、月、国、地区、项目、店铺、比例", template)

    def test_allocation_country_migration_is_idempotent(self):
        migration = (
            ROOT / "migrations" / "20260815_add_country_to_allocation_ratio.py"
        ).read_text(encoding="utf-8")

        self.assertIn("COL_LENGTH(N'dbo.tk_费用分摊比例', N'国') IS NULL", migration)
        self.assertIn("ADD [国] NVARCHAR(50) NULL", migration)
        self.assertIn("IX_allocation_ratio_country_key", migration)


if __name__ == "__main__":
    unittest.main()
