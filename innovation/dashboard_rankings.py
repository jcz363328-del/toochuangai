from __future__ import annotations

from typing import Any, Iterable


def select_personal_proposal_performers(
    rows: Iterable[Iterable[Any]],
    *,
    total_limit: int = 5,
    effective_limit: int = 3,
) -> list[dict[str, Any]]:
    """按提案总数取前五名（含第五名并列），再取有效率前三名（含第三名并列）。"""
    normalized: list[dict[str, Any]] = []
    for raw in rows or []:
        values = list(raw)
        if len(values) < 4 or values[0] in (None, ""):
            continue
        count = int(values[2] or 0)
        effective_count = int(values[3] or 0)
        effective_rate = (
            float(values[4])
            if len(values) > 4 and values[4] is not None
            else (effective_count / count if count else 0.0)
        )
        normalized.append(
            {
                "name": str(values[0]),
                "department": str(values[1] or ""),
                "count": count,
                "effective_count": effective_count,
                "effective_rate": effective_rate,
            }
        )

    # 总量第五名如果并列，同量人员全部进入有效率排名。
    total_sorted = sorted(normalized, key=lambda item: (-item["count"], item["name"]))
    if len(total_sorted) <= total_limit:
        total_top = total_sorted
    else:
        total_cutoff = total_sorted[total_limit - 1]["count"]
        total_top = [item for item in total_sorted if item["count"] >= total_cutoff]
    effective_sorted = sorted(
        total_top,
        key=lambda item: (-item["effective_rate"], -item["count"], item["name"]),
    )
    if len(effective_sorted) <= effective_limit:
        return effective_sorted

    cutoff = effective_sorted[effective_limit - 1]["effective_rate"]
    return [item for item in effective_sorted if item["effective_rate"] >= cutoff]
