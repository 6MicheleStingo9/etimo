#!/usr/bin/env python3
"""Walk every Italian lemma once, and record where etimo gets to.

This answers a different question from the nightly audit, and the two are
deliberately separate.

**The audit asks whether the parser has broken**, and for that a sample
suffices: a structural regression is a property of the code, not of the entry,
so thirty template-only entries a night establish as much as seventy thousand
would. It never ends, because the source never stops moving.

**This asks how far the tool reaches across the whole language** — how many of
the 127101 lemmas yield a chain, how many stop at a limit of the program, how
many at a limit of the source. That is a property of the *distribution*, so no
sample answers it: it has to be counted. And it ends, which is why it is a
separate run rather than a quota inside the nightly one, where it would be
throttled forever by work that has no end.

**What it does not establish.** A recorded chain is not a correct chain.
`Trebisacce` once descended from «tre bisacce» — three saddlebags — while its
own entry said the name is a corruption of τραπεζὰκιον, and every structural
check passed. A survey of this kind maps where the tool arrives; whether what
it says there is true is a question for the hand-written expectations and for
a reader.

Results are appended as JSON Lines rather than rewritten as one document. The
run takes days and will be interrupted; appending means an interruption costs
the entry in flight and nothing else, and that the file is never rewritten at
65 MB to add one row.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from etimo.cache import DiskCache  # noqa: E402
from etimo.cache import default_path as default_cache_path  # noqa: E402
from etimo.models import Node  # noqa: E402
from etimo.walker import Reconstructor  # noqa: E402
from etimo.wiktionary import (  # noqa: E402
    DictSource,
    SourceError,
    WikitextSource,
    WiktionaryClient,
)

DEFAULT_CORPUS = ROOT / "tools" / "validation" / "corpus_catalog.json"
DEFAULT_OUTPUT = ROOT / "tools" / "validation" / "corpus-survey.jsonl"


def _load_corpus(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(
            f"no corpus at {path}. Build one first:\n"
            "  python tools/build_corpus.py --source api --progress"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not items:
        raise SystemExit(f"{path} holds no items")
    return items


def _already_done(path: Path) -> set[str]:
    """Words already surveyed, read back from the append-only log.

    A truncated final line is skipped rather than fatal: the process was
    killed mid-write, and that entry is simply surveyed again.
    """
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                done.add(json.loads(line)["word"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def _terminals(node: Node) -> list[Node]:
    if not node.children:
        return [node]
    found: list[Node] = []
    for child in node.children:
        found.extend(_terminals(child))
    return found


def _survey_one(word: str, source: WikitextSource) -> dict[str, Any]:
    """Where the walk got to for one lemma, and at whose limit it stopped."""
    started = time.perf_counter()
    try:
        result = Reconstructor(source).reconstruct(word, "it")
    except SourceError as error:
        return {"word": word, "outcome": "unreachable", "error": str(error)[:120]}
    except Exception as error:  # a survey must not stop on one entry
        return {
            "word": word,
            "outcome": "exception",
            "error": f"{type(error).__name__}: {error}"[:160],
        }

    leaves = _terminals(result.start)
    terminals = [leaf.terminal for leaf in leaves if leaf.terminal is not None]
    linguistic = [t for t in terminals if t.is_linguistic]

    # An entry "reaches an end" when the walk stopped because the language had
    # nothing more to give. It "hits a limit" when the source or this program
    # could not go on. A tree with several branches can do both, and the
    # distinction is what the whole project turns on, so it is recorded per
    # branch and not collapsed into one verdict.
    if result.steps == 0 and not linguistic:
        outcome = "no chain"
    elif linguistic and len(linguistic) == len(terminals):
        outcome = "complete"
    elif linguistic:
        outcome = "partial"
    else:
        outcome = "limited"

    return {
        "word": word,
        "outcome": outcome,
        "steps": result.steps,
        "terminals": sorted({t.name.lower() for t in terminals}),
        "linguistic_terminals": len(linguistic),
        "total_terminals": len(terminals),
        "resolved_to": result.start.form.lemma if result.resolved else None,
        "etymologies": result.available_senses,
        "requests": result.requests,
        "seconds": round(time.perf_counter() - started, 2),
    }


def _summarise(path: Path) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    terminals: Counter[str] = Counter()
    steps_total = 0
    counted = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            outcomes[row.get("outcome", "?")] += 1
            counted += 1
            steps_total += int(row.get("steps") or 0)
            for name in row.get("terminals", []):
                terminals[name] += 1
    return {
        "surveyed": counted,
        "outcomes": dict(outcomes.most_common()),
        "terminals": dict(terminals.most_common()),
        "mean_steps": round(steps_total / counted, 2) if counted else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Survey how far etimo reaches across the Italian corpus."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Stop after this many entries (0 = no limit).",
    )
    parser.add_argument(
        "--minutes", type=float, default=0.0,
        help="Stop after this long. A survey of 127101 entries runs for days; "
             "this is what lets a scheduled job take a slice and hand over.",
    )
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument(
        "--offline-fixtures", type=Path, default=None,
        help="Survey against frozen pages instead of the network.",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print the totals for what has been surveyed so far, and exit.",
    )
    parser.add_argument("--summary-md", type=Path, default=None)
    args = parser.parse_args()

    if args.summary:
        print(json.dumps(_summarise(args.output), ensure_ascii=False, indent=2))
        return 0

    corpus = _load_corpus(args.corpus)
    done = _already_done(args.output)
    pending = [item for item in corpus if item.get("word") not in done]

    print(
        f"corpus {len(corpus)} · surveyed {len(done)} · remaining {len(pending)}",
        file=sys.stderr,
    )
    if not pending:
        print(json.dumps(_summarise(args.output), ensure_ascii=False, indent=2))
        return 0

    if args.offline_fixtures and args.offline_fixtures.exists():
        source: WikitextSource = DictSource(
            json.loads(args.offline_fixtures.read_text(encoding="utf-8"))
        )
    else:
        source = DiskCache(
            WiktionaryClient(), path=args.cache_dir or default_cache_path()
        )

    deadline = time.monotonic() + args.minutes * 60 if args.minutes else None
    processed = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Opened in append mode and flushed per row: the run will be interrupted,
    # and an interruption must cost the entry in flight and nothing more.
    with args.output.open("a", encoding="utf-8") as handle:
        for item in pending:
            if args.limit and processed >= args.limit:
                break
            if deadline and time.monotonic() >= deadline:
                break
            row = _survey_one(item["word"], source)
            row["at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            processed += 1
            if processed % 100 == 0:
                print(f"  {processed} surveyed…", file=sys.stderr)
            if args.delay and not isinstance(source, DictSource):
                time.sleep(args.delay)

    summary = _summarise(args.output)
    summary["processed_this_run"] = processed
    summary["remaining"] = len(pending) - processed
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.summary_md:
        total = summary["surveyed"] + summary["remaining"]
        lines = [
            "## Corpus survey",
            "",
            f"**{summary['surveyed']} of {total}** lemmas surveyed "
            f"({100 * summary['surveyed'] / max(1, total):.1f}%), "
            f"{processed} this run.",
            "",
            "| outcome | count | meaning |",
            "|---|---:|---|",
        ]
        meaning = {
            "complete": "every branch ended on a fact about the language",
            "partial": "some branches ended on a fact, others on a limit",
            "limited": "every branch stopped at a limit of source or program",
            "no chain": "no ancestor could be read at all",
            "unreachable": "the source could not be reached",
            "exception": "the walk raised an unexpected error",
        }
        for name, count in summary["outcomes"].items():
            lines.append(f"| `{name}` | {count} | {meaning.get(name, '')} |")
        args.summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
