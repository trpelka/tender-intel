"""
Gemini Flash summarization.
One API request per tender: English + Polish.
"""

import httpx
import os
import logging
import time
import time

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1/"
    "models/gemini-3.6-flash:generateContent"
)


def _call(prompt):
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set")
        return None

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 500
        }
    }

    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        if r.status_code == 429:
            print("    Gemini: 429 rate limit — skipping request")
            return None

        if r.status_code == 503:
            print("    Gemini: 503 unavailable — skipping request")
            return None

        r.raise_for_status()

        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    except (httpx.HTTPError, KeyError, IndexError, TypeError) as e:
        logger.error(f"Gemini error: {e}")
        return None


def summarize_notice(n):
    title = n.get("title", "")
    desc = n.get("description", "")
    country = n.get("buyer_country", "")
    deadline = n.get("deadline", "")
    value = n.get("estimated_value")
    currency = n.get("currency", "EUR")

    val_str = f"{value:,.0f} {currency}" if value else "not specified"
    cpvs = n.get("cpv_codes", [])

    prompt = f"""Analyze this EU public tender.

Return EXACTLY:

EN:
[3 concise sentences in English]

PL:
[2 concise sentences in Polish]

EN:
1. What is being procured and by whom.
2. Key requirements or scope.
3. Deadline, estimated value and currency.

PL:
1. Przedmiot zamówienia i zamawiający.
2. Termin i wartość.

No preamble.

Country: {country}
Deadline: {deadline}
Value: {val_str}

Title:
{title}

Description:
{desc[:1000]}

CPV:
{', '.join(str(c) for c in cpvs)}
"""

    result = _call(prompt)

    if not result:
        n["summary_en"] = title
        n["summary_pl"] = title
        return n

    try:
        if "PL:" in result:
            en_part, pl_part = result.split("PL:", 1)
            n["summary_en"] = en_part.replace("EN:", "", 1).strip() or title
            n["summary_pl"] = pl_part.strip() or title
        else:
            n["summary_en"] = result
            n["summary_pl"] = title
    except Exception as e:
        logger.error(f"Gemini response parsing error: {e}")
        n["summary_en"] = result
        n["summary_pl"] = title

    return n


def summarize_batch(notices, max_items=40):
    notices = notices[:max_items]

    print(f"Summarizing {len(notices)} notices...")

    for i, n in enumerate(notices):
        print(
            f"  {i + 1}/{len(notices)}: "
            f"{n.get('notice_id', '')[:40]}"
        )
        summarize_notice(n)

    return notices
