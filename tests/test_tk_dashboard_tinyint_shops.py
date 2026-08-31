import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = ROOT / "tk_total_dashboard.py"


def load_tinyint_shop_helper():
    source = BACKEND_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_tinyint_shop_in_clause"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(BACKEND_PATH), "exec"), namespace)
    return namespace["_tinyint_shop_in_clause"]


class TkDashboardTinyintShopTests(unittest.TestCase):
    def test_out_of_range_and_invalid_shops_are_excluded(self):
        build_clause = load_tinyint_shop_helper()

        self.assertEqual(
            build_clause(["82", "255", "601", "82", "bad", "1.0"]),
            "82,255",
        )

    def test_empty_tinyint_shop_selection_produces_safe_no_match_clause(self):
        build_clause = load_tinyint_shop_helper()

        self.assertEqual(build_clause(["601", "shop-x"]), "NULL")

    def test_active_fee_queries_use_the_tinyint_safe_clause(self):
        source = BACKEND_PATH.read_text(encoding="utf-8")
        fast_block = source.split(
            "def _fetch_dashboard_metrics_fast(", 1
        )[1].split("def _build_dashboard_shell_payload(", 1)[0]
        compute_block = source.split(
            "def _compute_metrics_payload(", 1
        )[1].split("def _get_cached_metrics_payload(", 1)[0]

        self.assertIn("AND dian IN ({fee_in_clause})", fast_block)
        self.assertEqual(
            compute_block.count("AND dian IN ({fee_in_clause})"),
            3,
        )


if __name__ == "__main__":
    unittest.main()
