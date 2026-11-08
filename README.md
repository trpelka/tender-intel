# Tender Intelligence

Automated procurement intelligence for IT, cybersecurity and technology tenders across European public procurement data.

```text
TED / Polish BZP
      |
      v
 collection -> normalization -> deduplication -> relevance scoring
      |
      v
 optional Gemini summaries -> SQLite -> HTML digest / email
```

## What it does

- Collects EU notices from the public **TED** API (no authentication required)
- Collects Polish below-threshold tenders from the **BZP** RSS feed
- Filters by CPV codes, countries, publication date and minimum contract value
- Matches multilingual keywords against titles and descriptions
- Scores relevance with explainable rules and labels each notice `HIGH` / `MEDIUM` / `LOW`
- Summarises notices in English and Polish with Gemini Flash (optional)
- Stores notices, clients and intelligence in SQLite
- Generates a browser-readable HTML digest and optionally emails it via SMTP

## Quick start

```bash
git clone https://github.com/trpelka/tender-intel.git
cd tender-intel
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Optional configuration — only needed for summaries and email:

```bash
cp .env.example .env
```

First run, without Gemini, database writes or email:

```bash
python scripts/run_pipeline.py --profile profiles/sample_client.json --dry-run --no-translate
```

The digest is written to `output/`. Open the HTML file in a browser.

Run with Gemini summaries, still without storing or emailing:

```bash
python scripts/run_pipeline.py --profile profiles/sample_client.json --dry-run
```

Full pipeline for all registered clients:

```bash
python scripts/add_client.py profiles/sample_client.json
python scripts/run_pipeline.py
```

Without `--dry-run`, results are written to `tender_intel.db` and an email is sent if SMTP is configured.

## Client profiles

A profile is a JSON file describing what a client cares about. `--profile` auto-registers the client if its name is not in the database yet; running without `--profile` processes every active client.

```json
{
  "name": "Test Client",
  "email": "you@example.com",
  "cpv_codes": ["72", "48"],
  "countries": ["PL", "CZ", "DE"],
  "keywords": ["software", "IT", "system", "digital", "oprogramowanie"],
  "days_back": 7,
  "min_value": 50000,
  "min_relevance_score": 3,
  "notes": "IT services, CEE markets"
}
```

| Field | Meaning |
| --- | --- |
| `cpv_codes` | CPV prefixes to match. `72` covers IT services, `48` software packages |
| `countries` | Buyer country codes |
| `keywords` | Case-insensitive terms matched against title and description |
| `days_back` | Publication lookback window |
| `min_value` | Notices below this estimated value are discarded |
| `min_relevance_score` | Minimum score to appear in the digest (default 3) |

## How relevance is scored

| Signal | Points |
| --- | --- |
| Exact CPV match | +5 |
| Related / prefix CPV match | +3 |
| Each keyword match | +2 |
| Buyer country in profile | +1 |
| Below `min_value` | score forced to 0 |

Impact labels: `HIGH` at 6+, `MEDIUM` at 3+, otherwise `LOW`. The rules are in [`processing/relevance.py`](./processing/relevance.py), so a score can always be explained.

## Output

- `output/<client>_YYYYMMDD.html` — the digest
- `tender_intel.db` — SQLite tables `clients`, `notices`, `intelligence`, `digests`

## Environment variables

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Enables EN/PL summaries. Free key: https://aistudio.google.com/app/apikey |
| `SMTP_HOST`, `SMTP_PORT` | Mail server (defaults: `smtp.gmail.com`, `465`) |
| `SMTP_USER`, `SMTP_PASS` | SMTP credentials; for Gmail use an app password |
| `DATABASE_URL` | SQLite path (default `tender_intel.db`) |

Without `GEMINI_API_KEY` the pipeline still runs; notices keep their original titles. Without SMTP settings the digest is only written to disk.

## Project structure

```text
collectors/       TED API and BZP RSS collection
processing/       normalization helpers, deduplication, relevance scoring, Gemini summaries
database/         SQLite schema and queries
reports/          HTML digest generation and email delivery
profiles/         example client profile
scripts/          run_pipeline.py, add_client.py
output/           generated digests (created at runtime)
requirements.txt
.env.example
setup.sh          optional bootstrap for an empty sandbox
```

`setup.sh` regenerates the source tree from embedded templates. Do not run it on an existing checkout unless you intend to overwrite files.

## Limitations

- The BZP RSS feed does not expose CPV codes, so Polish below-threshold notices are matched mainly by keywords.
- Gemini summaries are rate-limited (a delay between requests) and capped per run.
- Email delivery requires valid SMTP credentials.
- There is no automated test suite yet; use `--dry-run` and inspect a generated digest after changes.
- TED and BZP are external services: schema or feed changes can break collection until the adapters are updated.

## Status

Working MVP. The pipeline collects real procurement notices, scores them against a client profile and produces a browser-readable intelligence digest.
