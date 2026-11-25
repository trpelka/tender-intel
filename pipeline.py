"""The collection pipeline as a callable, shared by the CLI and the API.

Keeping stages in the CLI entry point made them impossible to test or reuse.
This module has no argument parsing and no `print` contract: it takes a profile
and returns a structured result.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from pathlib import Path

from collectors import bzp, ted
from database.repository import Repository
from processing import dedup, relevance, translate
from reports import digest


@dataclass
class RunResult:
    notices_collected: int
    unique: int
    scored: int
    stored: int
    digest_items: int
    digest_path: str


def run(profile: dict, client_id: int, *, dry_run: bool = False,
        no_translate: bool = False, out_dir: str = "output",
        repo: Repository | None = None, send_email: bool = False) -> RunResult:
    repo = repo or Repository()

    notices = ted.collect(profile) + bzp.collect(profile)
    collected = len(notices)
    if not notices:
        return RunResult(collected, 0, 0, 0, 0, "")

    unique = dedup.deduplicate(notices)
    if not unique:
        return RunResult(collected, 0, 0, 0, 0, "")

    scored = relevance.filter_and_score(unique, profile)
    if not scored:
        return RunResult(collected, len(unique), 0, 0, 0, "")
    if not no_translate:
        scored = translate.summarize_batch(scored, max_items=30)

    if dry_run:
        stored = 0
        intel = [{key: n.get(key, "") for key in (
            "title", "buyer_name", "buyer_country", "deadline",
            "estimated_value", "currency", "url", "relevance_score",
            "summary_en", "summary_pl", "impact", "summary_status")}
            for n in scored]
        # digest.generate expects JSON-encoded cpv_codes when rows come from SQL.
        for row, notice in zip(intel, scored, strict=True):
            row["cpv_codes"] = json.dumps(notice.get("cpv_codes", []))
    else:
        stored = repo.store_run(scored, client_id)
        intel = repo.client_intelligence(client_id, profile.get("days_back", 7))

    now = datetime.now(UTC)
    html = digest.generate(
        profile["name"], intel,
        (now - timedelta(days=profile.get("days_back", 7))).strftime("%d %b %Y"),
        now.strftime("%d %b %Y"),
        profile.get("email", ""),
    )
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{profile['name'].lower().replace(' ', '_')}_{now:%Y%m%d}.html"
    digest.save(html, str(path))

    if send_email and not dry_run and profile.get("email") and \
            profile["email"] != "you@example.com":
        digest.send_email(html, profile["email"],
                          f"Tender Intelligence — {profile['name']} — {now:%V %Y}")

    return RunResult(collected, len(unique), len(scored), stored, len(intel), str(path))
