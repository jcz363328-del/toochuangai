import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from business_analysis_store_tier_history_snapshot import refresh_store_tier_history_snapshot


class StoreTierHistorySnapshotTests(unittest.TestCase):
    def test_refresh_writes_file_backed_history_snapshot(self):
        rows = [
            (date(2026, 10, 13), 2, "银1", 4, "运营一部", "周雪", "王丽爽"),
            (date(2026, 10, 14), 2, "银2", 5, "运营一部", "周雪", "王丽爽"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tier-history.json"
            result = refresh_store_tier_history_snapshot(lambda _sql: rows, output)
            snapshot = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("2026-10-14", result["maxDate"])
        self.assertEqual(2, result["rows"])
        self.assertEqual("银2", snapshot["rows"][1]["tier"])
        self.assertEqual("王丽爽", snapshot["rows"][1]["operator"])
        self.assertEqual(1, snapshot["schemaVersion"])
        self.assertIn("promotionEvents", snapshot)


if __name__ == "__main__":
    unittest.main()
