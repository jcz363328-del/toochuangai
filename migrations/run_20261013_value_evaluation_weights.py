from pathlib import Path
import sys

import pytds

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secret_settings import sql_server_config


sql_path = Path(__file__).with_name("20261013_add_value_evaluation_weights.sql")
connection = pytds.connect(**sql_server_config())
try:
    cursor = connection.cursor()
    cursor.execute(sql_path.read_text(encoding="utf-8"))
    connection.commit()
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='JiaZhiGuan_QuanZhong'"
    )
    print(f"JiaZhiGuan_QuanZhong exists={bool(cursor.fetchone()[0])}")
except Exception:
    connection.rollback()
    raise
finally:
    connection.close()
