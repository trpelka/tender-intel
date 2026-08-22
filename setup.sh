#!/bin/bash
# Tender Intelligence — bootstrap
# Run in Codespaces terminal: bash setup.sh
# Creates full project structure and installs dependencies

set -e
echo "=== Tender Intelligence Setup ==="

# Structure
mkdir -p collectors processing database reports profiles scripts output logs
touch collectors/__init__.py processing/__init__.py database/__init__.py reports/__init__.py

# ── requirements.txt ──────────────────────────────────────────
cat > requirements.txt << 'PYEOF'
httpx>=0.27.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
lxml>=5.0.0
PYEOF

# ── .env.example ──────────────────────────────────────────────
cat > .env.example << 'PYEOF'
GEMINI_API_KEY=your_gemini_api_key_here
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your@gmail.com
SMTP_PASS=your_app_password_here
DATABASE_URL=tender_intel.db
PYEOF

# ── collectors/ted.py ─────────────────────────────────────────
cat > collectors/ted.py << 'PYEOF'
"""
TED Europa API v3 — free, no auth for published notices.
Docs: https://api.ted.europa.eu/swagger-ui/index.html
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)
TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

FIELDS = [
    "notice-id", "publication-date", "title", "description",
    "cpv-code", "buyer-name", "buyer-country",
    "deadline-receipt-request", "total-value", "currency",
    "notice-type", "document-url",
]

def build_query(cpv_codes, countries, days_back=7, min_value=None):
    date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y%m%d")
    cpv_filters = " OR ".join(f"cpv-code ~ {code}" for code in cpv_codes)
    country_filter = " OR ".join(f"buyer-country == {c}" for c in countries)
    q = f"({cpv_filters}) AND ({country_filter}) AND publication-date >= {date_from}"
    if min_value:
        q += f" AND total-value >= {min_value}"
    return q

def fetch_notices(cpv_codes, countries, days_back=7, min_value=None):
    query = build_query(cpv_codes, countries, days_back, min_value)
    notices = []
    page = 1
    with httpx.Client(timeout=30) as client:
        while True:
            params = {
                "query": query,
                "fields": ",".join(FIELDS),
                "page": page,
                "limit": 100,
                "sort": "publication-date DESC",
            }
            try:
                resp = client.get(TED_SEARCH_URL, params=params,
                                  headers={"Accept": "application/json"})
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.error(f"TED API error p{page}: {e}")
                break
            results = data.get("notices", [])
            if not results:
                break
            notices.extend(results)
            print(f"  TED page {page}: {len(results)} notices")
            if page * 100 >= data.get("total", 0):
                break
            page += 1
    return notices

def _first(d):
    if not d:
        return ""
    for lang in ("en", "pl", "de", "fr"):
        if isinstance(d, dict) and d.get(lang):
            return d[lang]
    return next(iter(d.values()), "") if isinstance(d, dict) else str(d)

def normalize(raw):
    return {
        "source": "TED",
        "notice_id": raw.get("notice-id", ""),
        "title": _first(raw.get("title", {})),
        "description": _first(raw.get("description", {})),
        "cpv_codes": raw.get("cpv-code", []),
        "buyer_name": _first(raw.get("buyer-name", {})),
        "buyer_country": raw.get("buyer-country", ""),
        "publication_date": raw.get("publication-date", ""),
        "deadline": raw.get("deadline-receipt-request", ""),
        "estimated_value": raw.get("total-value"),
        "currency": raw.get("currency", "EUR"),
        "url": raw.get("document-url", ""),
        "notice_type": raw.get("notice-type", ""),
        "raw": raw,
    }

def collect(profile):
    raw = fetch_notices(
        cpv_codes=profile.get("cpv_codes", ["72"]),
        countries=profile.get("countries", ["PL"]),
        days_back=profile.get("days_back", 7),
        min_value=profile.get("min_value"),
    )
    return [normalize(r) for r in raw]
PYEOF

# ── collectors/bzp.py ─────────────────────────────────────────
cat > collectors/bzp.py << 'PYEOF'
"""
BZP RSS — below-threshold Polish tenders.
"""
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)
BZP_RSS_URL = "https://bzp.uzp.gov.pl/ZP400PodgladOpublikowanego.aspx?id=rss"

def fetch_rss():
    with httpx.Client(timeout=30) as client:
        try:
            resp = client.get(BZP_RSS_URL,
                              headers={"User-Agent": "TenderIntel/1.0"},
                              follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"BZP RSS error: {e}")
            return []
    return parse_rss(resp.text)

def parse_rss(xml_text):
    notices = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error(f"BZP XML error: {e}")
        return []
    channel = root.find("channel")
    if channel is None:
        return []
    for item in channel.findall("item"):
        title = item.findtext("title", "")
        link  = item.findtext("link", "")
        desc  = item.findtext("description", "")
        pub   = item.findtext("pubDate", "")
        if not title:
            continue
        notices.append({
            "source": "BZP",
            "notice_id": "BZP-" + hashlib.md5((link or title).encode()).hexdigest()[:12],
            "title": title.strip(),
            "description": desc.strip(),
            "cpv_codes": [],
            "buyer_name": "",
            "buyer_country": "PL",
            "publication_date": _parse_date(pub),
            "deadline": "",
            "estimated_value": None,
            "currency": "PLN",
            "url": link.strip(),
            "notice_type": "contract-notice",
            "raw": {},
        })
    print(f"  BZP: {len(notices)} notices")
    return notices

def _parse_date(s):
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10] if s else ""

def collect(profile):
    notices = fetch_rss()
    kw = profile.get("keywords", [])
    if not kw:
        return notices
    out = [n for n in notices
           if any(k.lower() in f"{n['title']} {n['description']}".lower() for k in kw)]
    print(f"  BZP after keyword filter: {len(out)}")
    return out
PYEOF

# ── database/db.py ────────────────────────────────────────────
cat > database/db.py << 'PYEOF'
import sqlite3, os, json
from pathlib import Path

DB_PATH = os.getenv("DATABASE_URL", "tender_intel.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT NOT NULL,
            profile TEXT NOT NULL, active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id TEXT, source TEXT, title TEXT, description TEXT,
            cpv_codes TEXT, buyer_name TEXT, buyer_country TEXT,
            publication_date TEXT, deadline TEXT, estimated_value REAL,
            currency TEXT, url TEXT, notice_type TEXT,
            content_hash TEXT UNIQUE,
            collected_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS intelligence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER REFERENCES notices(id),
            client_id INTEGER REFERENCES clients(id),
            relevance_score INTEGER, summary_en TEXT, summary_pl TEXT,
            impact TEXT, created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER, period_from TEXT, period_to TEXT,
            html TEXT, sent_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_hash ON notices(content_hash);
        CREATE INDEX IF NOT EXISTS idx_intel_client ON intelligence(client_id);
    """)
    conn.commit(); conn.close()
    print(f"DB ready: {DB_PATH}")

def notice_exists(h):
    conn = get_conn()
    row = conn.execute("SELECT id FROM notices WHERE content_hash=?", (h,)).fetchone()
    conn.close()
    return row is not None

def insert_notice(n):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO notices (notice_id,source,title,description,cpv_codes,
        buyer_name,buyer_country,publication_date,deadline,estimated_value,
        currency,url,notice_type,content_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (n["notice_id"],n["source"],n.get("title",""),n.get("description",""),
          json.dumps(n.get("cpv_codes",[])),n.get("buyer_name",""),
          n.get("buyer_country",""),n.get("publication_date",""),
          n.get("deadline",""),n.get("estimated_value"),n.get("currency",""),
          n.get("url",""),n.get("notice_type",""),n["content_hash"]))
    conn.commit(); new_id = cur.lastrowid; conn.close()
    return new_id

def insert_intelligence(i):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO intelligence (notice_id,client_id,relevance_score,
        summary_en,summary_pl,impact)
        VALUES (?,?,?,?,?,?)
    """, (i["notice_id"],i["client_id"],i["relevance_score"],
          i.get("summary_en",""),i.get("summary_pl",""),i.get("impact","MEDIUM")))
    conn.commit(); new_id = cur.lastrowid; conn.close()
    return new_id

def get_client_intelligence(client_id, days_back=7):
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.*, n.title, n.buyer_name, n.buyer_country, n.deadline,
               n.estimated_value, n.currency, n.url, n.cpv_codes
        FROM intelligence i JOIN notices n ON n.id=i.notice_id
        WHERE i.client_id=? AND i.created_at>=datetime('now',? ||' days')
        ORDER BY i.relevance_score DESC
    """, (client_id, f"-{days_back}")).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_clients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_client(name, email, profile):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO clients (name,email,profile) VALUES (?,?,?)",
        (name, email, json.dumps(profile)))
    conn.commit(); new_id = cur.lastrowid; conn.close()
    return new_id
PYEOF

# ── processing/dedup.py ───────────────────────────────────────
cat > processing/dedup.py << 'PYEOF'
import hashlib
from database.db import notice_exists

def make_hash(n):
    key = f"{n['source']}:{n['notice_id']}" if n.get("notice_id") else \
          f"{n['source']}:{n.get('title','')}:{n.get('publication_date','')}"
    return hashlib.sha256(key.encode()).hexdigest()

def deduplicate(notices):
    seen = set(); out = []
    for n in notices:
        h = make_hash(n); n["content_hash"] = h
        if h in seen or notice_exists(h):
            continue
        seen.add(h); out.append(n)
    print(f"Dedup: {len(notices)-len(out)} dropped, {len(out)} new")
    return out
PYEOF

# ── processing/relevance.py ───────────────────────────────────
cat > processing/relevance.py << 'PYEOF'
HIGH, MEDIUM = 6, 3

def score(notice, profile):
    total = 0
    for pc in profile.get("cpv_codes", []):
        for nc in notice.get("cpv_codes", []):
            if str(nc) == str(pc): total += 5
            elif str(nc).startswith(str(pc)) or str(pc).startswith(str(nc)): total += 3
    text = f"{notice.get('title','')} {notice.get('description','')}".lower()
    for kw in profile.get("keywords", []):
        if kw.lower() in text: total += 2
    if notice.get("buyer_country") in profile.get("countries", []): total += 1
    mv = profile.get("min_value")
    if mv and notice.get("estimated_value") and notice["estimated_value"] < mv:
        return 0
    return total

def impact_label(s):
    return "HIGH" if s >= HIGH else "MEDIUM" if s >= MEDIUM else "LOW"

def filter_and_score(notices, profile):
    min_s = profile.get("min_relevance_score", MEDIUM)
    out = []
    for n in notices:
        s = score(n, profile)
        if s >= min_s:
            n["relevance_score"] = s
            n["impact"] = impact_label(s)
            out.append(n)
    out.sort(key=lambda x: x["relevance_score"], reverse=True)
    print(f"Relevance: {len(out)}/{len(notices)} passed")
    return out
PYEOF

# ── processing/translate.py ───────────────────────────────────
cat > processing/translate.py << 'PYEOF'
"""
Gemini Flash — free tier, 1500 req/day.
Key: https://aistudio.google.com/app/apikey
"""
import httpx, os, time, logging

logger = logging.getLogger(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "gemini-2.0-flash:generateContent")
RPM_DELAY = 6.5

def _call(prompt):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400}}
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload,
                        headers={"Content-Type": "application/json"})
        r.raise_for_status()
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return ""

def summarize_notice(n):
    title = n.get("title",""); desc = n.get("description","")
    country = n.get("buyer_country",""); deadline = n.get("deadline","")
    value = n.get("estimated_value"); currency = n.get("currency","EUR")
    val_str = f"{value:,.0f} {currency}" if value else "not specified"
    cpvs = n.get("cpv_codes", [])

    en = f"""Summarize this EU public tender in 3 sentences for a business reader.
1: What is procured and by whom (country: {country}).
2: Key requirements or scope.
3: Deadline ({deadline}), value ({val_str}).
Title: {title}
Description: {desc[:800]}
CPV: {', '.join(str(c) for c in cpvs)}
English only. No preamble."""

    pl = f"""Streść to zamówienie publiczne w 2 zdaniach po polsku.
1: Co jest przedmiotem i kto ogłasza (kraj: {country}).
2: Termin ({deadline}), wartość ({val_str}).
Tytuł: {title}
Opis: {desc[:400]}
Tylko po polsku. Bez wstępu."""

    try:
        n["summary_en"] = _call(en); time.sleep(RPM_DELAY)
        n["summary_pl"] = _call(pl); time.sleep(RPM_DELAY)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        n["summary_en"] = title; n["summary_pl"] = title
    return n

def summarize_batch(notices, max_items=40):
    notices = notices[:max_items]
    print(f"Summarizing {len(notices)} notices...")
    for i, n in enumerate(notices):
        print(f"  {i+1}/{len(notices)}: {n.get('notice_id','')[:40]}")
        summarize_notice(n)
    return notices
PYEOF

# ── reports/digest.py ─────────────────────────────────────────
cat > reports/digest.py << 'PYEOF'
from datetime import datetime
from pathlib import Path
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

C = {"HIGH":"#c0392b","MEDIUM":"#e67e22","LOW":"#7f8c8d"}
BG= {"HIGH":"#fdf2f2","MEDIUM":"#fef9f0","LOW":"#f8f9fa"}

def _block(n, idx):
    imp = n.get("impact","MEDIUM"); c = C[imp]; bg = BG[imp]
    val = n.get("estimated_value")
    val_s = f"{val:,.0f} {n.get('currency','EUR')}" if val else "—"
    import json
    cpvs = n.get("cpv_codes",[])
    if isinstance(cpvs, str):
        try: cpvs = json.loads(cpvs)
        except: cpvs = []
    return f"""
<div style="margin-bottom:18px;border-left:4px solid {c};background:{bg};
            padding:14px;border-radius:4px;">
  <span style="background:{c};color:white;font-size:11px;padding:2px 7px;
               border-radius:3px;font-weight:bold;">{imp}</span>
  <span style="color:#999;font-size:12px;float:right;">#{idx} · {n.get('source','')} · {n.get('buyer_country','')}</span>
  <h3 style="margin:10px 0 6px;font-size:15px;">
    <a href="{n.get('url','#')}" style="color:#2c3e50;text-decoration:none;">
      {n.get('title','No title')[:120]}
    </a>
  </h3>
  <p style="margin:0 0 8px;color:#444;font-size:14px;line-height:1.5;">
    {n.get('summary_en') or n.get('description','')[:280]}
  </p>
  {"<p style='margin:0 0 6px;color:#666;font-size:13px;font-style:italic;'>" + n.get('summary_pl','') + "</p>" if n.get('summary_pl') else ''}
  <span style="font-size:13px;color:#555;">
    <b>Value:</b> {val_s} &nbsp;·&nbsp;
    <b>Deadline:</b> {n.get('deadline','—')} &nbsp;·&nbsp;
    <b>CPV:</b> {', '.join(str(c) for c in cpvs[:2]) or '—'}
  </span>
  <br><a href="{n.get('url','#')}" style="font-size:13px;color:#2980b9;">→ Full tender</a>
</div>"""

def generate(client_name, notices, period_from, period_to, client_email=""):
    now = datetime.utcnow().strftime("%d %b %Y")
    hi = [n for n in notices if n.get("impact")=="HIGH"]
    me = [n for n in notices if n.get("impact")=="MEDIUM"]
    lo = [n for n in notices if n.get("impact")=="LOW"]

    def sec(label, items, start):
        if not items: return ""
        blocks = "".join(_block(n, start+i) for i,n in enumerate(items))
        return f"<h2 style='margin:28px 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:1px;color:#7f8c8d;border-bottom:1px solid #eee;padding-bottom:5px;'>{label} ({len(items)})</h2>{blocks}"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Tender Intelligence — {client_name}</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
max-width:680px;margin:0 auto;padding:20px;color:#2c3e50;background:#fff;">
<div style="background:#2c3e50;color:white;padding:22px;border-radius:6px;margin-bottom:26px;">
  <div style="font-size:11px;text-transform:uppercase;letter-spacing:2px;opacity:.7;">Tender Intelligence</div>
  <h1 style="margin:4px 0;font-size:20px;">Weekly Digest</h1>
  <div style="opacity:.8;font-size:13px;">{client_name} · {period_from} – {period_to}</div>
</div>
<div style="background:#eaf4fb;border-radius:6px;padding:14px;margin-bottom:22px;font-size:14px;color:#2471a3;">
  <b>{len(notices)} relevant tenders</b> this week —
  <span style="color:{C['HIGH']}">{len(hi)} high</span>,
  <span style="color:{C['MEDIUM']}">{len(me)} medium</span>,
  {len(lo)} low priority.
</div>
{sec('High Priority', hi, 1)}
{sec('Medium Priority', me, len(hi)+1)}
{sec('Low Priority', lo, len(hi)+len(me)+1)}
{'<p style="color:#aaa;text-align:center;font-size:13px;">No relevant tenders this week.</p>' if not notices else ''}
<div style="margin-top:36px;padding-top:16px;border-top:1px solid #eee;
font-size:12px;color:#aaa;text-align:center;">Generated {now} · Tender Intelligence</div>
</body></html>"""

def save(html, path):
    Path(path).write_text(html, encoding="utf-8")
    print(f"Digest saved: {path}")

def send_email(html, to_email, subject):
    smtp_host = os.getenv("SMTP_HOST","smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT","465"))
    smtp_user = os.getenv("SMTP_USER","")
    smtp_pass = os.getenv("SMTP_PASS","")
    if not smtp_user:
        print("SMTP not configured — skipping email")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to_email, msg.as_string())
        print(f"Email sent → {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
PYEOF

# ── profiles/sample_client.json ───────────────────────────────
cat > profiles/sample_client.json << 'PYEOF'
{
  "name": "Test Client",
  "email": "you@example.com",
  "cpv_codes": ["72", "48"],
  "countries": ["PL", "CZ", "DE"],
  "keywords": ["software", "IT", "system", "digital", "oprogramowanie"],
  "days_back": 7,
  "min_value": 50000,
  "min_relevance_score": 3,
  "notes": "IT services, CEE markets"
}
PYEOF

# ── scripts/add_client.py ─────────────────────────────────────
cat > scripts/add_client.py << 'PYEOF'
#!/usr/bin/env python3
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import init_db, insert_client

if len(sys.argv) < 2:
    print("Usage: python scripts/add_client.py profiles/sample_client.json")
    sys.exit(1)

with open(sys.argv[1]) as f:
    p = json.load(f)

init_db()
cid = insert_client(p["name"], p["email"], p)
print(f"Added: {p['name']} <{p['email']}> — ID {cid}")
PYEOF

# ── scripts/run_pipeline.py ───────────────────────────────────
cat > scripts/run_pipeline.py << 'PYEOF'
#!/usr/bin/env python3
"""
Usage:
  python scripts/run_pipeline.py --profile profiles/sample_client.json --dry-run --no-translate
  python scripts/run_pipeline.py   # all DB clients, sends email
"""
import sys, os, json, argparse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

from database.db import (init_db, insert_notice, insert_intelligence,
                         get_client_intelligence, get_all_clients, insert_client)
from collectors import ted, bzp
from processing import dedup, relevance, translate
from reports import digest


def run(profile, client_id, args):
    print(f"\n{'='*55}\nClient: {profile['name']}\n{'='*55}")

    print("\n[1] Collecting...")
    all_notices = ted.collect(profile) + bzp.collect(profile)
    print(f"    Total: {len(all_notices)}")
    if not all_notices:
        print("    Nothing collected."); return 0

    print("\n[2] Deduplicating...")
    new = dedup.deduplicate(all_notices)

    if new:
        print("\n[3] Scoring relevance...")
        scored = relevance.filter_and_score(new, profile)

        if scored:
            if not args.no_translate:
                print("\n[4] Summarizing via Gemini...")
                scored = translate.summarize_batch(scored, max_items=30)
            else:
                print("\n[4] Skipping translation")

            print("\n[5] Storing...")
            for n in scored:
                try:
                    nid = insert_notice(n)
                    insert_intelligence({"notice_id": nid, "client_id": client_id,
                                         "relevance_score": n["relevance_score"],
                                         "summary_en": n.get("summary_en",""),
                                         "summary_pl": n.get("summary_pl",""),
                                         "impact": n["impact"]})
                except Exception as e:
                    print(f"  Store err: {e}")

    intel = get_client_intelligence(client_id, days_back=7)
    print(f"\nDigest: {len(intel)} items")

    period_to   = datetime.utcnow().strftime("%d %b %Y")
    period_from = (datetime.utcnow() - timedelta(days=7)).strftime("%d %b %Y")
    html = digest.generate(profile["name"], intel, period_from, period_to,
                           profile.get("email",""))

    out = Path("output")
    out.mkdir(exist_ok=True)
    slug = profile["name"].lower().replace(" ","_")
    path = out / f"{slug}_{datetime.utcnow().strftime('%Y%m%d')}.html"
    digest.save(html, str(path))

    if not args.dry_run and profile.get("email") and profile["email"] != "you@example.com":
        week = datetime.utcnow().strftime("W%V %Y")
        digest.send_email(html, profile["email"],
                          f"Tender Intelligence — {profile['name']} — {week}")
    else:
        print("Dry run — email skipped")
        print(f"Preview: open {path} in browser")

    return len(intel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", help="Path to client profile JSON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-translate", action="store_true")
    args = ap.parse_args()

    init_db()

    if args.profile:
        p = json.load(open(args.profile))
        # Quick single-run: use client_id 1 or insert temporarily
        clients = get_all_clients()
        match = next((c for c in clients if c["name"]==p["name"]), None)
        if match:
            cid = match["id"]
        else:
            cid = insert_client(p["name"], p["email"], p)
            print(f"Auto-registered client ID {cid}")
        run(p, cid, args)
    else:
        clients = get_all_clients()
        if not clients:
            print("No clients. Run:\n  python scripts/add_client.py profiles/sample_client.json")
            return
        for c in clients:
            p = json.loads(c["profile"])
            p["name"] = c["name"]; p["email"] = c["email"]
            run(p, c["id"], args)

    print("\nDone.")

if __name__ == "__main__":
    main()
PYEOF

# ── install ───────────────────────────────────────────────────
echo ""
echo "Installing dependencies..."
pip install httpx beautifulsoup4 python-dotenv lxml -q

echo ""
echo "=== Done. Next steps: ==="
echo ""
echo "1. Set your Gemini key (get free key at aistudio.google.com):"
echo "   export GEMINI_API_KEY=your_key_here"
echo ""
echo "2. Edit profiles/sample_client.json — change name/email/CPV/countries"
echo ""
echo "3. Test run (no email, no Gemini):"
echo "   python scripts/run_pipeline.py --profile profiles/sample_client.json --dry-run --no-translate"
echo ""
echo "4. Check output/ folder — open the HTML file in the Codespaces browser preview"
echo ""
echo "5. Full run with summaries:"
echo "   python scripts/run_pipeline.py --profile profiles/sample_client.json --dry-run"
