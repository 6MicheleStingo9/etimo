#!/usr/bin/env python3
"""Daily validation harness for etimo against Wiktionary data.

Validates a deterministic batch of Wiktionary entries, records their state in a
persistent coverage ledger, enforces universal structural fidelity invariants alongside
case-specific expected facts, tracks corpus provenance, and outputs audit reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure project src is in sys.path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from etimo import __version__ as ETIMO_VERSION  # noqa: E402
from etimo.cache import DiskCache  # noqa: E402
from etimo.cache import default_path as default_cache_path  # noqa: E402
from etimo.languages import impossible_order  # noqa: E402
from etimo.models import Node, Relation, Terminal  # noqa: E402
from etimo.walker import DEFAULT_MAX_DEPTH, Reconstructor, Result  # noqa: E402
from etimo.wiktionary import (  # noqa: E402
    DictSource,
    SourceError,
    WikitextSource,
    WiktionaryClient,
)

DEFAULT_WORD_FILE = ROOT / "tools" / "validation" / "sample_words.json"
DEFAULT_QUEUE_FILE = ROOT / "tools" / "validation" / "coverage-ledger.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "wiktionary-validation"
DEFAULT_ARCHIVE_PASS_THRESHOLD = 3
DEFAULT_REVALIDATE_DAYS = 30

VALIDATION_STATUSES = {
    "pending",
    "priority",
    "retry",
    "manual_review",
    "pass",
    "fail",
    "blocked",
    "archived",
}

FAILURE_CLASSES = {
    "FIDELITY_INVARIANT_VIOLATION",
    "EXPECTED_FACT_MISSING",
    "SOURCE_LIMIT",
    "TRANSIENT_NETWORK_ERROR",
    "EXECUTION_EXCEPTION",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _compute_source_hash(source_text: str | None) -> str | None:
    if source_text is None:
        return None
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _classify_source_diagnostic(
    previous_hash: str | None,
    current_hash: str | None,
    failure_class: str | None,
) -> str | None:
    if failure_class is None:
        return None
    if previous_hash is None or current_hash is None:
        return None
    if current_hash == previous_hash:
        return "PARSER_REGRESSION"
    return "SOURCE_DRIFT"


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return f"sha256:{h.hexdigest()[:16]}"


def _load_word_list(path: Path) -> list[dict[str, Any]]:
    """Read a seed file or a corpus catalog into a list of cases.

    Both shapes are accepted because both exist: the hand-written seed keys
    its cases under `words`, the generated catalog under `items`. Reading only
    one of the two is how the builder and this script came to disagree about
    the file passing between them — the catalog loaded as **zero lemmas**, and
    the run reported a tidy audit of nothing at all.

    An empty corpus is therefore an error and not a result. Coverage of zero
    out of zero is 100% by arithmetic and meaningless by construction, and it
    is the sort of number that survives a long time before anybody doubts it.
    """
    if not path.exists():
        raise FileNotFoundError(f"word list not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(payload, dict):
        for key in ("words", "items", "cases"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            raise ValueError(
                f"{path} holds no case list: expected one of 'words', 'items' "
                f"or 'cases', found {sorted(payload)}"
            )

    if not isinstance(payload, list):
        raise ValueError(f"word list must be a list of records: {path}")
    if not payload:
        raise ValueError(f"{path} contains no cases; there is nothing to audit")
    _validate_expectations(payload)
    return payload


_KNOWN_RELATIONS = {r.name.lower() for r in Relation} | {
    r.label.lower() for r in Relation
}
_KNOWN_TERMINALS = {t.name.lower() for t in Terminal} | {
    t.label.lower() for t in Terminal
}
_EXPECTATION_FIELDS = {
    "must_include_relations": _KNOWN_RELATIONS,
    "must_not_include_relations": _KNOWN_RELATIONS,
    "must_include_terminals": _KNOWN_TERMINALS,
    "must_not_include_terminals": _KNOWN_TERMINALS,
}


def _validate_expectations(cases: list[dict[str, Any]]) -> None:
    """Reject expectations naming a relation or terminal that cannot exist.

    A misspelling behaves differently on either side, and the difference is
    the whole reason for this check. `must_include_relations: ["borowed"]`
    fails loudly and gets fixed within the minute. `must_not_include_relations:
    ["borowed"]` matches nothing, is never violated, and **passes forever** —
    an expectation that cannot fail, in a file no type checker reads.

    Checking the vocabulary at load time is what keeps a typo from quietly
    turning a case into decoration. Forms are not checked: they are lemmas in
    any language, not a closed set.
    """
    problems: list[str] = []
    for case in cases:
        expected = case.get("expected") or {}
        for field, vocabulary in _EXPECTATION_FIELDS.items():
            for name in expected.get(field, []):
                if str(name).strip().lower() not in vocabulary:
                    problems.append(
                        f"  {case.get('word', '?')}: {field} names "
                        f"'{name}', which is not a known value"
                    )
    if problems:
        raise ValueError(
            "the seed names relations or terminals that do not exist:\n"
            + "\n".join(problems)
            + "\n\nA name that cannot match makes a `must_not_include_*` "
            "expectation impossible to violate, so the case would pass "
            "whatever the tool did."
        )


def _default_status_for_case(case: dict[str, Any]) -> str:
    if case.get("manual_review"):
        return "manual_review"
    if case.get("status") in VALIDATION_STATUSES:
        return case["status"]
    category = case.get("category", "")
    priority_categories = {
        "compound",
        "multi-step",
        "uncertain-origin",
        "borrowed",
        "homograph",
    }
    if category in priority_categories:
        return "priority"
    return "pending"


def _default_priority_for_case(case: dict[str, Any]) -> int:
    category = case.get("category", "")
    priorities = {
        "borrowed": 90,
        "uncertain-origin": 95,
        "multi-step": 85,
        "compound": 80,
        "homograph": 80,
        "learned": 75,
        "general": 50,
        "standard": 50,
    }
    base = priorities.get(category, 50)
    return base + int(bool(case.get("manual_review")) * 25)


def _seed_queue(seed_file: Path) -> dict[str, Any]:
    cases = _load_word_list(seed_file)
    items: list[dict[str, Any]] = []
    for case in cases:
        word = case.get("word")
        if not word:
            continue
        item: dict[str, Any] = {
            "word": word,
            "language": case.get("language", "it"),
            "category": case.get("category", "general"),
            "status": _default_status_for_case(case),
            "priority": case.get("priority", _default_priority_for_case(case)),
            "attempts": 0,
            "consecutive_passes": 0,
            "first_seen": _utc_now_iso(),
            "last_validated": None,
            "next_due_at": None,
            "last_batch_id": None,
            "last_result": None,
            "last_failure_class": None,
            "source_hash": None,
            "diagnostic_class": None,
            "manual_review": bool(case.get("manual_review")),
            "manual_review_reason": case.get("manual_review_reason"),
            "expected": case.get("expected", {}),
        }
        if "sense" in case:
            item["sense"] = case["sense"]
        items.append(item)

    corpus_metadata = {
        "snapshot_id": f"corpus-{_utc_now().strftime('%Y%m%d')}",
        "dump_date": _utc_now().strftime("%Y-%m-%d"),
        "dataset_hash": _file_sha256(seed_file),
        "parser_version": ETIMO_VERSION,
        "total_corpus_lemmas": len(items),
        "seed_file": str(seed_file.name),
        "last_updated": _utc_now_iso(),
    }

    return {"corpus_metadata": corpus_metadata, "items": items}


def _load_ledger(queue_file: Path, seed_file: Path) -> dict[str, Any]:
    if not queue_file.exists():
        ledger = _seed_queue(seed_file)
        _save_ledger(queue_file, ledger)
        return ledger

    payload = json.loads(queue_file.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not items:
        ledger = _seed_queue(seed_file)
        _save_ledger(queue_file, ledger)
        return ledger

    # Sync any new words present in seed_file that are not in queue
    seed_cases = _load_word_list(seed_file)
    existing_keys = {
        (it.get("word"), it.get("language", "it"), it.get("sense")) for it in items
    }
    added = False
    for case in seed_cases:
        key = (case.get("word"), case.get("language", "it"), case.get("sense"))
        if key not in existing_keys and case.get("word"):
            items.append(
                {
                    "word": case["word"],
                    "language": case.get("language", "it"),
                    "category": case.get("category", "general"),
                    "status": _default_status_for_case(case),
                    "priority": case.get("priority", _default_priority_for_case(case)),
                    "attempts": 0,
                    "consecutive_passes": 0,
                    "first_seen": _utc_now_iso(),
                    "last_validated": None,
                    "next_due_at": None,
                    "last_batch_id": None,
                    "last_result": None,
                    "last_failure_class": None,
                    "source_hash": None,
                    "diagnostic_class": None,
                    "manual_review": bool(case.get("manual_review")),
                    "manual_review_reason": case.get("manual_review_reason"),
                    "expected": case.get("expected", {}),
                    **({"sense": case["sense"]} if "sense" in case else {}),
                }
            )
            existing_keys.add(key)
            added = True

    corpus_meta = payload.get("corpus_metadata", {})
    corpus_meta["total_corpus_lemmas"] = len(items)
    corpus_meta["dataset_hash"] = _file_sha256(seed_file)
    corpus_meta["parser_version"] = ETIMO_VERSION
    payload["corpus_metadata"] = corpus_meta
    payload["items"] = items

    if added:
        _save_ledger(queue_file, payload)

    return payload


def _save_ledger(queue_file: Path, ledger: dict[str, Any]) -> None:
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    ledger["corpus_metadata"]["last_updated"] = _utc_now_iso()
    queue_file.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _invalidate_ledger(
    ledger: dict[str, Any],
    category: str | None = None,
    invalidate_all: bool = False,
) -> int:
    """Force re-audit of items by resetting their status to priority."""
    count = 0
    for item in ledger.get("items", []):
        if invalidate_all or (category and item.get("category") == category):
            item["status"] = "priority"
            item["priority"] = max(80, int(item.get("priority", 50)) + 15)
            item["consecutive_passes"] = 0
            item["next_due_at"] = None
            count += 1
    return count


def _queue_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    status_rank = {
        "priority": 0,
        "retry": 1,
        "pending": 2,
        "manual_review": 3,
        "fail": 4,
        "pass": 5,
        "blocked": 6,
        "archived": 7,
    }
    last_validated = item.get("last_validated") or "1970-01-01T00:00:00+00:00"
    return (
        status_rank.get(item.get("status"), 99),
        -int(item.get("priority", 0)),
        last_validated,
        item.get("word", ""),
    )


def _allocate_batch_targets(batch_size: int) -> dict[str, int]:
    weights = {
        "new": 0.40,
        "retry": 0.30,
        "manual_review": 0.15,
        "recheck": 0.15,
    }
    raw_targets = {name: batch_size * weight for name, weight in weights.items()}
    targets = {name: int(value) for name, value in raw_targets.items()}
    remaining = batch_size - sum(targets.values())
    if remaining > 0:
        ordered = sorted(
            weights,
            key=lambda name: (raw_targets[name] - targets[name], -weights[name]),
            reverse=True,
        )
        for name in ordered[:remaining]:
            targets[name] += 1
    return targets


def _diverse_pool_pick(pool: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not pool:
        return []

    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in pool:
        category = item.get("category", "general")
        by_category.setdefault(category, []).append(item)

    for cat_items in by_category.values():
        cat_items.sort(key=_queue_sort_key)

    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, str, Any]] = set()

    while len(selected) < min(limit, len(pool)):
        picked_this_round = False
        for cat_items in by_category.values():
            if not cat_items:
                continue
            item = cat_items.pop(0)
            key = (
                item.get("word", ""),
                item.get("language", "it"),
                item.get("sense"),
            )
            if key in selected_keys:
                continue
            selected.append(item)
            selected_keys.add(key)
            picked_this_round = True
            if len(selected) >= min(limit, len(pool)):
                break
        if not picked_this_round:
            break

    return selected


def _select_batch(queue: list[dict[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    """Choose a deterministic daily batch, by quota over new/retry/review/recheck."""
    if batch_size <= 0 or not queue:
        return []

    now_iso = _utc_now_iso()
    for item in queue:
        if item.get("status") == "archived":
            due = item.get("next_due_at")
            if due and due <= now_iso:
                item["status"] = "pending"

    targets = _allocate_batch_targets(batch_size)
    # Each pool is defined by the status it wants. The `and status != "blocked"`
    # that used to trail every one of these could not ever be false — a status
    # equal to "retry" is not "blocked" — so it filtered nothing while reading
    # as though it did. Blocked items are excluded because no pool asks for
    # them, which is worth stating once here rather than mis-stating four times.
    groups = {
        "new": [
            item for item in queue
            if item.get("status") in {"priority", "pending"}
        ],
        "retry": [item for item in queue if item.get("status") == "retry"],
        "manual_review": [
            item for item in queue if item.get("status") == "manual_review"
        ],
        "recheck": [
            item
            for item in queue
            if item.get("status") == "archived"
            and item.get("next_due_at")
            and item.get("next_due_at") <= now_iso
        ],
    }
    for pool in groups.values():
        pool.sort(key=_queue_sort_key)

    non_empty_groups = [name for name, pool in groups.items() if pool]
    selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, str, Any]] = set()

    for group_name in ("new", "retry", "manual_review", "recheck"):
        pool = groups.get(group_name, [])
        if not pool:
            continue
        if len(non_empty_groups) == 1:
            limit = min(batch_size, len(pool))
        else:
            limit = min(targets.get(group_name, 0), len(pool))
        for item in _diverse_pool_pick(pool, limit):
            key = (
                item.get("word", ""),
                item.get("language", "it"),
                item.get("sense"),
            )
            if key not in selected_keys:
                selected.append(item)
                selected_keys.add(key)

    if len(selected) < batch_size:
        fallback = sorted(
            (
                item
                for item in queue
                if item.get("status") not in {"blocked", "pass", "fail", "archived"}
                and item.get("word")
            ),
            key=_queue_sort_key,
        )
        for item in fallback:
            if len(selected) >= batch_size:
                break
            key = (
                item.get("word", ""),
                item.get("language", "it"),
                item.get("sense"),
            )
            if key not in selected_keys:
                selected.append(item)
                selected_keys.add(key)

    return selected[:batch_size]


# --- Invariant & Structure Extraction ---


def _every_node(node: Node):
    yield node
    for child in node.children:
        yield from _every_node(child)


def _extract_tree_facts(root: Node) -> dict[str, Any]:
    forms: set[str] = set()
    bare_forms: set[str] = set()
    relations: set[str] = set()
    terminals: set[str] = set()
    hypotheses: set[str] = set()
    chains: list[list[str]] = []

    def _walk_chains(current: Node, current_chain: list[str]):
        lemma_key = (
            f"{current.form.lemma}::{current.form.language}" if current.form.lemma else ""
        )
        new_chain = [*current_chain, lemma_key] if lemma_key else current_chain
        if not current.children:
            chains.append(new_chain)
        else:
            for child in current.children:
                _walk_chains(child, new_chain)

    _walk_chains(root, [])

    for node in _every_node(root):
        if node.form.lemma:
            forms.add(f"{node.form.lemma}::{node.form.language}")
            bare_forms.add(node.form.lemma)
        if node.relation:
            relations.add(node.relation.label)
            relations.add(node.relation.name.lower())
        if node.terminal is not None:
            terminals.add(node.terminal.name.lower())
            terminals.add(node.terminal.label.lower())
        for hyp in node.hypotheses:
            if hyp.form.lemma:
                hypotheses.add(hyp.form.lemma)
                hypotheses.add(f"{hyp.form.lemma}::{hyp.form.language}")

    return {
        "forms": forms,
        "bare_forms": bare_forms,
        "relations": relations,
        "terminals": terminals,
        "hypotheses": hypotheses,
        "chains": chains,
    }


def _verify_fidelity_invariants(root: Node) -> list[str]:
    """Universal structural fidelity checks (from test_fidelity_checks.py)."""
    violations: list[str] = []

    for node in _every_node(root):
        lemma = node.form.lemma or ""

        # I1: No markup in lemmas (<t:...>, [[...]], ::, etc.)
        if re.search(r"[<>]|\[\[|\]\]|::", lemma):
            violations.append(f"I1 markup corruption in lemma: «{lemma}»")

        # I2: No un-split language prefix in lemma (e.g. pgd:lemma)
        if ":" in lemma:
            violations.append(f"I2 language prefix not split in lemma: «{lemma}»")

        # I3: Chronological order sanity
        for child in node.children:
            if impossible_order(child.form.language, node.form.language):
                violations.append(
                    f"I3 impossible chronological link: {child.form.language} "
                    f"«{child.form.lemma}» ancestor of {node.form.language} «{lemma}»"
                )

        # I5: Linguistic terminal must rest on an attested, non-empty form
        if node.terminal is not None and node.terminal.is_linguistic and not lemma:
            violations.append(
                f"I5 linguistic terminal '{node.terminal.name}' on empty form"
            )

        # I6: Hypotheses integrity
        for h in node.hypotheses:
            if not h.form.lemma:
                violations.append("I6 hypothesis with empty lemma")
            elif re.search(r"[<>]|\[\[|\]\]", h.form.lemma):
                violations.append(f"I6 markup in hypothesis lemma: «{h.form.lemma}»")

    # I4: No cycles disguised as branches (no repeated form on any branch)
    def _check_branch_cycles(node: Node, seen: tuple[str, ...]):
        key = node.form.key
        if key in seen:
            violations.append(
                f"I4 form «{node.form.lemma}» ({node.form.language}) repeated in branch"
            )
        for child in node.children:
            _check_branch_cycles(child, (*seen, key))

    _check_branch_cycles(root, ())

    return violations


def _named(candidate: str, present: set[str]) -> bool:
    """Whether a name the seed uses matches one the tree recorded.

    Both spellings of every relation and terminal are collected — the enum
    name and the human label — so a seed may write `uncertain_origin` or
    `uncertain origin` and mean the same thing. Matching is on equality
    against that set, never on substring.

    Substring matching was the original rule for required facts, while
    forbidden facts were compared by equality. That asymmetry ran in the
    direction that acquits: `must_include: ["borrowed"]` was satisfied by
    `unadapted borrowing`, while `must_not_include: ["borrowed"]` was not
    violated by it. A required fact was easier to satisfy than a forbidden one
    was to breach, so the seed asserted less than it appeared to — and the
    weakening was invisible, because a passing test looks the same either way.
    """
    return candidate.strip().lower() in present


def _check_expected_facts(facts: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Check case-specific expectations against extracted tree facts."""
    failures: list[str] = []
    relations = {r.lower() for r in facts["relations"]}
    terminals = {t.lower() for t in facts["terminals"]}

    # Relations
    req_relations = expected.get("must_include_relations", [])
    for rel in req_relations:
        if not _named(str(rel), relations):
            failures.append(f"missing required relation: '{rel}'")

    # Terminals
    req_terminals = expected.get("must_include_terminals", [])
    for term in req_terminals:
        if not _named(str(term), terminals):
            failures.append(f"missing required terminal: '{term}'")

    # Forms
    req_forms = expected.get("must_include_forms", [])
    for form in req_forms:
        if "::" in form:
            if form not in facts["forms"]:
                failures.append(f"missing required form (exact lang): '{form}'")
        elif form not in facts["bare_forms"]:
            failures.append(f"missing required form: '{form}'")

    # Hypotheses
    req_hypotheses = expected.get("must_include_hypotheses", [])
    for hyp in req_hypotheses:
        if "::" in hyp:
            if hyp not in facts["hypotheses"]:
                failures.append(f"missing required hypothesis (exact lang): '{hyp}'")
        else:
            hyp_bare = {h.split("::")[0] for h in facts["hypotheses"]}
            if hyp not in facts["hypotheses"] and hyp not in hyp_bare:
                failures.append(f"missing required hypothesis: '{hyp}'")

    # Chains (sub-path match)
    req_chains = expected.get("must_include_chains", [])
    for req_chain in req_chains:
        matched = False
        for tree_chain in facts["chains"]:
            n_req = len(req_chain)
            for i in range(len(tree_chain) - n_req + 1):
                sub = tree_chain[i : i + n_req]
                if all(
                    r == s or ("::" not in r and r == s.split("::")[0])
                    for r, s in zip(req_chain, sub, strict=False)
                ):
                    matched = True
                    break
            if matched:
                break
        if not matched:
            failures.append(f"missing required lineage chain: {req_chain}")

    # Slot-specific prohibitions. A form the source only proposes must appear
    # among the hypotheses *and* be absent from the chain, and it takes both
    # halves to say so: `must_include_hypotheses` alone passes even when the
    # tool has drawn the conjecture as an ancestor, which is the exact error
    # these cases exist to catch. An expectation that cannot fail on the
    # defect it targets is the `assert … or True` of two days ago, written as
    # data instead of code.
    for form in expected.get("must_not_include_forms", []):
        if form in facts["forms"] or form in facts["bare_forms"]:
            failures.append(f"form drawn in the chain but must not be: '{form}'")
    for rel in expected.get("must_not_include_relations", []):
        if _named(str(rel), relations):
            failures.append(f"relation present but must not be: '{rel}'")
    for term in expected.get("must_not_include_terminals", []):
        if _named(str(term), terminals):
            failures.append(f"terminal present but must not be: '{term}'")

    # Forbidden items (must_not_include)
    forbidden = expected.get("must_not_include")
    if forbidden:
        if isinstance(forbidden, list):
            forbidden_items = forbidden
        elif isinstance(forbidden, dict):
            forbidden_items = (
                forbidden.get("relations", [])
                + forbidden.get("forms", [])
                + forbidden.get("terminals", [])
            )
        else:
            forbidden_items = [forbidden]

        for item in forbidden_items:
            if _named(str(item), relations):
                failures.append(f"forbidden relation found: '{item}'")
            if any(item == f or item == f.split("::")[0] for f in facts["forms"]):
                failures.append(f"forbidden form found: '{item}'")
            if _named(str(item), terminals):
                failures.append(f"forbidden terminal found: '{item}'")

    return failures


# --- Case Runner & Reporting ---


def _classify_failure(
    fidelity_violations: list[str],
    expectation_failures: list[str],
    starved: bool,
    error: Exception | None,
) -> str | None:
    """Name the cause, choosing the one that tells the reader something.

    `starved` means the *starting* entry yielded nothing — no page, no
    language section, no etymology — so there was never anything to read and
    every expectation fails as a consequence. That is a fact about the source.

    A limit reached higher up the tree is not. `albicocca` is read fine, walks
    several steps, and ends a branch on a missing page; when its expectations
    also fail, the informative answer is *which* expectation, not that some
    ancestor lacked an entry. Classifying on any source limit anywhere put
    every such case under SOURCE_LIMIT and hid the real reason underneath a
    true but useless statement.
    """
    if error is not None:
        if isinstance(error, SourceError):
            return "TRANSIENT_NETWORK_ERROR"
        return "EXECUTION_EXCEPTION"
    if fidelity_violations:
        return "FIDELITY_INVARIANT_VIOLATION"
    if starved:
        return "SOURCE_LIMIT"
    if expectation_failures:
        return "EXPECTED_FACT_MISSING"
    return None


def _run_single_case(
    case: dict[str, Any],
    source: WikitextSource,
    max_depth: int = DEFAULT_MAX_DEPTH,
    batch_id: str | None = None,
) -> dict[str, Any]:
    word = case["word"]
    language = case.get("language", "it")
    sense = case.get("sense")
    category = case.get("category", "general")
    expected = case.get("expected", {})
    previous_source_hash = case.get("source_hash")

    raw_source = None
    try:
        raw_source = source.wikitext(word) if hasattr(source, "wikitext") else None
    except Exception:
        raw_source = None
    current_source_hash = _compute_source_hash(raw_source)

    reconstructor = Reconstructor(source, max_depth=max_depth)
    error_obj: Exception | None = None
    result: Result | None = None

    start_time = time.perf_counter()
    try:
        sense_kw = {"sense": int(sense)} if sense is not None else {}
        result = reconstructor.reconstruct(word, language=language, **sense_kw)
    except Exception as exc:
        error_obj = exc

    elapsed_s = round(time.perf_counter() - start_time, 3)

    if result is None or error_obj is not None:
        fail_class = _classify_failure([], [], False, error_obj)
        error_msg = f"{type(error_obj).__name__}: {error_obj}"
        source_diagnostic = _classify_source_diagnostic(
            previous_source_hash, current_source_hash, fail_class
        )
        return {
            "word": word,
            "language": language,
            "sense": sense,
            "category": category,
            "status": "fail",
            "batch_id": batch_id,
            "elapsed_seconds": elapsed_s,
            "expected": expected,
            "failure_class": fail_class,
            "source_hash": current_source_hash,
            "diagnostic_class": source_diagnostic,
            "reasons": [f"Execution failed: {error_msg}"],
            "error": error_msg,
            "fidelity_violations": [],
        }

    # Extract facts & evaluate invariants
    fidelity_violations = _verify_fidelity_invariants(result.start)
    facts = _extract_tree_facts(result.start)
    expectation_failures = _check_expected_facts(facts, expected)

    # Only the starting entry can starve the run: a limit further up means the
    # walk did read something and got somewhere.
    root_terminal = result.start.terminal
    starved = (
        not result.start.children
        and root_terminal is not None
        and root_terminal.name.lower()
        in {"etymology_missing", "entry_missing", "language_missing"}
    )
    fail_class = _classify_failure(
        fidelity_violations, expectation_failures, starved, None
    )

    all_failures = fidelity_violations + expectation_failures
    is_ok = len(all_failures) == 0
    source_diagnostic = _classify_source_diagnostic(
        previous_source_hash, current_source_hash, fail_class
    )

    if case.get("manual_review"):
        status = "manual_review"
    elif is_ok:
        status = "pass"
    else:
        status = "fail"

    payload: dict[str, Any] = {
        "word": word,
        "language": language,
        "sense": sense,
        "category": category,
        "status": status,
        "batch_id": batch_id,
        "elapsed_seconds": elapsed_s,
        "expected": expected,
        "failure_class": fail_class if not is_ok else None,
        "source_hash": current_source_hash,
        "diagnostic_class": source_diagnostic,
        "reasons": all_failures,
        "fidelity_violations": fidelity_violations,
        "actual_summary": {
            "steps": result.steps,
            "chosen_etymology": result.chosen_sense,
            "available_etymologies": result.available_senses,
            "network_requests": result.requests,
            "cache_hits": result.cache_hits,
            "terminals": sorted(facts["terminals"]),
            "forms_count": len(facts["forms"]),
        },
    }
    return payload


def _item_backlog_age_days(item: dict[str, Any], now: datetime | None = None) -> int:
    now = now or _utc_now()
    anchor = item.get("first_seen") or item.get("last_validated") or _utc_now_iso()
    try:
        anchor_dt = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
    except ValueError:
        return 0
    delta = now - anchor_dt
    return max(0, int(delta.total_seconds() // 86400))


def _coverage_summary(queue: list[dict[str, Any]]) -> dict[str, Any]:
    summary = dict.fromkeys(sorted(VALIDATION_STATUSES), 0)
    category_summary: dict[str, dict[str, int]] = {}
    failure_classes: dict[str, int] = dict.fromkeys(sorted(FAILURE_CLASSES), 0)
    backlog_ages: list[int] = []

    for item in queue:
        status_key = item.get("status", "pending")
        summary[status_key] = summary.get(status_key, 0) + 1

        cat = item.get("category", "general")
        cat_stats = category_summary.setdefault(
            cat, {"total": 0, "pass": 0, "fail": 0, "manual_review": 0, "archived": 0}
        )
        cat_stats["total"] += 1
        if status_key in cat_stats:
            cat_stats[status_key] += 1

        f_class = item.get("last_failure_class")
        if f_class and f_class in failure_classes:
            failure_classes[f_class] += 1

        if status_key in {"pending", "priority", "retry", "manual_review", "fail"}:
            backlog_ages.append(_item_backlog_age_days(item))

    total_items = len(queue)
    covered_items = summary.get("pass", 0) + summary.get("archived", 0)
    coverage_pct = round((covered_items / max(1, total_items)) * 100, 1)

    backlog_avg = round(sum(backlog_ages) / len(backlog_ages), 1) if backlog_ages else 0.0
    backlog_max = max(backlog_ages, default=0)

    return {
        "statuses": summary,
        "categories": category_summary,
        "failure_classes": failure_classes,
        "total_corpus_lemmas": total_items,
        "covered_corpus_lemmas": covered_items,
        "corpus_coverage_percent": coverage_pct,
        "backlog_age_days": {"avg": backlog_avg, "max": backlog_max},
    }


def _build_report(
    processed: list[dict[str, Any]],
    ledger: dict[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    totals = {
        "pass": 0,
        "fail": 0,
        "manual_review": 0,
        "retry": 0,
        "priority": 0,
        "pending": 0,
    }
    for case in processed:
        st = case["status"]
        totals[st] = totals.get(st, 0) + 1

    queue = ledger.get("items", [])
    cov = _coverage_summary(queue)

    return {
        "generated_by": "tools.validate_wiktionary",
        "batch_id": batch_id,
        "timestamp": _utc_now_iso(),
        "corpus_metadata": ledger.get("corpus_metadata", {}),
        "total_cases_processed": len(processed),
        "batch_totals": totals,
        "corpus_coverage": cov,
        "cases": processed,
    }


def _generate_markdown_summary(report: dict[str, Any]) -> str:
    batch_totals = report.get("batch_totals", {})
    cov = report.get("corpus_coverage", {})
    statuses = cov.get("statuses", {})
    categories = cov.get("categories", {})
    meta = report.get("corpus_metadata", {})
    tot_batch = report.get("total_cases_processed", 0)
    cov_pct = cov.get("corpus_coverage_percent", 0.0)

    cov_lemmas = cov.get("covered_corpus_lemmas")
    tot_lemmas = cov.get("total_corpus_lemmas")
    cov_count_str = f"({cov_lemmas}/{tot_lemmas} lemmas)"
    pr_count = statuses.get("priority", 0) + statuses.get("retry", 0)
    lines = [
        "## 🔍 Wiktionary Daily Audit & Corpus Coverage Summary",
        "",
        (
            f"**Batch ID**: `{report.get('batch_id')}` | "
            f"**Corpus Snapshot**: `{meta.get('snapshot_id', 'n/a')}` | "
            f"**Parser Version**: `v{meta.get('parser_version', '0.1.0')}`"
        ),
        (
            f"**Timestamp**: `{report.get('timestamp')}` | "
            f"**Corpus Coverage**: `{cov_pct}%` {cov_count_str}"
        ),
        "",
        "### 📊 Batch Execution Results",
        "| Pass | Fail | Manual Review | Total Processed |",
        "|:---:|:---:|:---:|:---:|",
        (
            f"| ✅ {batch_totals.get('pass', 0)} "
            f"| ❌ {batch_totals.get('fail', 0)} "
            f"| ⚠️ {batch_totals.get('manual_review', 0)} "
            f"| 📦 {tot_batch} |"
        ),
        "",
        "### 📈 Corpus Queue State",
        "| State | Count | State | Count |",
        "|---|---|---|---|",
        (
            f"| **Pass / Active** | `{statuses.get('pass', 0)}` "
            f"| **Archived (Stable)** | `{statuses.get('archived', 0)}` |"
        ),
        (
            f"| **Pending** | `{statuses.get('pending', 0)}` | "
            f"**Priority / Retry** | `{pr_count}` |"
        ),
        (
            f"| **Manual Review** | `{statuses.get('manual_review', 0)}` "
            f"| **Blocked** | `{statuses.get('blocked', 0)}` |"
        ),
        "",
        "### 🏷️ Coverage by Category",
        "| Category | Total | Pass/Archived | Pass Rate |",
        "|---|---|---|---|",
    ]

    for cat_name, cat_data in sorted(categories.items()):
        c_tot = cat_data.get("total", 0)
        c_ok = cat_data.get("pass", 0) + cat_data.get("archived", 0)
        c_rate = round((c_ok / max(1, c_tot)) * 100, 1)
        lines.append(f"| `{cat_name}` | `{c_tot}` | `{c_ok}` | **{c_rate}%** |")

    failed_cases = [c for c in report.get("cases", []) if c["status"] == "fail"]
    if failed_cases:
        lines.append("")
        lines.append("### ❌ Failures in this Batch")
        lines.append("| Word | Class | Category | Failure Reasons |")
        lines.append("|---|---|---|---|")
        for f in failed_cases:
            reasons_str = "<br>".join(f.get("reasons", [])[:2])
            f_class = f.get("failure_class", "UNKNOWN")
            lines.append(
                f"| **{f['word']}** | `{f_class}` | `{f['category']}` | {reasons_str} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a deterministic batch of Wiktionary words."
    )
    parser.add_argument(
        "--seed-file",
        type=Path,
        default=DEFAULT_WORD_FILE,
        help="Path to the seed validation cases.",
    )
    parser.add_argument(
        "--queue-file",
        type=Path,
        default=DEFAULT_QUEUE_FILE,
        help="Coverage queue ledger file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Maximum number of cases to process in this run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Folder used to store the validation report JSON.",
    )
    parser.add_argument(
        "--rate-limit-delay",
        type=float,
        default=0.05,
        help="Delay in seconds between requests to avoid rate limits.",
    )
    parser.add_argument(
        "--offline-fixtures",
        type=Path,
        default=None,
        help="Optional path to offline entries JSON fixture (skips network).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Custom disk cache directory.",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=None,
        help="Optional path to write a Markdown summary.",
    )
    parser.add_argument(
        "--invalidate-category",
        type=str,
        default=None,
        help="Force re-validation of a specific category in the ledger.",
    )
    parser.add_argument(
        "--invalidate-all",
        action="store_true",
        help="Force re-validation of all corpus lemmas in the ledger.",
    )
    args = parser.parse_args()

    ledger = _load_ledger(args.queue_file, args.seed_file)

    # Handle invalidation triggers if requested
    if args.invalidate_all or args.invalidate_category:
        count = _invalidate_ledger(
            ledger,
            category=args.invalidate_category,
            invalidate_all=args.invalidate_all,
        )
        _save_ledger(args.queue_file, ledger)
        print(f"Invalidated {count} items in ledger for re-audit.")
        return 0

    batch_id = f"audit-{_utc_now().strftime('%Y%m%d-%H%M%S')}"
    queue = ledger.get("items", [])
    batch = _select_batch(queue, args.batch_size)

    # Initialize source.
    #
    # `DiskCache` wraps a source rather than taking a path: the network client
    # goes inside it, not beside it. Getting this backwards raised a TypeError
    # on the first line of every networked run, which no test caught because
    # the harness only ever exercised `--offline-fixtures`. The same two lines
    # exist in `cli.py`; if a third copy is ever needed, they belong in one
    # place instead.
    if args.offline_fixtures and args.offline_fixtures.exists():
        fixtures_data = json.loads(args.offline_fixtures.read_text(encoding="utf-8"))
        source: WikitextSource = DictSource(fixtures_data)
    else:
        cache_path = args.cache_dir or default_cache_path()
        source = DiskCache(WiktionaryClient(), path=cache_path)

    processed: list[dict[str, Any]] = []
    for item in batch:
        word = item.get("word")
        if not word:
            continue

        if args.rate_limit_delay > 0 and not isinstance(source, DictSource):
            time.sleep(args.rate_limit_delay)

        summary = _run_single_case(item, source, batch_id=batch_id)
        processed.append(summary)

        # Update ledger item metadata and lifecycle
        previous_hash = item.get("source_hash")
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["last_validated"] = _utc_now_iso()
        item["last_batch_id"] = batch_id
        item["last_result"] = summary["status"]
        item["last_failure_class"] = summary.get("failure_class")
        item["source_hash"] = summary.get("source_hash")
        item["diagnostic_class"] = _classify_source_diagnostic(
            previous_hash,
            summary.get("source_hash"),
            summary.get("failure_class"),
        )

        if item.get("manual_review"):
            item["status"] = "manual_review"
        elif summary["status"] == "pass":
            passes = int(item.get("consecutive_passes", 0)) + 1
            item["consecutive_passes"] = passes
            if passes >= DEFAULT_ARCHIVE_PASS_THRESHOLD:
                item["status"] = "archived"
                due_dt = _utc_now() + timedelta(days=DEFAULT_REVALIDATE_DAYS)
                item["next_due_at"] = due_dt.isoformat()
            else:
                item["status"] = "pass"
                item["priority"] = max(1, int(item.get("priority", 50)) - 5)
        else:
            item["consecutive_passes"] = 0
            item["next_due_at"] = None
            if summary.get("failure_class") == "TRANSIENT_NETWORK_ERROR":
                # Do not penalize priority for temporary network hiccups
                item["status"] = "retry"
            else:
                item["status"] = "retry"
                item["priority"] = min(200, int(item.get("priority", 50)) + 10)

    _save_ledger(args.queue_file, ledger)

    report = _build_report(processed, ledger, batch_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "daily-wiktionary-audit.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_summary = _generate_markdown_summary(report)
    if args.summary_md:
        args.summary_md.parent.mkdir(parents=True, exist_ok=True)
        args.summary_md.write_text(md_summary, encoding="utf-8")

    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "total_cases_processed": report["total_cases_processed"],
                "batch_totals": report["batch_totals"],
                "corpus_coverage": report["corpus_coverage"],
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
