#!/usr/bin/env python3
"""
Usage:

  python scripts/run_pipeline.py \
      --profile profiles/sample_client.json \
      --dry-run \
      --no-translate

  python scripts/run_pipeline.py
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database.db import (
    init_db,
    insert_notice,
    insert_intelligence,
    get_client_intelligence,
    get_all_clients,
    insert_client,
)

from collectors import ted, bzp
from processing import dedup, relevance, translate
from reports import digest


def now_utc():
    return datetime.now(UTC)


def run(profile, client_id, args):

    print(f"\n{'=' * 55}")
    print(f"Client: {profile['name']}")
    print(f"{'=' * 55}")

    # --------------------------------------------------------
    # 1. COLLECT
    # --------------------------------------------------------
    print("\n[1] Collecting...")

    ted_notices = ted.collect(profile)
    bzp_notices = bzp.collect(profile)

    all_notices = ted_notices + bzp_notices

    print(f"    Total: {len(all_notices)}")

    if not all_notices:
        print("    Nothing collected.")
        return 0

    # --------------------------------------------------------
    # 2. DEDUPLICATE
    # --------------------------------------------------------
    print("\n[2] Deduplicating...")

    new = dedup.deduplicate(all_notices)

    if not new:
        print("    No new opportunities after deduplication.")
        return 0

    # --------------------------------------------------------
    # 3. SCORE
    # --------------------------------------------------------
    print("\n[3] Scoring relevance...")

    scored = relevance.filter_and_score(new, profile)

    if not scored:
        print("    No relevant opportunities.")
        return 0

    # --------------------------------------------------------
    # 4. TRANSLATION / SUMMARIZATION
    # --------------------------------------------------------
    if not args.no_translate:
        print("\n[4] Summarizing via Gemini...")
        scored = translate.summarize_batch(scored, max_items=30)
    else:
        print("\n[4] Skipping translation")

    # --------------------------------------------------------
    # 5. STORE
    # --------------------------------------------------------
    if args.dry_run:

        print("\n[5] Storing...")
        print("    Dry run — database unchanged")

        # Build digest directly from this run.
        # Nothing is written to SQLite.
        intel = []

        for n in scored:
            intel.append({
                "title": n.get("title", ""),
                "buyer_name": n.get("buyer_name", ""),
                "buyer_country": n.get("buyer_country", ""),
                "deadline": n.get("deadline", ""),
                "estimated_value": n.get("estimated_value"),
                "currency": n.get("currency", ""),
                "url": n.get("url", ""),
                "cpv_codes": json.dumps(
                    n.get("cpv_codes", []),
                    ensure_ascii=False
                ),
                "relevance_score": n.get("relevance_score", 0),
                "summary_en": n.get("summary_en", ""),
                "summary_pl": n.get("summary_pl", ""),
                "impact": n.get("impact", "MEDIUM"),
            })

    else:

        print("\n[5] Storing...")

        stored = 0

        for n in scored:
            try:
                nid = insert_notice(n)

                # Don't create duplicate intelligence for this client.
                from database.db import intelligence_exists
                if intelligence_exists(nid, client_id):
                    continue

                insert_intelligence({
                    "notice_id": nid,
                    "client_id": client_id,
                    "relevance_score": n["relevance_score"],
                    "summary_en": n.get("summary_en", ""),
                    "summary_pl": n.get("summary_pl", ""),
                    "impact": n.get("impact", "MEDIUM"),
                })

                stored += 1

            except Exception as e:
                print(f"  Store err: {e}")

        print(f"    Stored: {stored}")

        intel = get_client_intelligence(
            client_id,
            days_back=profile.get("days_back", 7)
        )

    # --------------------------------------------------------
    # DIGEST
    # --------------------------------------------------------
    print(f"\nDigest: {len(intel)} items")

    now = now_utc()

    period_to = now.strftime("%d %b %Y")
    period_from = (
        now - timedelta(days=profile.get("days_back", 7))
    ).strftime("%d %b %Y")

    html = digest.generate(
        profile["name"],
        intel,
        period_from,
        period_to,
        profile.get("email", "")
    )

    out = Path("output")
    out.mkdir(exist_ok=True)

    slug = profile["name"].lower().replace(" ", "_")

    path = out / (
        f"{slug}_{now.strftime('%Y%m%d')}.html"
    )

    digest.save(html, str(path))

    # --------------------------------------------------------
    # EMAIL
    # --------------------------------------------------------
    if (
        not args.dry_run
        and profile.get("email")
        and profile["email"] != "you@example.com"
    ):
        week = now.strftime("W%V %Y")

        digest.send_email(
            html,
            profile["email"],
            f"Tender Intelligence — {profile['name']} — {week}"
        )

    else:
        print("Dry run — email skipped")
        print(f"Preview: open {path} in browser")

    return len(intel)


def main():

    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--profile",
        help="Path to client profile JSON"
    )

    ap.add_argument(
        "--dry-run",
        action="store_true"
    )

    ap.add_argument(
        "--no-translate",
        action="store_true"
    )

    args = ap.parse_args()

    init_db()

    # --------------------------------------------------------
    # SINGLE PROFILE
    # --------------------------------------------------------
    if args.profile:

        with open(args.profile, encoding="utf-8") as f:
            p = json.load(f)

        clients = get_all_clients()

        match = next(
            (
                c for c in clients
                if c["name"] == p["name"]
            ),
            None
        )

        if match:
            cid = match["id"]
        else:
            cid = insert_client(
                p["name"],
                p["email"],
                p
            )
            print(f"Auto-registered client ID {cid}")

        run(p, cid, args)

    # --------------------------------------------------------
    # ALL DB CLIENTS
    # --------------------------------------------------------
    else:

        clients = get_all_clients()

        if not clients:
            print(
                "No clients. Run:\n"
                "  python scripts/add_client.py "
                "profiles/sample_client.json"
            )
            return

        for c in clients:

            p = json.loads(c["profile"])

            p["name"] = c["name"]
            p["email"] = c["email"]

            run(p, c["id"], args)

    print("\nDone.")


if __name__ == "__main__":
    main()
