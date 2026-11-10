"""Generate the file-backed store-tier history used by the dashboard."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from bjc import sf_db
from business_analysis_store_tier_promotion import detect_promotions


SNAPSHOT_PATH = Path(__file__).resolve().parent / "business_analysis" / "data" / "store-tier-history-snapshot.json"


def refresh_store_tier_history_snapshot(query_fn=sf_db, output_path=SNAPSHOT_PATH):
    rows = query_fn("""
        SELECT CAST(cj.RiQi AS date), cj.Dian,
               CONCAT(CONVERT(nvarchar(20), cj.CengJi1), CONVERT(nvarchar(10), cj.CengJi2)),
               cj.CengJiID, dp.BuMen, dp.ZuZhang, dp.YunYing
          FROM CengJi cj
          LEFT JOIN v_PinPaiDianPu dp ON cj.Dian = dp.Dian
         ORDER BY cj.RiQi, cj.Dian
    """) or []
    payload_rows = [{
        "date": value[0].isoformat() if hasattr(value[0], "isoformat") else str(value[0])[:10],
        "store": int(value[1]),
        "tier": str(value[2] or ""),
        "tierRank": int(value[3]) if value[3] is not None else None,
        "department": str(value[4] or ""),
        "leader": str(value[5] or ""),
        "operator": str(value[6] or ""),
    } for value in rows]
    promotion_events = detect_promotions([
        (row["date"], row["store"], row["tier"], row["tierRank"])
        for row in payload_rows if row["tierRank"] is not None
    ])
    snapshot = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "maxDate": max((row["date"] for row in payload_rows), default=None),
        "promotionEvents": [{
            "store": event.store,
            "tier": event.tier,
            "tierRank": event.tier_rank,
            "qualifiedOn": event.qualified_on.isoformat(),
            "streakStartedOn": event.streak_started_on.isoformat(),
            "consecutive": event.consecutive,
            "previousQualifiedOn": (
                event.previous_qualified_on.isoformat() if event.previous_qualified_on else None
            ),
            "previousTier": event.previous_tier,
            "gapDays": event.gap_days,
        } for event in promotion_events],
        "rows": payload_rows,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{output_path.name}.", suffix=".tmp", dir=output_path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary_name, output_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return {
        "path": str(output_path),
        "generatedAt": snapshot["generatedAt"],
        "maxDate": snapshot["maxDate"],
        "rows": len(payload_rows),
        "promotionEvents": len(promotion_events),
    }
