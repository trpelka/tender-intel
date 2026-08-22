"""
BZP / e-Zamówienia API collector.

Official BZP WebService:
https://ezamowienia.gov.pl/mo-board/api/v1/notice

Free, public GET API.
Pagination uses SearchAfter = objectId from the previous response.
"""

import httpx
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BZP_API_URL = "https://ezamowienia.gov.pl/mo-board/api/v1/notice"

NOTICE_TYPES = [
    "ContractNotice",
    "SmallContractNotice",
]


def _iso_date(days_back: int = 7):
    now = datetime.utcnow()
    start = now - timedelta(days=days_back)

    return (
        start.strftime("%Y-%m-%dT00:00:00"),
        now.strftime("%Y-%m-%dT23:59:59"),
    )


def _normalize(raw: dict) -> dict:
    """Convert BZP API record to TenderIntel internal schema."""

    notice_id = (
        raw.get("objectId")
        or raw.get("noticeNumber")
        or raw.get("bzpNumber")
        or ""
    )

    title = raw.get("orderObject") or ""

    cpv = raw.get("cpvCode") or []
    if isinstance(cpv, str):
        cpv_codes = [cpv] if cpv else []
    elif isinstance(cpv, list):
        cpv_codes = [
            str(x.get("code", x)) if isinstance(x, dict) else str(x)
            for x in cpv
        ]
    else:
        cpv_codes = []

    description = raw.get("htmlBody") or ""

    return {
        "source": "BZP",
        "notice_id": str(notice_id),
        "title": title,
        "description": description,
        "cpv_codes": cpv_codes,
        "buyer_name": raw.get("organizationName", ""),
        "buyer_country": raw.get("organizationCountry", "PL"),
        "publication_date": raw.get("publicationDate", ""),
        "deadline": raw.get("submittingOffersDate", ""),
        "estimated_value": None,
        "currency": "PLN",
        "url": (
            "https://ezamowienia.gov.pl/"
            "mo-client-board/bzp/notice-details/id/"
            + str(raw.get("objectId", ""))
        ),
        "notice_type": raw.get("noticeType", ""),
        "language": "pl",
        "raw": raw,
    }


def _matches_keywords(notice: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True

    text = (
        f"{notice.get('title', '')} "
        f"{notice.get('description', '')}"
    ).lower()

    return any(str(k).lower() in text for k in keywords)


def fetch_notice_type(
    notice_type: str,
    days_back: int = 7,
    cpv_codes: list[str] | None = None,
    keywords: list[str] | None = None,
    page_size: int = 500,
) -> list[dict]:

    date_from, date_to = _iso_date(days_back)

    notices = []
    search_after = ""

    with httpx.Client(
        timeout=60,
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": "TenderIntel/1.0",
        },
    ) as client:

        while True:

            params = {
                "NoticeType": notice_type,
                "PublicationDateFrom": date_from,
                "PublicationDateTo": date_to,
                "PageSize": page_size,
            }

            if search_after:
                params["SearchAfter"] = search_after

            # CPV filtering is supported directly by the API.
            # Make separate requests for each CPV rather than constructing
            # undocumented expressions.
            if cpv_codes:
                # API accepts one CpvCode value; first broad request is
                # intentionally used, with exact filtering below.
                pass

            try:
                response = client.get(BZP_API_URL, params=params)
                response.raise_for_status()
                data = response.json()

            except Exception as e:
                logger.error(
                    "BZP %s error: %s",
                    notice_type,
                    e,
                )
                break

            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = (
                    data.get("items")
                    or data.get("content")
                    or data.get("notices")
                    or data.get("results")
                    or []
                )
            else:
                rows = []

            if not rows:
                break

            for raw in rows:
                n = _normalize(raw)

                # CPV filter
                if cpv_codes:
                    ncpvs = n["cpv_codes"]

                    cpv_match = any(
                        str(ncpv).startswith(str(pcpv))
                        or str(pcpv).startswith(str(ncpv))
                        for pcpv in cpv_codes
                        for ncpv in ncpvs
                    )

                    if not cpv_match:
                        continue

                # Keyword filter
                if not _matches_keywords(n, keywords or []):
                    continue

                notices.append(n)

            logger.info(
                "BZP %s: fetched %d records, %d matched",
                notice_type,
                len(rows),
                len(notices),
            )

            if len(rows) < page_size:
                break

            last = rows[-1]
            search_after = str(last.get("objectId", ""))

            if not search_after:
                break

    return notices


def collect(profile: dict) -> list[dict]:
    """
    Main BZP collector.

    Collects national contract notices and small-contract notices,
    then applies CPV/keyword filtering.
    """

    days_back = profile.get("days_back", 7)
    cpv_codes = profile.get("cpv_codes", [])
    keywords = profile.get("keywords", [])

    all_notices = []

    for notice_type in NOTICE_TYPES:
        all_notices.extend(
            fetch_notice_type(
                notice_type=notice_type,
                days_back=days_back,
                cpv_codes=cpv_codes,
                keywords=keywords,
            )
        )

    # Remove duplicates within BZP itself.
    seen = set()
    unique = []

    for n in all_notices:
        key = n["notice_id"]

        if not key or key in seen:
            continue

        seen.add(key)
        unique.append(n)

    print(
        f"BZP: {len(unique)} notices after keyword/CPV filtering"
    )

    return unique
