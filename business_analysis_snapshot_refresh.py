"""Scheduled entry point for refreshing the business-analysis fiscal snapshot."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from business_analysis_fiscal_overview import refresh_fiscal_overview_snapshot
from business_analysis_store_tier_promotion import notify_store_tier_promotions
from business_analysis_store_tier_refresh import refresh_store_tiers
from business_analysis_store_tier_history_snapshot import refresh_store_tier_history_snapshot


def main():
    root = Path(__file__).resolve().parent
    store_tier_result = refresh_store_tiers()
    store_tier_history_result = refresh_store_tier_history_snapshot()
    promotion_result = None
    if store_tier_result.get("fromDate") and store_tier_result.get("throughDate"):
        promotion_result = notify_store_tier_promotions(
            date.fromisoformat(store_tier_result["fromDate"]),
            date.fromisoformat(store_tier_result["throughDate"]),
        )
    dashboard = subprocess.run(
        ["node", "scripts/refresh-dashboard-snapshot.mjs"],
        cwd=root / "business_analysis",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    dashboard_result = json.loads(dashboard.stdout.strip().splitlines()[-1])
    result = refresh_fiscal_overview_snapshot("2026-2027")
    result["storeTierRefresh"] = store_tier_result
    result["storeTierHistorySnapshot"] = store_tier_history_result
    result["storeTierPromotionNotifications"] = promotion_result or {
        "status": "up-to-date",
        "detected": 0,
        "sent": 0,
        "skipped": 0,
        "failed": [],
        "recipients": ["蔡晶", "王晓菁", "韩雅俊", "陈子烨", "周俊成", "崔晓晨"],
    }
    result["dashboardSnapshot"] = dashboard_result
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
