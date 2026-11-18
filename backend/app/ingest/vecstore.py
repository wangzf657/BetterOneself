"""sqlite-vec 向量存取:与业务表分离的 vec_chunks 虚拟表(数据模型 3.1)。

写入必须复用业务会话的同一连接:SQLite 单写者,另开连接写向量会 database is locked。
"""

from sqlalchemy import Connection, bindparam, text
from sqlalchemy.engine import Engine


def index_chunks(conn: Connection, items: list[tuple[int, bytes]]) -> None:
    """chunk_id 与已序列化向量成对写入;重解析前调用方先清旧向量。"""
    for cid, vec in items:
        conn.execute(
            text("INSERT INTO vec_chunks(chunk_id, embedding) VALUES (:cid, :vec)"),
            {"cid": cid, "vec": vec},
        )


def clear_source(conn: Connection, source_id: int) -> None:
    conn.execute(
        text(
            "DELETE FROM vec_chunks WHERE chunk_id IN "
            "(SELECT id FROM source_chunks WHERE source_id = :sid)"
        ),
        {"sid": source_id},
    )


_SEARCH_SQL = text(
    """
    SELECT vc.chunk_id, vc.distance
    FROM (
        SELECT chunk_id, distance FROM vec_chunks
        WHERE embedding MATCH :vec AND k = :fetch
        ORDER BY distance
    ) vc
    JOIN source_chunks sc ON sc.id = vc.chunk_id
    WHERE sc.source_id IN :sids
    LIMIT :k
    """
).bindparams(bindparam("sids", expanding=True))


def search(
    engine: Engine,
    query_vec: bytes,
    source_ids: list[int],
    k: int = 6,
) -> list[tuple[int, float]]:
    """余弦距离 top-k,限定资料范围。

    shortcut: vec0 KNN 不支持下推 source 过滤,取 4 倍候选再 JOIN 过滤;
    资料量上万出现召回不足再升级元数据列
    """
    fetch = max(k * 4, 24)
    with engine.connect() as conn:
        rows = conn.execute(
            _SEARCH_SQL, {"vec": query_vec, "fetch": fetch, "sids": source_ids, "k": k}
        ).fetchall()
    return [(row[0], float(row[1])) for row in rows]
