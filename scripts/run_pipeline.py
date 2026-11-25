#!/usr/bin/env python3
"""CLI entry point. The pipeline itself lives in `pipeline.py`."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database.migrations import upgrade
from database.repository import Repository
from pipeline import run


def _client_id(repo, profile):
    match = repo.find_client(profile["name"])
    if match:
        return match["id"]
    client_id = repo.insert_client(profile["name"], profile.get("email", ""), profile)
    print(f"Auto-registered client ID {client_id}")
    return client_id


def main():
    ap = argparse.ArgumentParser(description="Run the tender intelligence pipeline")
    ap.add_argument("--profile", help="Path to client profile JSON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--out", default="output", help="digest output directory")
    args = ap.parse_args()

    upgrade()
    repo = Repository()
    profiles = []
    if args.profile:
        with open(args.profile, encoding="utf-8") as handle:
            profiles.append(json.load(handle))
    else:
        clients = repo.clients()
        if not clients:
            print("No clients. Run: python scripts/add_client.py profiles/sample_client.json")
            return 1
        for client in clients:
            profile = json.loads(client["profile"])
            profile["name"] = client["name"]
            profile["email"] = client["email"]
            profiles.append(profile)

    for profile in profiles:
        result = run(profile, _client_id(repo, profile),
                     dry_run=args.dry_run, no_translate=args.no_translate,
                     out_dir=args.out, repo=repo, send_email=not args.dry_run)
        print(f"{profile['name']}: {result.notices_collected} collected, "
              f"{result.unique} unique, {result.scored} scored, "
              f"{result.stored} stored, {result.digest_items} in digest")
        if result.digest_path:
            print(f"Digest: {result.digest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
