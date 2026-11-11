from collections import Counter
import re


HIGH = 10
MEDIUM = 5


# ============================================================
# HIGH-VALUE SECURITY KEYWORDS
# ============================================================
#
# These are security concepts which should receive +6 when
# found in the normalized TITLE.
#
# IMPORTANT:
# This list is multilingual because TED titles remain in the
# original procurement language.
#
HIGH_VALUE_KEYWORDS = {
    # --------------------------------------------------------
    # English
    # --------------------------------------------------------
    "cybersecurity",
    "cyber security",
    "cybersecurity audit",
    "security audit",
    "information security",
    "it security",
    "security monitoring",
    "penetration testing",
    "vulnerability",
    "vulnerability assessment",
    "security assessment",
    "cyber risk",
    "cyber risk assessment",
    "incident response",
    "threat intelligence",
    "security operations",
    "security operations center",
    "siem",
    "edr",
    "xdr",
    "firewall",
    "network security",
    "application security",
    "api security",
    "secure software",
    "cyber threat intelligence",

    # --------------------------------------------------------
    # Polish
    # --------------------------------------------------------
    "cyberbezpieczeństwo",
    "cyberbezpieczeństwa",
    "cyberbezpieczeństwem",
    "cybernetyczne bezpieczeństwo",
    "bezpieczeństwo cybernetyczne",
    "bezpieczeństwa cybernetycznego",
    "bezpieczeństwem cybernetycznym",
    "bezpieczeństwo informacji",
    "bezpieczeństwa informacji",
    "bezpieczeństwo informatyczne",
    "bezpieczeństwa informatycznego",
    "bezpieczeństwo sieci",
    "bezpieczeństwa sieci",
    "bezpieczeństwo aplikacji",
    "bezpieczeństwa aplikacji",
    "monitoring bezpieczeństwa",
    "monitorowanie bezpieczeństwa",
    "monitoring cyberbezpieczeństwa",
    "audyt bezpieczeństwa",
    "audyt cyberbezpieczeństwa",
    "testy penetracyjne",
    "testowanie penetracyjne",
    "ocena podatności",
    "ocena ryzyka cybernetycznego",
    "ryzyko cybernetyczne",
    "reagowanie na incydenty",
    "reakcja na incydenty",
    "wykrywanie zagrożeń",
    "zagrożenia cybernetyczne",
    "wywiad o zagrożeniach",
    "wywiad cybernetyczny",
    "centrum operacji bezpieczeństwa",
    "centrum operacji bezpieczeństwa soc",
    "zapora sieciowa",
    "zapory sieciowe",
    "firewalle",
    "firewallów",

    # --------------------------------------------------------
    # Czech
    # --------------------------------------------------------
    "kyberbezpečnost",
    "kyberbezpečnosti",
    "kybernetická bezpečnost",
    "kybernetické bezpečnosti",
    "kybernetickou bezpečnost",
    "bezpečnost informací",
    "informační bezpečnost",
    "bezpečnost informačních systémů",
    "bezpečnost sítě",
    "síťová bezpečnost",
    "bezpečnostní monitoring",
    "monitoring bezpečnosti",
    "monitorování bezpečnosti",
    "bezpečnostní audit",
    "audit kybernetické bezpečnosti",
    "posouzení bezpečnosti",
    "posouzení zranitelnosti",
    "penetrační testování",
    "penetrační test",
    "reakce na incidenty",
    "detekce kybernetických hrozeb",
    "detekci kybernetických hrozeb",
    "kybernetických hrozeb",
    "kybernetické hrozby",
    "bezpečnostní operace",
    "centrum bezpečnostních operací",
    "bezpečnostní operační centrum",
    "firewally",
    "firewallů",
    "ochrana sítě",
}


# Short keywords such as "soc", "edr", "xdr", "siem" must not
# match arbitrary substrings inside words.
#
# For normal words/phrases we allow ordinary substring matching.
# For short technical acronyms we require token boundaries.
SHORT_EXACT_KEYWORDS = {
    "soc",
    "siem",
    "edr",
    "xdr",
    "api",
}


def as_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(x).strip()
            for x in value
            if x not in (None, "")
        ]

    text = str(value).strip()

    return [text] if text else []


def as_text(value):
    if isinstance(value, list):
        return " ".join(
            str(x)
            for x in value
            if x not in (None, "")
        )

    if value is None:
        return ""

    return str(value)


def normalize_keyword(value):
    return " ".join(
        str(value).strip().lower().split()
    )


def keyword_in_text(keyword, text):
    """
    Match a keyword against normalized text.

    For short technical acronyms (SOC/SIEM/EDR/XDR/API),
    require token boundaries.

    For longer security terms, normal substring matching is
    intentional because Polish/Czech inflected or compound
    forms can contain the security root inside a larger word.
    """

    keyword = normalize_keyword(keyword)
    text = normalize_keyword(text)

    if not keyword or not text:
        return False

    if keyword in SHORT_EXACT_KEYWORDS:
        pattern = rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])"
        return re.search(pattern, text) is not None

    return keyword in text


def score(notice, profile):
    """
    Explainable relevance scoring.

    CPV:
      exact match       +8
      prefix match      +2
      ONLY strongest CPV match counts

    Normal title keywords:
      first title keyword      +4
      additional title keyword +2
      title maximum            +8

    High-value security title keywords:
      one or more matches      +6 total

    Description:
      first matching keyword      +1
      maximum                     +2

    Country:
      +1

    Minimum value:
      hard exclusion

    Title and description are taken ONLY from normalized fields.
    Raw TED JSON/XML is never searched by the scorer.
    """

    total = 0
    reasons = []

    # ========================================================
    # CPV
    # ========================================================

    profile_cpvs = as_list(
        profile.get("cpv_codes", [])
    )

    notice_cpvs = as_list(
        notice.get("cpv_codes", [])
    )

    best_cpv = 0
    best_cpv_code = None
    best_profile_code = None

    for pc in profile_cpvs:
        pc = str(pc).strip()

        if not pc:
            continue

        for nc in notice_cpvs:
            nc = str(nc).strip()

            if not nc:
                continue

            if nc == pc:
                points = 8

            elif nc.startswith(pc) or pc.startswith(nc):
                points = 2

            else:
                continue

            if points > best_cpv:
                best_cpv = points
                best_cpv_code = nc
                best_profile_code = pc

    if best_cpv:
        total += best_cpv

        reasons.append(
            f"CPV "
            f"{best_profile_code}/"
            f"{best_cpv_code} "
            f"+{best_cpv}"
        )

    # ========================================================
    # TITLE / DESCRIPTION
    # ========================================================

    title = normalize_keyword(
        notice.get("title", "")
    )

    description = normalize_keyword(
        notice.get("description", "")
    )

    title_hits = []
    high_title_hits = []
    description_hits = []

    profile_keywords = profile.get(
        "keywords",
        []
    )

    for raw_kw in profile_keywords:

        kw = normalize_keyword(raw_kw)

        if not kw:
            continue

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        if keyword_in_text(kw, title):

            if kw in HIGH_VALUE_KEYWORDS:
                high_title_hits.append(kw)
            else:
                title_hits.append(kw)

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        elif keyword_in_text(kw, description):
            description_hits.append(kw)

    # Remove duplicates while preserving order.
    title_hits = list(
        dict.fromkeys(title_hits)
    )

    high_title_hits = list(
        dict.fromkeys(high_title_hits)
    )

    description_hits = list(
        dict.fromkeys(description_hits)
    )

    # ========================================================
    # HIGH-VALUE SECURITY TITLE MATCH
    # ========================================================

    if high_title_hits:

        high_points = 6
        total += high_points

        reasons.append(
            "high-title "
            f"[{', '.join(high_title_hits[:5])}] "
            f"+{high_points}"
        )

    # ========================================================
    # NORMAL TITLE KEYWORDS
    # ========================================================

    if title_hits:

        title_points = min(
            8,
            4 + max(
                0,
                len(title_hits) - 1
            ) * 2
        )

        total += title_points

        reasons.append(
            "title "
            f"[{', '.join(title_hits[:5])}] "
            f"+{title_points}"
        )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    if description_hits:

        description_points = min(
            2,
            len(description_hits)
        )

        total += description_points

        reasons.append(
            "description "
            f"[{', '.join(description_hits[:5])}] "
            f"+{description_points}"
        )

    # ========================================================
    # COUNTRY
    # ========================================================

    countries = {
        str(x).strip().upper()
        for x in profile.get(
            "countries",
            []
        )
    }

    notice_countries = {
        str(x).strip().upper()
        for x in as_list(
            notice.get(
                "buyer_country",
                []
            )
        )
    }

    country_hits = (
        countries &
        notice_countries
    )

    if country_hits:

        total += 1

        reasons.append(
            "country "
            f"{','.join(sorted(country_hits))} "
            "+1"
        )

    # ========================================================
    # MINIMUM VALUE
    # ========================================================

    mv = profile.get("min_value")

    if mv not in (None, ""):

        try:
            minimum = float(mv)

            raw_value = notice.get(
                "estimated_value"
            )

            if isinstance(raw_value, list):
                raw_value = (
                    raw_value[0]
                    if raw_value
                    else None
                )

            if raw_value not in (None, ""):

                value = float(raw_value)

                if value < minimum:
                    return 0, [
                        "below minimum value"
                    ]

        except (
            TypeError,
            ValueError
        ):
            pass

    return total, reasons


def impact_label(score_value):

    if score_value >= HIGH:
        return "HIGH"

    if score_value >= MEDIUM:
        return "MEDIUM"

    return "LOW"


def _deadline_expired(value):
    """Return True only when a notice has a parseable past deadline."""
    if value in (None, ""):
        return False

    from datetime import datetime, timezone

    text = str(value).strip()

    try:
        # TED may use either Z or an explicit UTC offset.
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt < datetime.now(timezone.utc)

    except (TypeError, ValueError):
        return False


def filter_and_score(
    notices,
    profile
):

    min_s = profile.get(
        "min_relevance_score",
        MEDIUM
    )

    try:
        min_s = int(min_s)

    except (
        TypeError,
        ValueError
    ):
        min_s = MEDIUM

    out = []

    expired_count = 0

    for n in notices:

        # A tender whose submission deadline has already passed is
        # not an actionable opportunity. Missing/unparseable deadlines
        # are retained rather than being falsely classified as expired.
        if _deadline_expired(n.get("deadline")):
            expired_count += 1
            continue

        score_value, reasons = score(
            n,
            profile
        )

        if score_value >= min_s:

            if isinstance(
                n.get("buyer_country"),
                list
            ):

                n["buyer_country"] = ",".join(
                    str(x)
                    for x in n[
                        "buyer_country"
                    ]
                    if x not in (
                        None,
                        ""
                    )
                )

            n["relevance_score"] = (
                score_value
            )

            n["impact"] = impact_label(
                score_value
            )

            n["score_reasons"] = reasons

            out.append(n)

    out.sort(
        key=lambda x: x[
            "relevance_score"
        ],
        reverse=True
    )

    print(
        f"Relevance: "
        f"{len(out)}/{len(notices)} passed"
    )

    if out:

        counts = Counter(
            n["impact"]
            for n in out
        )

        print(
            "Impact:",
            ", ".join(
                f"{k}={v}"
                for k, v in sorted(
                    counts.items()
                )
            )
        )

        print(
            "\nTop matches:"
        )

        for i, n in enumerate(
            out[:15],
            1
        ):

            country = as_text(
                n.get(
                    "buyer_country",
                    ""
                )
            )

            print(
                f"{i:2}. "
                f"{n['relevance_score']:>2} "
                f"{n['impact']:<6} "
                f"{country:<8} | "
                f"{n.get('title', '')[:90]}"
            )

            print(
                "    "
                + " | ".join(
                    n.get(
                        "score_reasons",
                        []
                    )
                )
            )

    return out
