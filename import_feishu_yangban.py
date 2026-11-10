"""Import the authorized Feishu Base sample index into the local YangBan tables.

Run without flags for a read-only preview. Pass --apply to download attachments
and commit the database upsert in one transaction.
"""

from __future__ import annotations
from secret_settings import relocate_storage_path

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytds

from secret_settings import sql_server_config


BASE_TOKEN = "V8V3bwPnLaJVWysvfIqcE4SWnJc"
TABLE_ID = "tbl86KdGXl2QvkrV"
VIEW_ID = "vewhq7Nqmi"
ATTACHMENT_FIELD = "样品图片"
IMAGE_DIR = Path(relocate_storage_path(r"D:\tuchuangai\样板图"))
PAGE_SIZE = 200
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".heic",
    ".tif",
    ".tiff",
}


def _cli_script() -> Path:
    appdata = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    script = appdata / "npm" / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
    if not script.exists():
        raise RuntimeError(f"找不到 lark-cli 入口：{script}")
    return script


def _run_cli(args: list[str], *, cwd: Path | None = None) -> dict:
    command = ["node", str(_cli_script()), *args]
    completed = subprocess.run(
        command,
        cwd=str(cwd or Path.cwd()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or stdout or "lark-cli 调用失败")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"lark-cli 返回了无法解析的结果：{stdout[:300]}") from exc
    if payload.get("ok") is False:
        error = payload.get("error") or {}
        raise RuntimeError(str(error.get("message") or error or "飞书接口调用失败"))
    return payload


def _fetch_feishu_rows() -> tuple[list[dict], str]:
    offset = 0
    records: list[dict] = []
    attachment_field_id = ""
    while True:
        payload = _run_cli(
            [
                "base",
                "+record-list",
                "--base-token",
                BASE_TOKEN,
                "--table-id",
                TABLE_ID,
                "--view-id",
                VIEW_ID,
                "--offset",
                str(offset),
                "--limit",
                str(PAGE_SIZE),
            ]
        )
        page = payload.get("data") or {}
        fields = list(page.get("fields") or [])
        field_ids = list(page.get("field_id_list") or [])
        if not attachment_field_id and ATTACHMENT_FIELD in fields:
            attachment_field_id = field_ids[fields.index(ATTACHMENT_FIELD)]
        rows = list(page.get("data") or [])
        record_ids = list(page.get("record_id_list") or [])
        for index, values in enumerate(rows):
            mapped = dict(zip(fields, values))
            mapped["_record_id"] = record_ids[index] if index < len(record_ids) else ""
            records.append(mapped)
        if not page.get("has_more"):
            break
        if not rows:
            raise RuntimeError("飞书返回 has_more=true，但当前页没有记录，已停止以避免死循环")
        offset += len(rows)
    if not attachment_field_id:
        raise RuntimeError(f"没有找到附件字段：{ATTACHMENT_FIELD}")
    return records, attachment_field_id


def _text(value, limit: int | None = None) -> str:
    if value is None:
        result = ""
    elif isinstance(value, list):
        result = "、".join(
            str(item.get("name") if isinstance(item, dict) else item).strip()
            for item in value
            if str(item.get("name") if isinstance(item, dict) else item).strip()
        )
    else:
        result = str(value).strip()
    return result[:limit] if limit else result


def _sample_name(code: str, description: str) -> str:
    first_line = next(
        (line.strip() for line in str(description or "").splitlines() if line.strip()),
        "",
    )
    return (first_line or code)[:100]


def _parse_datetime(value) -> datetime:
    text = _text(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.now()


def _attachment_list(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and _text(item.get("file_token"), 100)
    ]


def _map_record(row: dict, attachment_field_id: str) -> dict:
    code = _text(row.get("样板编码"), 50)
    description = _text(row.get("样品描述"))
    return {
        "record_id": _text(row.get("_record_id"), 50),
        "attachment_field_id": attachment_field_id,
        "source_code": code,
        "code": code,
        "name": _sample_name(code, description),
        "category": "采购",
        "tags": "[]",
        "factory": _text(row.get("工厂"), 120),
        "unit": _text(row.get("毛型数量"), 20),
        "owner": _text(row.get("采购员"), 80),
        "location": _text(row.get("存放位置"), 100),
        "status": "ZhengChang",
        "description": description,
        "created_at": _parse_datetime(row.get("日期")),
        "attachments": _attachment_list(row.get(ATTACHMENT_FIELD)),
    }


def _resolve_missing_and_duplicate_codes(records: list[dict]) -> list[dict]:
    used = {record["source_code"] for record in records if record["source_code"]}
    seen = Counter()
    resolutions: list[dict] = []
    for record in records:
        source_code = record["source_code"]
        if source_code:
            seen[source_code] += 1
            if seen[source_code] == 1:
                continue
            suffix = seen[source_code]
            candidate = f"{source_code}-{suffix}"
            while candidate in used:
                suffix += 1
                candidate = f"{source_code}-{suffix}"
            record["code"] = candidate[:50]
            used.add(record["code"])
            resolutions.append(
                {
                    "record_id": record["record_id"],
                    "reason": "duplicate",
                    "source_code": source_code,
                    "import_code": record["code"],
                }
            )
            continue

        prefix = re.sub(r"[^0-9A-Za-z_-]+", "", record["factory"]) or "FEISHU"
        prefix = f"{prefix}Y{record['created_at']:%Y%m}"
        sequence = 1
        candidate = f"{prefix}{sequence:03d}"
        while candidate in used:
            sequence += 1
            candidate = f"{prefix}{sequence:03d}"
        record["code"] = candidate[:50]
        record["name"] = _sample_name(record["code"], record["description"])
        used.add(record["code"])
        resolutions.append(
            {
                "record_id": record["record_id"],
                "reason": "blank",
                "source_code": "",
                "import_code": record["code"],
            }
        )
    return resolutions


def _safe_image_name(code: str, index: int, attachment: dict) -> str:
    original = _text(attachment.get("name"))
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".jpg"
    safe_code = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", code).strip(" ._")
    safe_code = safe_code[:60] or "sample"
    token = _text(attachment.get("file_token"), 100)
    return f"feishu_{safe_code}_{index:02d}_{token[:12]}{extension}"


def _ensure_browser_image(path: Path) -> tuple[Path, bool]:
    if path.suffix.lower() != ".heic":
        return path, False
    output_path = path.with_suffix(".jpg")
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path, False
    try:
        from PIL import Image
        from pillow_heif import register_heif_opener
    except ImportError as exc:
        raise RuntimeError(
            "发现 HEIC 图片，请先安装 requirements.txt 中的 pillow-heif"
        ) from exc
    register_heif_opener()
    with Image.open(path) as image:
        image.convert("RGB").save(output_path, format="JPEG", quality=92)
    return output_path, True


def _download_images(records: list[dict]) -> tuple[list[Path], int, int]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    newly_downloaded: list[Path] = []
    reused = 0
    generated_browser_images = 0
    total = sum(len(record["attachments"]) for record in records)
    processed = 0
    for record in records:
        local_paths: list[str] = []
        for index, attachment in enumerate(record["attachments"], start=1):
            token = _text(attachment.get("file_token"), 100)
            filename = _safe_image_name(record["code"], index, attachment)
            full_path = IMAGE_DIR / filename
            if full_path.exists() and full_path.stat().st_size > 0:
                reused += 1
                browser_path, generated = _ensure_browser_image(full_path)
                generated_browser_images += int(generated)
                local_paths.append(str(browser_path))
                processed += 1
                continue
            extra = {
                "bitablePerm": {
                    "tableId": TABLE_ID,
                    "attachments": {
                        record["attachment_field_id"]: {
                            record["record_id"]: [token],
                        }
                    },
                }
            }
            params = {
                "extra": json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
            }
            _run_cli(
                [
                    "api",
                    "GET",
                    f"/open-apis/drive/v1/medias/{token}/download",
                    "--as",
                    "user",
                    "--params",
                    json.dumps(params, ensure_ascii=False, separators=(",", ":")),
                    "--output",
                    f"./{filename}",
                ],
                cwd=IMAGE_DIR,
            )
            if not full_path.exists() or full_path.stat().st_size <= 0:
                raise RuntimeError(f"图片下载后不存在或为空：{filename}")
            newly_downloaded.append(full_path)
            browser_path, generated = _ensure_browser_image(full_path)
            generated_browser_images += int(generated)
            local_paths.append(str(browser_path))
            processed += 1
            if processed % 25 == 0 or processed == total:
                print(f"附件进度：{processed}/{total}", flush=True)
        record["image_paths"] = ";".join(local_paths)
    return newly_downloaded, reused, generated_browser_images


def _existing_samples(connection) -> dict[str, dict]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT Id, YangBanBianHao, DangQianKuCun, ISNULL([tupian], N'')
        FROM dbo.YangBan
        """
    )
    return {
        str(row[1] or "").strip(): {
            "id": int(row[0]),
            "stock": row[2],
            "images": str(row[3] or "").strip(),
        }
        for row in cursor.fetchall()
        if str(row[1] or "").strip()
    }


def _preview(
    records: list[dict],
    existing: dict[str, dict],
    code_resolutions: list[dict],
) -> dict:
    codes = [record["code"] for record in records if record["code"]]
    source_codes = [
        record["source_code"] for record in records if record["source_code"]
    ]
    duplicates = sorted(
        code for code, count in Counter(source_codes).items() if count > 1
    )
    attachments = [
        attachment for record in records for attachment in record["attachments"]
    ]
    extensions = Counter(
        Path(_text(attachment.get("name"))).suffix.lower() or "(无扩展名)"
        for attachment in attachments
    )
    blank_codes = sum(1 for record in records if not record["source_code"])
    unique_codes = set(codes)
    return {
        "feishu_rows": len(records),
        "valid_rows": len(codes),
        "blank_code_rows": blank_codes,
        "source_duplicate_codes": duplicates,
        "code_resolutions": code_resolutions,
        "insert_count": len(unique_codes - set(existing)),
        "update_count": len(unique_codes & set(existing)),
        "attachment_count": len(attachments),
        "attachment_total_bytes": sum(
            int(attachment.get("size") or 0) for attachment in attachments
        ),
        "attachment_extensions": dict(sorted(extensions.items())),
    }


def _apply_database(records: list[dict], connection) -> dict:
    existing = _existing_samples(connection)
    cursor = connection.cursor()
    cursor.execute(
        "ALTER TABLE dbo.YangBan ALTER COLUMN BeiZhu NVARCHAR(MAX) NULL"
    )
    inserted = 0
    updated = 0
    inserted_flows = 0

    for record in records:
        code = record["code"]
        if not code:
            continue
        current = existing.get(code)
        image_paths = record.get("image_paths") or ""
        if current:
            if not image_paths:
                image_paths = current["images"]
            cursor.execute(
                """
                UPDATE dbo.YangBan
                   SET YangBanMingCheng = %s,
                       FenLei = %s,
                       BiaoQian = %s,
                       GongChang = %s,
                       DanWei = %s,
                       [tupian] = %s,
                       FuZeRen = %s,
                       KuWei = %s,
                       ZhuangTai = %s,
                       BeiZhu = %s,
                       GengXinShiJian = SYSDATETIME()
                 WHERE Id = %s
                """,
                (
                    record["name"],
                    record["category"],
                    record["tags"],
                    record["factory"],
                    record["unit"],
                    image_paths,
                    record["owner"],
                    record["location"],
                    record["status"],
                    record["description"],
                    current["id"],
                ),
            )
            updated += 1
            continue

        cursor.execute(
            """
            INSERT INTO dbo.YangBan
                (YangBanBianHao, YangBanMingCheng, FenLei, BiaoQian,
                 GongChang, DanWei, [tupian], DangQianKuCun, FuZeRen,
                 KuWei, ZhuangTai, BeiZhu, ChuangJianShiJian, GengXinShiJian)
            OUTPUT INSERTED.Id
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, SYSDATETIME())
            """,
            (
                code,
                record["name"],
                record["category"],
                record["tags"],
                record["factory"],
                record["unit"],
                image_paths,
                record["owner"],
                record["location"],
                record["status"],
                record["description"],
                record["created_at"],
            ),
        )
        sample_id = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO dbo.YangBan_LiuShui
                (YangBanId, BianDongLeiXing, BianDongShuLiang,
                 CaoZuoRen, GuanLianDanHao, BeiZhu, ChuangJianShiJian)
            VALUES (%s, N'RuKu', 1, N'飞书导入', %s, N'飞书多维表格初始库存导入', %s)
            """,
            (sample_id, record["record_id"], record["created_at"]),
        )
        existing[code] = {"id": sample_id, "stock": 1, "images": image_paths}
        inserted += 1
        inserted_flows += 1

    connection.commit()
    return {
        "inserted": inserted,
        "updated": updated,
        "inbound_flows_inserted": inserted_flows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="下载附件并提交数据库；不传时只做只读预览",
    )
    args = parser.parse_args()

    raw_rows, attachment_field_id = _fetch_feishu_rows()
    records = [_map_record(row, attachment_field_id) for row in raw_rows]
    code_resolutions = _resolve_missing_and_duplicate_codes(records)
    connection = pytds.connect(**sql_server_config())
    newly_downloaded: list[Path] = []
    try:
        existing = _existing_samples(connection)
        preview = _preview(records, existing, code_resolutions)
        print(json.dumps({"preview": preview}, ensure_ascii=False, indent=2))
        if not args.apply:
            connection.rollback()
            return 0

        newly_downloaded, reused, generated_browser_images = _download_images(records)
        result = _apply_database(records, connection)
        result.update(
            {
                "downloaded_images": len(newly_downloaded),
                "reused_images": reused,
                "generated_browser_images": generated_browser_images,
                "image_directory": str(IMAGE_DIR),
            }
        )
        print(json.dumps({"result": result}, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"导入失败：{error}", file=sys.stderr)
        raise SystemExit(1)
