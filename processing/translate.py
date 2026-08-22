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
        return None
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
