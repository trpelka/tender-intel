import hashlib
import re


def normalize_title(title):
    title = str(title or "").lower()

    parts = re.split(r"\s[–-]\s", title, maxsplit=2)

    if len(parts) >= 3:
        title = parts[-1]

    title = re.sub(
        r"[^a-z0-9ąćęłńóśźżáčďéěíňóřšťúůýž ]+",
        " ",
        title
    )
    return re.sub(r"\s+", " ", title).strip()


def procurement_key(n):
    buyer = str(n.get("buyer_name", "") or "").lower().strip()
    title = normalize_title(n.get("title", ""))
    country = str(n.get("buyer_country", "") or "").upper().strip()

    value = n.get("estimated_value")
    try:
        value = round(float(value), -2) if value is not None else ""
    except (TypeError, ValueError):
        value = ""

    return f"{country}|{buyer}|{title}|{value}"


def make_hash(n):
    if n.get("notice_id"):
        key = f"{n.get('source','')}:{n['notice_id']}"
    else:
        key = (
            f"{n.get('source','')}:"
            f"{normalize_title(n.get('title',''))}:"
            f"{n.get('publication_date','')}"
        )

    return hashlib.sha256(key.encode()).hexdigest()


def deduplicate(notices):
    seen_notice = set()
    seen_procurement = set()
    out = []

    exact_dropped = 0
    procurement_dropped = 0

    for n in notices:
        h = make_hash(n)
        n["content_hash"] = h

        # Only deduplicate within THIS collection run.
        if h in seen_notice:
            exact_dropped += 1
            continue

        seen_notice.add(h)

        pk = procurement_key(n)

        if pk in seen_procurement:
            procurement_dropped += 1
            continue

        seen_procurement.add(pk)
        out.append(n)

    print(
        f"Dedup: {exact_dropped + procurement_dropped} dropped, "
        f"{len(out)} unique opportunities "
        f"({exact_dropped} exact, "
        f"{procurement_dropped} procurement-level)"
    )

    return out
