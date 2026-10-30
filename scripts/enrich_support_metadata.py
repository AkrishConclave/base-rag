#!/usr/bin/env python3
"""Generate search phrases for a local support export using Yandex AI Studio."""
from __future__ import annotations

import argparse
from pathlib import Path
from api.chroma.enrichment import enrich_missing_search_phrases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    if not args.in_place:
        raise SystemExit("Refusing to modify the export without --in-place")
    raise SystemExit("Use POST /api/ingest: enrichment now runs automatically before indexing.")


if __name__ == "__main__":
    main()
