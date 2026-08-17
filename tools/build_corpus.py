#!/usr/bin/env python3
"""Build the reference corpus of Italian lemmas for the validation workflow.

The corpus is the set of entries `etimo` is meant to be able to read, and it is
taken from **the same edition the tool reads**: `Category:Italian lemmas` on
en.wiktionary.org. Drawing the universe from one dictionary and validating
against another would make the coverage figure measure the overlap between two
projects rather than the quality of this one.

**Membership is asked, never guessed.** Wiktionary already separates lemmas
from inflected forms — 129 665 against 468 090 at the time of writing — so the
category answers the question directly. An earlier version inferred it from the
ending instead, and excluded every infinitive (`mangiare`, `sapere`) along with
any word over eight letters ending in a vowel (`capolavoro`, `formaggio`):
thirty per cent of the seed, and precisely the entries where real defects had
been found. A corpus that drops the hard cases measures the easy half and calls
it coverage.

Acronyms are subtracted the same way, by category rather than by shape, because
they are out of scope: an acronym does not descend from its expansion.

The snapshot is **immutable**. Rebuilding it daily would leave the ledger
chasing a universe that moves under it, and coverage percentages computed
against a shifting denominator mean nothing. A snapshot is written once and
refused thereafter unless `--force` says otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tools" / "validation" / "sample_words.json"
DEFAULT_OUTPUT = ROOT / "tools" / "validation" / "corpus_catalog.json"
WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"

LEMMA_CATEGORY = "Category:Italian lemmas"

# Out of scope, and each asked of the source rather than inferred from capitals:
# `TV` is uppercase and a plain shortening, `d.C.` is neither.
EXCLUDED_CATEGORIES = (
    "Category:Italian acronyms",
    "Category:Italian initialisms",
    "Category:Italian abbreviations",
)

USER_AGENT = "etimo/validation-corpus-builder (https://en.wiktionary.org)"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_cases(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("words", payload.get("items", []))
    if isinstance(payload, list):
        words: list[str] = []
        for item in payload:
            if isinstance(item, str):
                words.append(item)
            elif isinstance(item, dict):
                word = item.get("word")
                if word:
                    words.append(str(word))
        return words
    raise ValueError(f"input must be a list of words or a dict with 'words': {path}")


def _fetch_category_members(
    category: str,
    *,
    api_endpoint: str = WIKTIONARY_API,
    max_pages: int | None = None,
    delay: float = 0.2,
    progress: bool = False,
) -> list[str]:
    """Every page in a category, following continuation to the end.

    `max_pages` exists for rehearsals only. It truncates at whatever the API
    returns first, which is one alphabetical stretch of the category and not a
    sample of it — a corpus built that way would validate the letter A.
    """
    titles: list[str] = []
    continue_token: str | None = None

    while True:
        params: dict[str, str] = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "page",
            "cmlimit": "max",
            "cmnamespace": "0",
        }
        if continue_token:
            params["cmcontinue"] = continue_token

        request = urllib.request.Request(
            f"{api_endpoint}?{urllib.parse.urlencode(params)}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 429:
                time.sleep(5.0)
                continue
            raise

        for entry in payload.get("query", {}).get("categorymembers", []):
            title = str(entry.get("title", "")).strip()
            if title and not title.lower().startswith("category:"):
                titles.append(title)
                if max_pages is not None and len(titles) >= max_pages:
                    return titles[:max_pages]

        continue_token = payload.get("continue", {}).get("cmcontinue")
        if not continue_token:
            break
        if progress:
            print(f"  … {len(titles)} from {category}", file=sys.stderr)
        time.sleep(delay)

    return titles


def _normalize_word(word: str) -> str:
    value = str(word).strip().replace(" ", " ")
    return re.sub(r"\s+", " ", value)


def _dataset_hash(words: list[str]) -> str:
    """A digest of the corpus contents, not of the file holding them.

    Hashing the file would change with formatting and with the timestamp in
    its own metadata; hashing the sorted lemmas identifies the *universe*, so
    two runs that see the same category agree, and a run that sees a changed
    category says so.
    """
    digest = hashlib.sha256()
    for word in sorted(words):
        digest.update(word.encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def build_catalog(
    output_file: Path,
    *,
    source_mode: str = "api",
    input_file: Path | None = None,
    snapshot_id: str | None = None,
    api_endpoint: str = WIKTIONARY_API,
    max_pages: int | None = None,
    force: bool = False,
    progress: bool = False,
) -> dict[str, Any]:
    if output_file.exists() and not force:
        existing = json.loads(output_file.read_text(encoding="utf-8"))
        current = existing.get("corpus_metadata", {}).get("snapshot_id")
        raise SystemExit(
            f"snapshot «{current}» already exists at {output_file}.\n"
            "A snapshot is the fixed denominator every coverage figure is "
            "measured against; rebuilding it silently would make yesterday's "
            "percentages incomparable with today's. Pass --force to replace "
            "it deliberately, and expect the ledger to be reconciled."
        )

    excluded_titles: set[str] = set()
    if source_mode == "api":
        if progress:
            print(f"Fetching {LEMMA_CATEGORY} …", file=sys.stderr)
        words = _fetch_category_members(
            LEMMA_CATEGORY,
            api_endpoint=api_endpoint,
            max_pages=max_pages,
            progress=progress,
        )
        for category in EXCLUDED_CATEGORIES:
            if progress:
                print(f"Fetching {category} …", file=sys.stderr)
            excluded_titles.update(
                _fetch_category_members(category, api_endpoint=api_endpoint)
            )
        source_name = "en.wiktionary category"
    else:
        if input_file is None:
            raise ValueError("input_file is required when source_mode is 'seed'")
        words = _load_cases(input_file)
        source_name = "seed_input"

    seen: set[str] = set()
    allowed: list[str] = []
    excluded: list[str] = []
    for raw in words:
        word = _normalize_word(raw)
        if not word or word.casefold() in seen:
            continue
        seen.add(word.casefold())
        (excluded if word in excluded_titles else allowed).append(word)

    allowed.sort(key=lambda s: s.casefold())
    snapshot = snapshot_id or f"corpus-{datetime.now(timezone.utc):%Y%m%d}"

    payload = {
        "corpus_metadata": {
            "snapshot_id": snapshot,
            "dump_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "dataset_hash": _dataset_hash(allowed),
            "source_mode": source_mode,
            "source_url": api_endpoint if source_mode == "api" else None,
            "source_category": LEMMA_CATEGORY if source_mode == "api" else None,
            "source_file": str(input_file) if input_file else None,
            "excluded_categories": list(EXCLUDED_CATEGORIES)
            if source_mode == "api"
            else [],
            "truncated_at": max_pages,
            "total_corpus_lemmas": len(allowed),
            "excluded_count": len(excluded),
            "schema_version": 2,
            "generated_at": _utc_now(),
        },
        "items": [
            {"word": word, "language": "it", "kind": "target_lemma",
             "source": source_name}
            for word in allowed
        ],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the immutable reference corpus of Italian lemmas."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", choices=("api", "seed"), default="api")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help="Seed file, used only with --source seed.")
    parser.add_argument("--snapshot-id", type=str, default=None,
                        help="Stable identifier for this snapshot.")
    parser.add_argument("--api-endpoint", type=str, default=WIKTIONARY_API)
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Rehearsal only: truncates alphabetically, so the "
                             "result is a prefix of the category and not a sample.")
    parser.add_argument("--force", action="store_true",
                        help="Replace an existing snapshot deliberately.")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()

    catalog = build_catalog(
        args.output,
        source_mode=args.source,
        input_file=args.input if args.source == "seed" else None,
        snapshot_id=args.snapshot_id,
        api_endpoint=args.api_endpoint,
        max_pages=args.max_pages,
        force=args.force,
        progress=args.progress,
    )
    metadata = catalog["corpus_metadata"]
    print(json.dumps({
        "snapshot_id": metadata["snapshot_id"],
        "dataset_hash": metadata["dataset_hash"],
        "total_corpus_lemmas": metadata["total_corpus_lemmas"],
        "excluded_count": metadata["excluded_count"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
