#!/usr/bin/env python3
"""Build an atomic, per-campaign snapshot for the local diagnostic service."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sellfox_ad_diagnostic_server import (
    CAMPAIGN_ID_RE,
    DEFAULT_MATURE_PAYLOAD,
    DEFAULT_SNAPSHOT_DIR,
    DiagnosticError,
    DiagnosticService,
    SnapshotStore,
    compact_overview_snapshot,
    snapshot_refresh_errors,
)
from sellfox_ads_monitor import load_api_credentials, single_instance
from sellfox_import import as_text


def refresh_snapshot_batch(
    service: DiagnosticService,
    store: SnapshotStore,
    *,
    batch_size: int = 8,
    delay_seconds: float = 0.5,
    requested_campaign_ids: Sequence[str] = (),
    catalog_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    catalog = (
        dict(catalog_payload)
        if catalog_payload is not None
        else service.campaigns(refresh=True)
    )
    rows = catalog.get("campaigns")
    if not isinstance(rows, list):
        raise ValueError("活动列表响应格式异常。")
    campaign_ids = [
        as_text(row.get("campaignId") or row.get("campaign_id")) for row in rows
    ]
    if any(not CAMPAIGN_ID_RE.fullmatch(item) for item in campaign_ids):
        raise ValueError("活动列表包含无效 ID。")
    if len(campaign_ids) != len(set(campaign_ids)):
        raise ValueError("活动列表包含重复 ID。")

    store.write_hot("campaigns", catalog, started)
    state_path = store.root / "batch-state.json"
    state = store._read_json(state_path) or {}
    refreshed = state.get("campaigns")
    refreshed = refreshed if isinstance(refreshed, dict) else {}

    def refreshed_at(campaign_id: str) -> str:
        return as_text(refreshed.get(campaign_id))

    requested = [as_text(item) for item in requested_campaign_ids]
    if len(requested) != len(set(requested)):
        raise ValueError("指定活动包含重复 ID。")
    unknown = sorted(set(requested).difference(campaign_ids))
    if unknown:
        raise ValueError(f"指定活动不在当前店铺：{','.join(unknown)}")
    selected = requested or sorted(campaign_ids, key=refreshed_at)[:batch_size]
    updated: list[str] = []
    failures: list[str] = []
    for index, campaign_id in enumerate(selected, 1):
        logging.info("刷新活动快照 %s/%s：%s", index, len(selected), campaign_id)
        try:
            detail = service.campaign_detail(
                campaign_id, refresh=True, section="full"
            )
            invalid = snapshot_refresh_errors(detail)
            if invalid:
                raise ValueError(f"下钻报表未通过验证：{','.join(invalid)}")
            generated_at = datetime.now(timezone.utc)
            store.write_hot("full", detail, generated_at, campaign_id)
            store.write_hot(
                "overview",
                compact_overview_snapshot(detail),
                generated_at,
                campaign_id,
            )
            refreshed[campaign_id] = generated_at.isoformat(timespec="seconds")
            updated.append(campaign_id)
            store._write_json(
                state_path,
                {
                    "schema_version": "sellfox-ad-diagnostic-batch-state-v1",
                    "shop_id": catalog.get("shop", {}).get("shop_id"),
                    "updated_at": generated_at.isoformat(timespec="seconds"),
                    "campaigns": refreshed,
                },
            )
        except Exception:
            logging.warning("活动快照刷新失败：%s", campaign_id)
            failures.append(campaign_id)
        if delay_seconds and index < len(selected):
            time.sleep(delay_seconds)

    finished = datetime.now(timezone.utc)
    return {
        "status": "partial" if failures else "ok",
        "shop_id": catalog.get("shop", {}).get("shop_id"),
        "campaign_count": len(campaign_ids),
        "batch_size": batch_size,
        "selected": selected,
        "updated": updated,
        "failures": failures,
        "known_snapshot_count": sum(item in refreshed for item in campaign_ids),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "finished_at": finished.isoformat(timespec="seconds"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="定时构建广告诊断快照")
    parser.add_argument("--mature-payload", type=Path, default=DEFAULT_MATURE_PAYLOAD)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--campaign-id", action="append", default=[])
    parser.add_argument("--check-config", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (
        args.batch_size < 1
        or args.batch_size > 25
        or args.delay_seconds < 0
        or len(args.campaign_id) > 25
        or any(not CAMPAIGN_ID_RE.fullmatch(item) for item in args.campaign_id)
    ):
        raise SystemExit("快照参数无效。")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        load_api_credentials()
        if args.check_config:
            print(json.dumps({"status": "ok", "read_only": True}, ensure_ascii=False))
            return 0
        with single_instance():
            service = DiagnosticService(
                mature_payload_path=args.mature_payload.resolve(),
                snapshot_dir=None,
            )
            manifest = refresh_snapshot_batch(
                service,
                SnapshotStore(args.snapshot_dir),
                batch_size=args.batch_size,
                delay_seconds=args.delay_seconds,
                requested_campaign_ids=args.campaign_id,
            )
    except DiagnosticError as exc:
        logging.error("快照刷新失败：%s", exc.error_code)
        return 1
    except Exception as exc:
        logging.error("快照刷新失败：%s", type(exc).__name__)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 1 if manifest["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
