"""
BZP RSS collector.
Handles malformed XML without breaking the pipeline.
"""

import hashlib
import logging
import re
from datetime import datetime
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

BZP_RSS_URL = "https://bzp.uzp.gov.pl/ZP400PodgladOpublikowanego.aspx?id=rss"


def _clean_xml(text):
    if not text:
        return ""

    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)

    text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)",
        "&amp;",
        text,
    )

    return text


def _parse_xml(text):
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        logger.warning("BZP XML malformed: %s", e)

    cleaned = _clean_xml(text)

    if cleaned != text:
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError as e:
            logger.warning("BZP XML cleanup failed: %s", e)

    return None


def _find_text(item, tag):
    element = item.find(tag)

    if element is not None and element.text:
        return element.text.strip()

    element = item.find(f".//{{*}}{tag}")

    if element is not None and element.text:
        return element.text.strip()

    return ""


def _parse_date(value):
    if not value:
        return ""

    value = value.strip()

    formats = (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return value[:10]


def parse_rss(xml_text):
    root = _parse_xml(xml_text)

    if root is None:
        return []

    channel = root.find("channel")

    if channel is None:
        channel = root.find(".//{*}channel")

    if channel is None:
        logger.warning("BZP RSS: channel element not found")
        return []

    items = channel.findall("item")

    if not items:
        items = channel.findall(".//{*}item")

    notices = []

    for item in items:
        title = _find_text(item, "title")
        link = _find_text(item, "link")
        description = _find_text(item, "description")
        pub_date = _find_text(item, "pubDate")

        if not title:
            continue

        identity = link or title

        notice_id = (
            "BZP-"
            + hashlib.md5(
                identity.encode("utf-8", errors="ignore")
            ).hexdigest()[:12]
        )

        notices.append({
            "source": "BZP",
            "notice_id": notice_id,
            "title": title,
            "description": description,
            "cpv_codes": [],
            "buyer_name": "",
            "buyer_country": "PL",
            "publication_date": _parse_date(pub_date),
            "deadline": "",
            "estimated_value": None,
            "currency": "PLN",
            "url": link,
            "notice_type": "contract-notice",
            "raw": {},
        })

    print(f"  BZP: {len(notices)} notices")

    return notices


def fetch_rss():
    try:
        with httpx.Client(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "TenderIntel/1.0",
                "Accept": "application/rss+xml,application/xml,text/xml,*/*",
            },
        ) as client:
            response = client.get(BZP_RSS_URL)
            response.raise_for_status()
            return parse_rss(response.text)

    except httpx.HTTPError as e:
        logger.error("BZP HTTP error: %s", e)
        return []

    except Exception as e:
        logger.error("BZP error: %s", e)
        return []


def collect(profile):
    notices = fetch_rss()

    if not notices:
        print("  BZP after keyword filter: 0")
        return []

    keywords = [
        str(k).strip().lower()
        for k in profile.get("keywords", [])
        if str(k).strip()
    ]

    if not keywords:
        return notices

    filtered = []

    for notice in notices:
        text = (
            f"{notice.get('title', '')} "
            f"{notice.get('description', '')}"
        ).lower()

        if any(k in text for k in keywords):
            filtered.append(notice)

    print(
        f"  BZP after keyword filter: {len(filtered)}"
    )

    return filtered
