"""ZD 报价助手 - SQLite 数据库层。

- 单连接批量 upsert：用 INSERT ... ON CONFLICT(brand,model) DO UPDATE +
  COALESCE(excluded.col, devices.col) 一次性写入，避免逐行开连/查询。
- COALESCE 实现「新值非空才覆盖、否则保留旧值」的合并语义。
"""
import sqlite3
import os
import zd_config as C

# 业务列（不含自增 id，brand/model 为唯一冲突键）
COLS = ["seq", "name", "brand", "model", "spec", "country", "qty",
         "unit", "remark", "code", "bid_param", "h_price", "q_price",
         "d_price", "p_price", "y_price", "budget_price",
         "sale_guide_price", "lease_price", "market_price"]


def _conn():
    os.makedirs(C.DATA_DIR, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH)
    # 写入/读取加速：WAL 提升并发读、NORMAL 同步降低落盘开销
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        pass
    return con


def init_db():
    con = _conn()
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        seq         TEXT,
        name        TEXT,
        brand       TEXT NOT NULL,
        model       TEXT NOT NULL,
        spec        TEXT,
        country     TEXT,
        qty         TEXT,
        unit        TEXT,
        remark      TEXT,
        code        TEXT,
        bid_param   TEXT,
        h_price     REAL,
        q_price     REAL,
        d_price     REAL,
        y_price     REAL,
        market_price REAL,
        tier1_price REAL,
        UNIQUE(brand, model)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    # 兼容旧库：补齐新增价格列、丢弃废弃的 tier1_price（不删数据）
    cur.execute("PRAGMA table_info(devices)")
    existing = {r[1] for r in cur.fetchall()}
    for c in COLS:
        if c not in existing:
            try:
                cur.execute(f"ALTER TABLE devices ADD COLUMN {c} REAL")
            except sqlite3.OperationalError:
                pass
    if "tier1_price" in existing:
        try:
            cur.execute("ALTER TABLE devices DROP COLUMN tier1_price")
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()


def _sanitize(v):
    """空字符串与 None 一律视为「未提供」，便于 COALESCE 保留旧值。"""
    return None if v in (None, "") else v


def bulk_upsert(rows: list) -> int:
    """批量合并写入。rows 为含 brand/model（必填）及任意其他字段的 dict 列表。

    返回成功写入（插入+更新）的行数。
    """
    if not rows:
        return 0
    con = _conn()
    cur = con.cursor()
    placeholders = ",".join(["?"] * len(COLS))
    # 更新子句：除冲突键外，新值非空才覆盖旧值
    update_cols = [c for c in COLS if c not in ("brand", "model")]
    update_clause = ",".join(
        f"{c}=COALESCE(excluded.{c}, devices.{c})" for c in update_cols
    )
    sql = (
        f"INSERT INTO devices ({','.join(COLS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(brand, model) DO UPDATE SET {update_clause}"
    )
    params = []
    for r in rows:
        brand = (r.get("brand") or "").strip()
        model = (r.get("model") or "").strip()
        if not brand or not model:
            continue
        params.append(tuple(_sanitize(r.get(c)) for c in COLS))
    if not params:
        con.close()
        return 0
    cur.executemany(sql, params)
    con.commit()
    n = cur.rowcount
    con.close()
    return n if n and n > 0 else len(params)


def count() -> int:
    con = _conn()
    n = con.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    con.close()
    return n


def get_price(brand: str, model: str, system_label: str):
    """返回某设备在指定价格体系下的价格（float），未找到返回 None。"""
    col = C.PRICE_SYSTEMS.get(system_label)
    if not col:
        return None
    con = _conn()
    row = con.execute(
        f"SELECT {col} FROM devices WHERE brand=? AND model=?",
        ((brand or "").strip(), (model or "").strip()),
    ).fetchone()
    con.close()
    if row is None:
        return None
    val = row[0]
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_record(brand: str, model: str):
    """返回某设备的整条数据库记录（dict），未找到返回 None。

    记录含配单表导入的标底参数 / 规格 / 国别 / 备注 / 序号 / 设备名称
    及全部价格字段，供生成报价单时回填空缺字段。
    """
    con = _conn()
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM devices WHERE brand=? AND model=?",
        ((brand or "").strip(), (model or "").strip()),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def set_meta(key: str, value: str):
    con = _conn()
    con.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    con.commit()
    con.close()


def get_meta(key: str):
    con = _conn()
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    con.close()
    return row[0] if row else None


def all_rows():
    con = _conn()
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM devices ORDER BY brand, model"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def clear_db():
    con = _conn()
    con.execute("DELETE FROM devices")
    con.execute("DELETE FROM meta")
    con.commit()
    con.close()


if __name__ == "__main__":
    init_db()
    print("DB initialized at", C.DB_PATH)
