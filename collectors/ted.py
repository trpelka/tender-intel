"""
TED Europa API v3 collector.

Search API:
https://api.ted.europa.eu/v3/notices/search

No API key is required for public notice search.

This collector:
- queries TED v3
- handles TED multilingual/nested field structures
- extracts title, buyer, country, CPV, publication date,
  deadline, value and currency
- extracts a usable description when TED returns one
- preserves the original raw notice
"""

from datetime import datetime, timedelta, UTC
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"


FIELDS = [
    "publication-number",
    "publication-date",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "deadline-receipt-request",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "notice-type",
    "description-proc",
]


COUNTRY_CODES = {
    "PL": "POL",
    "CZ": "CZE",
    "DE": "DEU",
    "AT": "AUT",
    "FR": "FRA",
    "IT": "ITA",
    "ES": "ESP",
    "PT": "PRT",
    "NL": "NLD",
    "BE": "BEL",
    "SE": "SWE",
    "NO": "NOR",
    "DK": "DNK",
    "FI": "FIN",
    "IE": "IRL",
    "RO": "ROU",
    "HU": "HUN",
    "SK": "SVK",
    "SI": "SVN",
    "HR": "HRV",
    "BG": "BGR",
    "GR": "GRC",
    "LT": "LTU",
    "LV": "LVA",
    "EE": "EST",
    "LU": "LUX",
    "CY": "CYP",
    "MT": "MLT",
}


PREFERRED_LANGUAGES = (
    "eng",
    "pol",
    "ces",
    "cze",
    "deu",
    "fra",
    "en",
    "pl",
    "cs",
    "cz",
    "de",
    "fr",
)


def normalize_country(code):
    """Convert common alpha-2 country codes to TED alpha-3."""
    code = str(code).upper().strip()
    return COUNTRY_CODES.get(code, code)


def build_query(
    cpv_codes,
    countries,
    days_back=7,
    min_value=None,
):
    """
    Build the TED expert-search query.

    CPV codes:
      - short codes are treated as prefixes
      - full CPV codes are exact matches

    Countries are OR'ed together.

    Publication date is restricted to the requested period.

    NOTE:
    min_value is currently passed to TED as a numeric filter.
    Currency normalization across different currencies is not
    performed here.
    """

    date_from = (
        datetime.now(UTC) - timedelta(days=days_back)
    ).strftime("%Y%m%d")

    cpv_filters = []

    for code in cpv_codes:
        code = str(code).strip()

        if not code:
            continue

        if len(code) < 5:
            cpv_filters.append(
                f"classification-cpv={code}*"
            )
        else:
            cpv_filters.append(
                f"classification-cpv={code}"
            )

    country_filters = []

    for country in countries:
        country = normalize_country(country)

        if country:
            country_filters.append(
                f"buyer-country={country}"
            )

    parts = []

    if cpv_filters:
        parts.append(
            "("
            + " OR ".join(cpv_filters)
            + ")"
        )

    if country_filters:
        parts.append(
            "("
            + " OR ".join(country_filters)
            + ")"
        )

    parts.append(
        f"publication-date>={date_from}"
    )

    if min_value not in (None, ""):
        parts.append(
            f"estimated-value-proc>={min_value}"
        )

    query = " AND ".join(parts)

    query += " SORT BY publication-date DESC"

    return query


def _extract_results(data):
    """Return the notices list from a TED response."""

    if not isinstance(data, dict):
        return []

    results = data.get("notices", [])

    if isinstance(results, list):
        return results

    return []


def fetch_notices(
    cpv_codes,
    countries,
    days_back=7,
    min_value=None,
):
    """
    Fetch all matching TED notices using page-number pagination.
    """

    query = build_query(
        cpv_codes,
        countries,
        days_back,
        min_value,
    )

    print(f"  TED query: {query}")

    notices = []
    page = 1

    with httpx.Client(timeout=60) as client:

        while True:

            payload = {
                "query": query,
                "fields": FIELDS,
                "page": page,
                "limit": 100,
                "scope": "ACTIVE",
                "checkQuerySyntax": False,
                "paginationMode": "PAGE_NUMBER",
            }

            try:
                resp = client.post(
                    TED_SEARCH_URL,
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code >= 400:
                    print(
                        "  TED response:",
                        resp.text[:2000],
                    )

                resp.raise_for_status()

                data = resp.json()

            except httpx.HTTPError as exc:

                logger.error(
                    f"TED API error p{page}: {exc}"
                )

                break

            except ValueError as exc:

                logger.error(
                    f"TED JSON decode error p{page}: {exc}"
                )

                break

            results = _extract_results(data)

            if not results:
                break

            notices.extend(results)

            print(
                f"  TED page {page}: "
                f"{len(results)} notices"
            )

            total = data.get(
                "totalNoticeCount",
                data.get("total", 0),
            )

            try:
                total = int(total or 0)
            except (TypeError, ValueError):
                total = 0

            if total and page * 100 >= total:
                break

            if len(results) < 100:
                break

            page += 1

    return notices


def _first(value):
    """
    Extract a readable scalar from TED's multilingual/nested
    structures.

    TED fields may appear as:
        "text"
        ["text"]
        {"eng": "text", "pol": "tekst"}
        [{"eng": "text"}]
        {"value": "text"}
        {"@value": "text"}

    English is preferred when available, followed by the
    original/local language.
    """

    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, list):

        for item in value:

            result = _first(item)

            if result:
                return result

        return ""

    if isinstance(value, dict):

        # Preferred language keys first.
        for lang in PREFERRED_LANGUAGES:

            if lang in value:

                result = _first(
                    value.get(lang)
                )

                if result:
                    return result

        # Common scalar keys.
        for key in (
            "value",
            "@value",
            "text",
            "content",
            "name",
            "label",
        ):

            if key in value:

                result = _first(
                    value.get(key)
                )

                if result:
                    return result

        # Fall back to the first useful nested value.
        for item in value.values():

            result = _first(item)

            if result:
                return result

        return ""

    return str(value).strip()


def _clean_list(value):
    """
    Convert TED list/multilingual structures into unique strings.
    """

    if value is None:
        return []

    if not isinstance(value, list):
        value = [value]

    out = []

    for item in value:

        text = _first(item)

        if text:
            text = str(text).strip()

            if text and text not in out:
                out.append(text)

    return out


def _scalar(value):
    """
    Extract a single readable value.
    """

    return _first(value)


def _numeric(value):
    """
    Convert TED numeric values to float.
    """

    value = _first(value)

    if value in (None, ""):
        return None

    text = str(value).strip()

    try:
        return float(text)
    except (TypeError, ValueError):
        pass

    # Handle occasional formatting such as:
    # "3 240 600"
    # "3,240,600"
    cleaned = (
        text
        .replace(" ", "")
        .replace(",", "")
    )

    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _description(raw):
    """
    Extract the best available description field.

    TED may return either short-description or description,
    depending on notice type/API response.
    """

    for key in (
        "short-description",
        "description",
        "notice-description",
        "object-description",
    ):

        value = _first(
            raw.get(key)
        )

        if value:
            return value

    return ""


def normalize(raw):
    """
    Convert a raw TED notice into the application's normalized
    opportunity schema.
    """

    if not isinstance(raw, dict):
        raw = {}

    publication_number = _scalar(
        raw.get(
            "publication-number",
            raw.get(
                "notice-identifier",
                "",
            ),
        )
    )

    title = _first(
        raw.get(
            "notice-title",
            "",
        )
    )

    buyer_name = _first(
        raw.get(
            "buyer-name",
            "",
        )
    )

    buyer_country = _scalar(
        raw.get(
            "buyer-country",
            "",
        )
    )

    cpv_codes = _clean_list(
        raw.get(
            "classification-cpv",
            [],
        )
    )

    deadline = _scalar(
        raw.get(
            "deadline-receipt-request",
            "",
        )
    )

    estimated_value = _numeric(
        raw.get(
            "estimated-value-proc"
        )
    )

    currency = _scalar(
        raw.get(
            "estimated-value-cur-proc",
            "EUR",
        )
    )

    publication_date = _scalar(
        raw.get(
            "publication-date",
            "",
        )
    )

    notice_type = _scalar(
        raw.get(
            "notice-type",
            "",
        )
    )

    description = _description(raw)

    url = (
        "https://ted.europa.eu/en/notice/-/detail/"
        + publication_number
        if publication_number
        else ""
    )

    return {
        "source": "TED",
        "notice_id": publication_number,
        "title": title,
        "description": description,
        "cpv_codes": cpv_codes,
        "buyer_name": buyer_name,
        "buyer_country": buyer_country,
        "publication_date": publication_date,
        "deadline": deadline,
        "estimated_value": estimated_value,
        "currency": currency,
        "url": url,
        "notice_type": notice_type,
        "raw": raw,
    }


def collect(profile):
    """
    Collector entry point used by the application.
    """

    raw = fetch_notices(
        cpv_codes=profile.get(
            "cpv_codes",
            ["72"],
        ),
        countries=profile.get(
            "countries",
            ["PL"],
        ),
        days_back=profile.get(
            "days_back",
            7,
        ),
        min_value=profile.get(
            "min_value",
        ),
    )

    return [
        normalize(notice)
        for notice in raw
    ]

