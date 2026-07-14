"""
为 v_quanyuanchuangxin 构建提案向量，并写入 chuangxin_xiangliang。

字段拼接标准（固定）：
标题 + 内容 + 解决方案

默认模型（中英文均可）：
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pytds

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from secret_settings import sql_server_config


DB_CONF = sql_server_config()

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def get_conn():
    return pytds.connect(
        server=DB_CONF["server"],
        user=DB_CONF["user"],
        password=DB_CONF["password"],
        database=DB_CONF["database"],
        autocommit=False,
    )


def ensure_table(conn):
    sql = """
    IF OBJECT_ID('dbo.chuangxin_xiangliang', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.chuangxin_xiangliang (
            id BIGINT IDENTITY(1,1) PRIMARY KEY,
            bianhao NVARCHAR(100) NOT NULL,
            biaoti NVARCHAR(MAX) NULL,
            neirong NVARCHAR(MAX) NULL,
            jiejuefangan NVARCHAR(MAX) NULL,
            pinjie_wenben NVARCHAR(MAX) NOT NULL,
            wenben_md5 CHAR(32) NOT NULL,
            xiangliang_moxing NVARCHAR(200) NOT NULL,
            xiangliang_weidu INT NOT NULL,
            xiangliang_json NVARCHAR(MAX) NOT NULL,
            gengxin_shijian DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE UNIQUE INDEX uq_chuangxin_xiangliang_bianhao ON dbo.chuangxin_xiangliang(bianhao);
    END
    """
    cur = conn.cursor()
    cur.execute(sql)
    # 兼容已存在老表：补充相似度字段
    cur.execute(
        """
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi1_bianhao') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi1_bianhao NVARCHAR(100) NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi1_fenshu') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi1_fenshu FLOAT NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi2_bianhao') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi2_bianhao NVARCHAR(100) NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi2_fenshu') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi2_fenshu FLOAT NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi3_bianhao') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi3_bianhao NVARCHAR(100) NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi3_fenshu') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi3_fenshu FLOAT NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi_top3_json') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi_top3_json NVARCHAR(MAX) NULL;
        IF COL_LENGTH('dbo.chuangxin_xiangliang','xiangsi_gengxin_shijian') IS NULL
            ALTER TABLE dbo.chuangxin_xiangliang ADD xiangsi_gengxin_shijian DATETIME2 NULL;
        """
    )
    conn.commit()


def fetch_source_rows(conn, bianhao: str | None = None) -> List[Tuple]:
    if bianhao:
        sql = """
        SELECT
            CAST(编号 AS NVARCHAR(100)) AS bianhao,
            ISNULL(CAST(标题 AS NVARCHAR(MAX)), '') AS biaoti,
            ISNULL(CAST(内容 AS NVARCHAR(MAX)), '') AS neirong,
            ISNULL(CAST(解决方案 AS NVARCHAR(MAX)), '') AS jiejuefangan
        FROM v_quanyuanchuangxin
        WHERE 编号 IS NOT NULL
          AND CAST(编号 AS NVARCHAR(100)) = %(bianhao)s
        """
        cur = conn.cursor()
        cur.execute(sql, {"bianhao": str(bianhao)})
        return cur.fetchall() or []

    sql = """
    SELECT
        CAST(编号 AS NVARCHAR(100)) AS bianhao,
        ISNULL(CAST(标题 AS NVARCHAR(MAX)), '') AS biaoti,
        ISNULL(CAST(内容 AS NVARCHAR(MAX)), '') AS neirong,
        ISNULL(CAST(解决方案 AS NVARCHAR(MAX)), '') AS jiejuefangan
    FROM v_quanyuanchuangxin
    WHERE 编号 IS NOT NULL
    ORDER BY 编号
    """
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall() or []


def fetch_existing_md5(conn) -> Dict[str, str]:
    sql = "SELECT bianhao, wenben_md5 FROM dbo.chuangxin_xiangliang"
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall() or []
    return {str(r[0]): str(r[1]) for r in rows}


def build_text(biaoti: str, neirong: str, jiejuefangan: str) -> str:
    # 固定模板，保证所有嵌入标准一致
    return f"标题：{biaoti.strip()}\n内容：{neirong.strip()}\n解决方案：{jiejuefangan.strip()}"


def md5_text(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def to_json_vector(vec) -> str:
    # 压缩体积，保留 6 位小数（统一标准）
    arr = [round(float(x), 6) for x in vec]
    return json.dumps(arr, ensure_ascii=False, separators=(",", ":"))


def upsert_vector_rows(conn, rows: List[Dict]):
    if not rows:
        return
    merge_sql = """
    MERGE dbo.chuangxin_xiangliang AS t
    USING (SELECT
              %(bianhao)s AS bianhao,
              %(biaoti)s AS biaoti,
              %(neirong)s AS neirong,
              %(jiejuefangan)s AS jiejuefangan,
              %(pinjie_wenben)s AS pinjie_wenben,
              %(wenben_md5)s AS wenben_md5,
              %(xiangliang_moxing)s AS xiangliang_moxing,
              %(xiangliang_weidu)s AS xiangliang_weidu,
              %(xiangliang_json)s AS xiangliang_json
           ) AS s
    ON t.bianhao = s.bianhao
    WHEN MATCHED THEN
      UPDATE SET
          biaoti = s.biaoti,
          neirong = s.neirong,
          jiejuefangan = s.jiejuefangan,
          pinjie_wenben = s.pinjie_wenben,
          wenben_md5 = s.wenben_md5,
          xiangliang_moxing = s.xiangliang_moxing,
          xiangliang_weidu = s.xiangliang_weidu,
          xiangliang_json = s.xiangliang_json,
          gengxin_shijian = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
      INSERT (bianhao, biaoti, neirong, jiejuefangan, pinjie_wenben, wenben_md5, xiangliang_moxing, xiangliang_weidu, xiangliang_json)
      VALUES (s.bianhao, s.biaoti, s.neirong, s.jiejuefangan, s.pinjie_wenben, s.wenben_md5, s.xiangliang_moxing, s.xiangliang_weidu, s.xiangliang_json);
    """
    cur = conn.cursor()
    for row in rows:
        cur.execute(merge_sql, row)
    conn.commit()


def fetch_vectors_for_similarity(conn, model_name: str) -> List[Tuple[str, List[float]]]:
    sql = """
    SELECT bianhao, xiangliang_json
    FROM dbo.chuangxin_xiangliang
    WHERE xiangliang_json IS NOT NULL
      AND xiangliang_json != ''
      AND xiangliang_moxing = %(model)s
    ORDER BY bianhao
    """
    cur = conn.cursor()
    cur.execute(sql, {"model": model_name})
    rows = cur.fetchall() or []
    parsed: List[Tuple[str, List[float]]] = []
    for bianhao, vec_json in rows:
        try:
            arr = json.loads(str(vec_json))
            if isinstance(arr, list) and len(arr) > 0:
                parsed.append((str(bianhao), [float(x) for x in arr]))
        except Exception:
            continue
    return parsed


def compute_top3_similarity(rows: List[Tuple[str, List[float]]]) -> Dict[str, List[Tuple[str, float]]]:
    if len(rows) <= 1:
        return {r[0]: [] for r in rows}
    bianhaos = [r[0] for r in rows]
    mat = np.array([r[1] for r in rows], dtype=np.float32)  # 已归一化向量
    sim = mat @ mat.T  # 余弦相似度
    n = sim.shape[0]
    top_map: Dict[str, List[Tuple[str, float]]] = {}
    for i in range(n):
        sim[i, i] = -1e9
        k = 3 if n > 3 else n - 1
        idx = np.argpartition(sim[i], -k)[-k:] if k > 0 else np.array([], dtype=np.int32)
        idx = idx[np.argsort(sim[i][idx])[::-1]] if k > 0 else idx
        top_map[bianhaos[i]] = [(bianhaos[j], float(sim[i, j])) for j in idx]
    return top_map


def update_top3_similarity(conn, top_map: Dict[str, List[Tuple[str, float]]]):
    if not top_map:
        return
    sql = """
    UPDATE dbo.chuangxin_xiangliang
       SET xiangsi1_bianhao = %(s1_id)s,
           xiangsi1_fenshu = %(s1_sc)s,
           xiangsi2_bianhao = %(s2_id)s,
           xiangsi2_fenshu = %(s2_sc)s,
           xiangsi3_bianhao = %(s3_id)s,
           xiangsi3_fenshu = %(s3_sc)s,
           xiangsi_top3_json = %(top3_json)s,
           xiangsi_gengxin_shijian = SYSUTCDATETIME()
     WHERE bianhao = %(bianhao)s
    """
    cur = conn.cursor()
    for bianhao, top3 in top_map.items():
        payload = {
            "bianhao": bianhao,
            "s1_id": top3[0][0] if len(top3) > 0 else None,
            "s1_sc": round(top3[0][1], 6) if len(top3) > 0 else None,
            "s2_id": top3[1][0] if len(top3) > 1 else None,
            "s2_sc": round(top3[1][1], 6) if len(top3) > 1 else None,
            "s3_id": top3[2][0] if len(top3) > 2 else None,
            "s3_sc": round(top3[2][1], 6) if len(top3) > 2 else None,
            "top3_json": json.dumps(
                [{"bianhao": x[0], "xiangsi_fenshu": round(x[1], 6)} for x in top3],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        cur.execute(sql, payload)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="构建创新提案向量表")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="嵌入模型名称（需支持中英文）")
    parser.add_argument("--batch-size", type=int, default=32, help="编码批次大小")
    parser.add_argument("--force", action="store_true", help="强制全量重算（忽略md5增量）")
    parser.add_argument("--bianhao", default="", help="只更新指定编号（可选）")
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise SystemExit(
            "缺少 sentence-transformers 依赖，请先安装：\n"
            "pip install sentence-transformers\n"
            f"原始错误：{e}"
        )

    started = datetime.now()
    conn = get_conn()
    try:
        ensure_table(conn)
        one_bianhao = str(args.bianhao or "").strip()
        src_rows = fetch_source_rows(conn, one_bianhao or None)
        old_md5 = fetch_existing_md5(conn)

        to_encode = []
        for bianhao, biaoti, neirong, jiejuefangan in src_rows:
            bianhao = str(bianhao or "").strip()
            if not bianhao:
                continue
            text = build_text(str(biaoti or ""), str(neirong or ""), str(jiejuefangan or ""))
            text_md5 = md5_text(text)
            if (not args.force) and old_md5.get(bianhao) == text_md5:
                continue
            to_encode.append(
                {
                    "bianhao": bianhao,
                    "biaoti": str(biaoti or ""),
                    "neirong": str(neirong or ""),
                    "jiejuefangan": str(jiejuefangan or ""),
                    "pinjie_wenben": text,
                    "wenben_md5": text_md5,
                }
            )

        print(f"[INFO] 源记录数: {len(src_rows)}，待嵌入数: {len(to_encode)}")

        written = 0
        dim = 0
        if to_encode:
            model = SentenceTransformer(args.model)
            texts = [r["pinjie_wenben"] for r in to_encode]
            vectors = model.encode(
                texts,
                batch_size=args.batch_size,
                show_progress_bar=True,
                normalize_embeddings=True,  # 统一标准
            )

            dim = len(vectors[0]) if len(vectors) else 0
            payload_rows = []
            for row, vec in zip(to_encode, vectors):
                payload_rows.append(
                    {
                        **row,
                        "xiangliang_moxing": args.model,
                        "xiangliang_weidu": dim,
                        "xiangliang_json": to_json_vector(vec),
                    }
                )

            upsert_vector_rows(conn, payload_rows)
            written = len(payload_rows)
            print(f"[OK] 完成向量写入: {written} 条，维度: {dim}")
        else:
            print("[INFO] 向量无需更新，继续计算Top3相似度。")

        sim_rows = fetch_vectors_for_similarity(conn, args.model)
        top_map = compute_top3_similarity(sim_rows)
        update_top3_similarity(conn, top_map)
        print(
            f"[OK] 已写入Top3相似度: {len(top_map)} 条，"
            f"总耗时: {datetime.now() - started}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
