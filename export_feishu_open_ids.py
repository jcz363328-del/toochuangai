# -*- coding: utf-8 -*-
import json
from datetime import date

import pytds
import export_feishu_open_ids_tc as tc
from innovation.message_service import MessageService
from secret_settings import get_feishu_message_config


_FEISHU_MESSAGE_CONFIG = get_feishu_message_config()
APP_ID = _FEISHU_MESSAGE_CONFIG["app_id"]
APP_SECRET = _FEISHU_MESSAGE_CONFIG["app_secret"] or MessageService().app_secret
TABLE = "feishu_id"


def switch_app():
    tc.FEISHU_CONFIG["app_id"] = APP_ID
    tc.FEISHU_CONFIG["app_secret"] = APP_SECRET
    pm = tc.permission_manager
    pm.app_id = APP_ID
    pm.app_secret = APP_SECRET
    pm.access_token = None
    pm.token_expires_at = None


def ensure_table(cur):
    cur.execute(f"""
    IF OBJECT_ID(N'dbo.{TABLE}', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.{TABLE} (
            feishu_id NVARCHAR(100) NOT NULL,
            yonghu NVARCHAR(100) NOT NULL,
            quanxian NVARCHAR(200) NULL,
            riqi DATE NOT NULL
        );
    END;
    IF COL_LENGTH(N'dbo.{TABLE}', N'feishu_id') IS NULL
        ALTER TABLE dbo.{TABLE} ADD feishu_id NVARCHAR(100) NULL;
    IF COL_LENGTH(N'dbo.{TABLE}', N'yonghu') IS NULL
        ALTER TABLE dbo.{TABLE} ADD yonghu NVARCHAR(100) NULL;
    IF COL_LENGTH(N'dbo.{TABLE}', N'quanxian') IS NULL
        ALTER TABLE dbo.{TABLE} ADD quanxian NVARCHAR(200) NULL;
    IF COL_LENGTH(N'dbo.{TABLE}', N'riqi') IS NULL
        ALTER TABLE dbo.{TABLE} ADD riqi DATE NULL;
    """)


def replace_rows(rows):
    today = date.today().isoformat()
    conn = pytds.connect(server=tc.DB_SERVER, database=tc.DB_DATABASE, user=tc.DB_USER, password=tc.DB_PASSWORD)
    try:
        cur = conn.cursor()
        ensure_table(cur)
        cur.execute(f"DELETE FROM dbo.{TABLE}")

        for row in rows:
            cur.execute(
                f"INSERT INTO dbo.{TABLE} (feishu_id, yonghu, quanxian, riqi) VALUES (%s, %s, %s, %s)",
                (
                    str(row.get("feishu_id") or "").strip(),
                    str(row.get("yonghu") or "").strip(),
                    "",
                    today,
                ),
            )

        if not conn.autocommit:
            conn.commit()
    finally:
        conn.close()


def main():
    switch_app()
    payload = tc.export_all_users()
    replace_rows(payload["rows"])
    print(json.dumps({
        "success": True,
        "app_id": APP_ID,
        "table": TABLE,
        "row_count": payload["row_count"],
        "quanxian": "empty",
        "import_date": date.today().isoformat(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
