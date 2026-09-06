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
import hashlib
import json
import sys
import time
import unicodedata
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


def _shape(word: str) -> str:
    """A rough grammatical class, read from the shape of the title alone.

    Not a linguistic judgement — a way of reporting what a partial survey has
    actually looked at. The three non-lemma classes behave quite differently
    from lemmas and would distort any figure quoted without them:

      multiword    `a caldo`, `alla luce del sole` — a phrase has no etymon,
                   it has a history as a phrase, and Wiktionary rarely writes
                   one an Etymology section
      proper       `Acquappesa`, `Abbattista` — a surname descends by a
                   mechanism (place → family) that `{{surname}}` does not
                   express as a relation
      affix        `-mente`, `pre-` — prefixes and suffixes
    """
    if " " in word or "'" in word.strip("'"):
        return "multiword"
    if word.startswith("-") or word.endswith("-"):
        return "affix"
    if word[:1].isupper():
        return "proper"
    return "lemma"


def _survey_order(word: str) -> str:
    """A stable, non-alphabetical position for an entry.

    The survey walks a corpus of 127101 in slices over weeks, so every figure
    it reports before finishing is a figure about its prefix. In alphabetical
    order that prefix is not a sample of anything: Italian puts its adverbial
    locutions under «a» — `a caldo`, `alla moda`, `a gambe all'aria`, because
    they are governed by a preposition — and its toponyms under `Acqua-`,
    `Alb-`, `Alt-`. The first 6805 entries surveyed were 6295 «a» words, 15%
    of them phrases, and reported 45.7% of the corpus as unreadable when the
    true figure for lemmas is 31.6%.

    Hashing the title scatters the walk deterministically: the same order every
    time, resumable, and any prefix of it is a fair sample of the whole. The
    problem was never in the sampling — it was that nobody chose a sampling at
    all, and alphabetical order came for free with a structure inside it.
    """
    return hashlib.sha256(word.encode("utf-8")).hexdigest()


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


class _Recording:
    """A source that keeps every page it hands over.

    The anchoring check needs the raw wikitext of every page the walk read, and
    the walk does not report which pages those were. Wrapping the source is the
    cheapest way to find out: no extra request, and the pages are already in
    memory by the time the tree exists.
    """

    def __init__(self, source: WikitextSource) -> None:
        self.source = source
        self.pages: dict[str, str] = {}

    def wikitext(self, title: str) -> str | None:
        text = self.source.wikitext(title)
        if text:
            self.pages[title] = text
        return text

    def seen(self) -> str:
        """Everything read, titles included.

        The titles matter: the word being looked up is the root of its own
        tree, and an entry does not generally repeat its own name in its
        etymology — `dipelare` says «From {{af|it|di-|pelo|-are}}» and never
        writes "dipelare" anywhere. Comparing against the body alone reported
        the starting word as unanchored on every entry of that shape, which is
        the check accusing the tool of inventing the question it was asked.
        """
        return "\n".join([*self.pages, *self.pages.values()])


def _bare(text: str) -> str:
    """A form stripped of the marks that differ between citations.

    An entry writes `πλατεῖα` where the page is titled `πλᾰτεῖᾰ`, and
    `*ḱḗr ~ *ḱr̥d-` where another writes `*ḱḗr`. Comparing those as strings
    reports a fabrication that did not happen — the same normalisation the
    walker uses when it reconciles two entries, for the same reason.
    """
    decomposed = unicodedata.normalize("NFD", text.lstrip("*").casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _anchoring(root: Node, seen_text: str) -> dict[str, Any]:
    """Whether every form drawn is one the source actually wrote.

    This is the check that matters most and the only one here that does **not**
    go through the parser's tables. It asks a flat textual question — does this
    lemma appear anywhere in the pages the walk read? — so a form the tool
    invented has nowhere to hide, even if the invention came from a table the
    parser and any table-driven check would agree about.

    It cannot say an etymology is *true*: that is Wiktionary's business and not
    ours. It says the tree is **anchored** — that everything in it was taken
    from the source rather than manufactured — which is the only correctness
    this tool can be held to, and the one it can be held to absolutely.

    A form is looked for in the whole of what was read, not in the entry that
    hosts it: the reserve deliberately carries forms from one entry into
    another, so requiring each node to appear in its own parent's page would
    report that design as a defect.
    """
    haystack = _bare(seen_text)
    drawn = [node.form for node in _every_node(root) if node.form.lemma]
    unanchored = [
        f"{form.lemma}::{form.language}"
        for form in drawn
        if _bare(form.lemma) and _bare(form.lemma) not in haystack
    ]
    return {
        "forms_drawn": len(drawn),
        "forms_unanchored": len(unanchored),
        "unanchored": unanchored[:8],
    }


def _every_node(node: Node):
    yield node
    for child in node.children:
        yield from _every_node(child)


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
    recorder = _Recording(source)
    try:
        result = Reconstructor(recorder).reconstruct(word, "it")
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

    anchoring = _anchoring(result.start, recorder.seen())

    return {
        "word": word,
        "outcome": outcome,
        "anchored": anchoring["forms_unanchored"] == 0,
        "steps": result.steps,
        "terminals": sorted({t.name.lower() for t in terminals}),
        **anchoring,
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
    anchored = 0
    with_forms = 0
    unanchored_examples: list[str] = []
    shapes: Counter[str] = Counter()
    by_shape: dict[str, Counter[str]] = {
        name: Counter() for name in ("lemma", "multiword", "proper", "affix")
    }
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
            shapes[_shape(row.get("word", ""))] += 1
            by_shape[_shape(row.get("word", ""))][row.get("outcome", "?")] += 1
            if row.get("forms_drawn"):
                with_forms += 1
                if row.get("anchored"):
                    anchored += 1
                elif len(unanchored_examples) < 20:
                    unanchored_examples.append(
                        f"{row['word']}: {', '.join(row.get('unanchored', []))}"
                    )
    return {
        "surveyed": counted,
        "outcomes": dict(outcomes.most_common()),
        "terminals": dict(terminals.most_common()),
        "mean_steps": round(steps_total / counted, 2) if counted else 0.0,
        # Of the entries that drew anything at all, how many drew only forms
        # the source had actually written. This is the reliability figure: not
        # whether the etymologies are right — Wiktionary's business — but
        # whether the tool reported what the source says.
        "anchored": anchored,
        "with_forms": with_forms,
        "anchored_percent": round(100 * anchored / with_forms, 2) if with_forms else 0.0,
        "unanchored_examples": unanchored_examples,
        # What has actually been looked at. A figure quoted without this is a
        # statement about a slice dressed as a statement about the corpus:
        # phrases and proper nouns behave nothing like lemmas and were never
        # part of the population the audit was scoped to.
        "composition": dict(shapes.most_common()),
        "outcomes_for_lemmas": dict(by_shape["lemma"].most_common()),
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
    pending = sorted(
        (item for item in corpus if item.get("word") not in done),
        key=lambda item: _survey_order(item.get("word", "")),
    )

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
            f"**Anchored: {summary['anchored']} of {summary['with_forms']}** "
            f"({summary['anchored_percent']}%) — every form drawn was one the "
            "source had written. This is not a claim that the etymologies are "
            "right, which is Wiktionary's business; it is the claim that the "
            "tool reported what the source says.",
            "",
            "### What has been looked at",
            "",
            "Percentages below are of this composition, not of the corpus. "
            "Phrases (`a caldo`), proper nouns (`Acquappesa`) and affixes "
            "behave nothing like lemmas and were never in the population the "
            "audit is scoped to.",
            "",
            "| shape | count |",
            "|---|---:|",
            *(
                f"| `{name}` | {count} |"
                for name, count in summary["composition"].items()
            ),
            "",
            "### Outcomes for lemmas only",
            "",
            "| outcome | count |",
            "|---|---:|",
            *(
                f"| `{name}` | {count} |"
                for name, count in summary["outcomes_for_lemmas"].items()
            ),
            "",
            "### Outcomes across everything surveyed",
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
        if summary["unanchored_examples"]:
            lines += [
                "",
                "### Forms drawn that the source did not write",
                "",
                "Each of these is a defect: the tool put something in a tree "
                "that is not in the pages it read.",
                "",
                *(f"- `{example}`" for example in summary["unanchored_examples"]),
            ]
        args.summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
