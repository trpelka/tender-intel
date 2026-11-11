#!/usr/bin/env python3
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from database.db import init_db, insert_client

if len(sys.argv) < 2:
    print("Usage: python scripts/add_client.py profiles/sample_client.json")
    sys.exit(1)

with open(sys.argv[1]) as f:
    p = json.load(f)

init_db()
cid = insert_client(p["name"], p["email"], p)
print(f"Added: {p['name']} <{p['email']}> — ID {cid}")
