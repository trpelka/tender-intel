# Tender Intelligence

Automated procurement intelligence pipeline for finding relevant IT, cybersecurity and technology tenders across European public procurement data.

## What it does

TED / Polish BZP -> collection -> normalization -> deduplication -> relevance scoring -> filtering -> HTML intelligence digest.

## Current capabilities

- TED procurement notice collection
- Polish BZP / e-Zamówienia collection
- CPV filtering
- Country and publication-date filtering
- Minimum contract-value filtering
- Multilingual keyword matching
- Cybersecurity-specific relevance scoring
- Exact and prefix CPV matching
- Explainable scoring reasons
- HIGH / MEDIUM / LOW prioritization
- Duplicate detection
- HTML weekly digest generation
- Client-specific profiles
- SQLite persistence
- Dry-run mode

## Example

The current sample profile searches Poland, Czechia and Germany for IT and cybersecurity procurement.

Example output:

    10 relevant tenders this week
    10 HIGH | 0 MEDIUM | 0 LOW

Each result contains the tender title, country, value, deadline, CPV codes, direct tender URL and relevance reasons.

## Technology

Python | HTTPX | XML/JSON processing | SQLite | multilingual text matching | procurement CPV classification | HTML reporting

## Project structure

    collectors/       TED and BZP collection
    processing/       normalization, deduplication and relevance
    database/         persistence
    reports/          HTML digest generation
    profiles/         client-specific configurations
    scripts/          pipeline entry points
    output/           generated reports
    tests/            automated tests

## Status

Working MVP. The pipeline currently collects real procurement notices, scores them against client requirements and generates a browser-readable intelligence digest.
