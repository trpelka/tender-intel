import sqlite3, os, json

DB_PATH = os.getenv("DATABASE_URL", "tender_intel.db")


def scalar(value):
    """Convert API values to SQLite-compatible scalar values."""
    if isinstance(value, list):
        if not value:
            return ""
        value = next((x for x in value if x not in (None, "")), "")
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def numeric(value):
    """Convert numeric API values safely."""
    value = scalar(value)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            profile TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id TEXT,
            source TEXT,
            title TEXT,
            description TEXT,
            cpv_codes TEXT,
            buyer_name TEXT,
            buyer_country TEXT,
            publication_date TEXT,
            deadline TEXT,
            estimated_value REAL,
            currency TEXT,
            url TEXT,
            notice_type TEXT,
            content_hash TEXT UNIQUE,
            collected_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER REFERENCES notices(id),
            client_id INTEGER REFERENCES clients(id),
            relevance_score INTEGER,
            summary_en TEXT,
            summary_pl TEXT,
            impact TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            period_from TEXT,
            period_to TEXT,
            html TEXT,
            sent_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_hash
            ON notices(content_hash);

        CREATE INDEX IF NOT EXISTS idx_notice_id
            ON notices(notice_id);

        CREATE INDEX IF NOT EXISTS idx_intel_client
            ON intelligence(client_id);
    """)
    conn.commit()
    conn.close()
    print(f"DB ready: {DB_PATH}")


def notice_exists(h):
    if not h:
        return False
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM notices WHERE content_hash=?",
        (h,)
    ).fetchone()
    conn.close()
    return row is not None


def insert_notice(n):
    conn = get_conn()

    content_hash = scalar(n.get("content_hash", ""))

    # Idempotent storage: an already-seen notice is not an error.
    if content_hash:
        existing = conn.execute(
            "SELECT id FROM notices WHERE content_hash=?",
            (content_hash,)
        ).fetchone()

        if existing:
            conn.close()
            return existing["id"]

    cur = conn.execute("""
        INSERT INTO notices (
            notice_id, source, title, description, cpv_codes,
            buyer_name, buyer_country, publication_date, deadline,
            estimated_value, currency, url, notice_type, content_hash
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        scalar(n.get("notice_id", "")),
        scalar(n.get("source", "")),
        scalar(n.get("title", "")),
        scalar(n.get("description", "")),
        json.dumps(n.get("cpv_codes", []), ensure_ascii=False),
        scalar(n.get("buyer_name", "")),
        scalar(n.get("buyer_country", "")),
        scalar(n.get("publication_date", "")),
        scalar(n.get("deadline", "")),
        scalar(n.get("estimated_value")),
        scalar(n.get("currency", "")),
        scalar(n.get("url", "")),
        scalar(n.get("notice_type", "")),
        content_hash
    ))

    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id

def intelligence_exists(notice_id, client_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM intelligence WHERE notice_id=? AND client_id=?",
        (int(notice_id), int(client_id))
    ).fetchone()
    conn.close()
    return row is not None


def insert_intelligence(i):
    conn = get_conn()

    cur = conn.execute("""
        INSERT INTO intelligence (
            notice_id, client_id, relevance_score,
            summary_en, summary_pl, impact
        )
        VALUES (?,?,?,?,?,?)
    """, (
        int(i["notice_id"]),
        int(i["client_id"]),
        int(i["relevance_score"]),
        scalar(i.get("summary_en", "")),
        scalar(i.get("summary_pl", "")),
        scalar(i.get("impact", "MEDIUM"))
    ))

    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_client_intelligence(client_id, days_back=7):
    conn = get_conn()

    rows = conn.execute("""
        SELECT
            i.*,
            n.title,
            n.buyer_name,
            n.buyer_country,
            n.deadline,
            n.estimated_value,
            n.currency,
            n.url,
            n.cpv_codes
        FROM intelligence i
        JOIN notices n ON n.id=i.notice_id
        WHERE i.client_id=?
          AND i.created_at >= datetime('now', ? || ' days')
        ORDER BY i.relevance_score DESC
    """, (client_id, f"-{days_back}")).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def get_all_clients():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM clients WHERE active=1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_client(name, email, profile):
    conn = get_conn()

    cur = conn.execute(
        "INSERT INTO clients (name,email,profile) VALUES (?,?,?)",
        (scalar(name), scalar(email), json.dumps(profile, ensure_ascii=False))
    )

    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id
