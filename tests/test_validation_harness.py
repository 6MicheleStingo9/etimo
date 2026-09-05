"""Tests for tools/validate_wiktionary.py validation harness."""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etimo.models import Form, Node, Relation  # noqa: E402
from etimo.wiktionary import DictSource, SourceError  # noqa: E402
from tools.validate_wiktionary import (  # noqa: E402
    _alarming,
    _check_expected_facts,
    _classify_failure,
    _classify_source_diagnostic,
    _coverage_summary,
    _generate_markdown_summary,
    _invalidate_ledger,
    _load_ledger,
    _load_word_list,
    _run_single_case,
    _select_batch,
    _utc_now,
    _verify_fidelity_invariants,
)

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "entries.json"
ENTRIES = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def test_seed_and_load_ledger(tmp_path: Path):
    seed_file = tmp_path / "sample.json"
    queue_file = tmp_path / "ledger.json"

    seed_file.write_text(
        json.dumps(
            [
                {"word": "fuoco", "category": "uncertain-origin", "manual_review": False},
                {
                    "word": "riso",
                    "sense": 1,
                    "category": "homograph",
                    "manual_review": False,
                },
                {"word": "allogliato", "category": "compound", "manual_review": True},
            ]
        ),
        encoding="utf-8",
    )

    ledger = _load_ledger(queue_file, seed_file)
    assert "corpus_metadata" in ledger
    assert ledger["corpus_metadata"]["total_corpus_lemmas"] == 3
    items = ledger["items"]
    assert len(items) == 3
    assert queue_file.exists()

    # Verify initial priorities & statuses
    fuoco = next(it for it in items if it["word"] == "fuoco")
    assert fuoco["status"] == "priority"
    assert fuoco["priority"] == 95
    assert fuoco["consecutive_passes"] == 0

    riso = next(it for it in items if it["word"] == "riso")
    assert riso["sense"] == 1
    assert riso["status"] == "priority"

    allogliato = next(it for it in items if it["word"] == "allogliato")
    assert allogliato["status"] == "manual_review"
    assert allogliato["priority"] == 80 + 25


def test_select_batch_stratification():
    queue = [
        {
            "word": "alpha",
            "category": "standard",
            "status": "priority",
            "priority": 90,
            "last_validated": None,
        },
        {
            "word": "beta",
            "category": "standard",
            "status": "priority",
            "priority": 85,
            "last_validated": None,
        },
        {
            "word": "gamma",
            "category": "borrowed",
            "status": "priority",
            "priority": 80,
            "last_validated": None,
        },
        {
            "word": "delta",
            "category": "compound",
            "status": "priority",
            "priority": 75,
            "last_validated": None,
        },
    ]

    batch = _select_batch(queue, batch_size=3)
    # Stratified selection should pick from diverse categories:
    batch_cats = {b["category"] for b in batch}
    assert len(batch_cats) == 3
    assert "standard" in batch_cats
    assert "borrowed" in batch_cats
    assert "compound" in batch_cats


def test_fidelity_invariant_i1_markup_detected():
    corrupted_node = Node(
        form=Form(lemma="*h₂el-<t:to grow>", language="ine-pro"),
        relation=Relation.DERIVED,
    )
    violations = _verify_fidelity_invariants(corrupted_node)
    assert any("I1 markup corruption" in v for v in violations)


def test_fidelity_invariant_i2_language_prefix_detected():
    corrupted_node = Node(
        form=Form(lemma="pgd:𐨭𐨐𐨪", language="pgd"),
        relation=Relation.DERIVED,
    )
    violations = _verify_fidelity_invariants(corrupted_node)
    assert any("I2 language prefix" in v for v in violations)


def test_fidelity_invariant_i3_impossible_chronology_detected():
    parent_node = Node(form=Form(lemma="caulis", language="la-lat"))
    child_node = Node(
        form=Form(lemma="cavolo", language="nap"), relation=Relation.DERIVED
    )
    parent_node.children.append(child_node)

    violations = _verify_fidelity_invariants(parent_node)
    assert any("I3 impossible chronological link" in v for v in violations)


def test_fidelity_invariant_i4_cycle_in_branch_detected():
    root = Node(form=Form(lemma="pizza", language="it"))
    mid = Node(form=Form(lemma="πίτα", language="gkm"), relation=Relation.DERIVED)
    cycle = Node(form=Form(lemma="pizza", language="it"), relation=Relation.DERIVED)
    root.children.append(mid)
    mid.children.append(cycle)

    violations = _verify_fidelity_invariants(root)
    assert any("I4 form" in v and "repeated in branch" in v for v in violations)


def test_failure_classification():
    # Invariant violation
    c1 = _classify_failure(["I1 markup error"], [], False, None)
    assert c1 == "FIDELITY_INVARIANT_VIOLATION"

    # Expected fact missing
    c2 = _classify_failure([], ["missing form: foo"], False, None)
    assert c2 == "EXPECTED_FACT_MISSING"

    # Source limit
    c3 = _classify_failure([], ["missing form: foo"], True, None)
    assert c3 == "SOURCE_LIMIT"

    # Network transient
    c4 = _classify_failure([], [], False, SourceError("503 timeout"))
    assert c4 == "TRANSIENT_NETWORK_ERROR"

    # Generic execution exception
    c5 = _classify_failure([], [], False, ValueError("invalid syntax"))
    assert c5 == "EXECUTION_EXCEPTION"


def test_invalidation_logic():
    ledger = {
        "corpus_metadata": {},
        "items": [
            {
                "word": "cane",
                "category": "standard",
                "status": "pass",
                "consecutive_passes": 3,
            },
            {
                "word": "caffè",
                "category": "borrowed",
                "status": "pass",
                "consecutive_passes": 2,
            },
            {
                "word": "girasole",
                "category": "compound",
                "status": "archived",
                "consecutive_passes": 4,
            },
        ],
    }

    # Invalidate only compound
    count = _invalidate_ledger(ledger, category="compound")
    assert count == 1
    assert ledger["items"][2]["status"] == "priority"
    assert ledger["items"][2]["consecutive_passes"] == 0
    assert ledger["items"][0]["status"] == "pass"

    # Invalidate all
    count_all = _invalidate_ledger(ledger, invalidate_all=True)
    assert count_all == 3
    assert all(it["status"] == "priority" for it in ledger["items"])


def test_coverage_summary_computation():
    queue = [
        {"word": "a", "category": "standard", "status": "pass"},
        {"word": "b", "category": "standard", "status": "archived"},
        {
            "word": "c",
            "category": "borrowed",
            "status": "retry",
            "last_failure_class": "EXPECTED_FACT_MISSING",
        },
        {"word": "d", "category": "compound", "status": "pending"},
    ]
    cov = _coverage_summary(queue)
    assert cov["total_corpus_lemmas"] == 4
    assert cov["covered_corpus_lemmas"] == 2
    assert cov["corpus_coverage_percent"] == 50.0
    assert cov["categories"]["standard"]["pass"] == 1
    assert cov["categories"]["standard"]["archived"] == 1
    assert cov["failure_classes"]["EXPECTED_FACT_MISSING"] == 1


def test_run_single_case_with_frozen_dict_source():
    source = DictSource(ENTRIES)
    case = {
        "word": "cavolo",
        "language": "it",
        "category": "uncertain-origin",
        "expected": {
            "must_include_forms": ["caulis::la"],
        },
    }
    result = _run_single_case(case, source, batch_id="test-batch-01")
    assert result["status"] == "pass"
    assert result["reasons"] == []
    assert result["fidelity_violations"] == []
    assert result["batch_id"] == "test-batch-01"
    assert result["actual_summary"]["forms_count"] > 1


def test_markdown_summary_generation():
    report = {
        "batch_id": "audit-20260816-01",
        "timestamp": "2026-08-16T12:00:00+00:00",
        "total_cases_processed": 2,
        "corpus_metadata": {
            "snapshot_id": "corpus-20260816",
            "parser_version": "0.1.0",
        },
        "batch_totals": {
            "pass": 1,
            "fail": 1,
            "manual_review": 0,
            "retry": 0,
            "priority": 0,
            "pending": 0,
        },
        "corpus_coverage": {
            "total_corpus_lemmas": 10,
            "covered_corpus_lemmas": 5,
            "corpus_coverage_percent": 50.0,
            "statuses": {
                "pass": 3,
                "archived": 2,
                "retry": 1,
                "priority": 2,
                "pending": 2,
                "manual_review": 0,
                "blocked": 0,
            },
            "categories": {
                "standard": {"total": 5, "pass": 3, "archived": 2},
                "borrowed": {"total": 5, "pass": 0, "archived": 0},
            },
            "failure_classes": {},
        },
        "cases": [
            {
                "word": "padre",
                "language": "it",
                "category": "multi-step",
                "status": "pass",
            },
            {
                "word": "fake",
                "language": "it",
                "category": "standard",
                "status": "fail",
                "failure_class": "EXPECTED_FACT_MISSING",
                "reasons": ["missing form"],
            },
        ],
    }
    md = _generate_markdown_summary(report)
    assert "Corpus Coverage Summary" in md
    assert "50.0%" in md
    assert "EXPECTED_FACT_MISSING" in md
    assert "**fake**" in md


def test_select_batch_respects_quota_targets():
    queue = []
    for idx in range(10):
        queue.append({
            "word": f"new-{idx}",
            "category": "standard",
            "status": "pending",
            "priority": 50,
            "last_validated": None,
        })
    for idx in range(8):
        queue.append({
            "word": f"retry-{idx}",
            "category": "borrowed",
            "status": "retry",
            "priority": 60,
            "last_validated": "2026-01-01T00:00:00+00:00",
        })
    for idx in range(5):
        queue.append({
            "word": f"review-{idx}",
            "category": "compound",
            "status": "manual_review",
            "priority": 70,
            "last_validated": "2026-01-01T00:00:00+00:00",
        })
    queue.append({
        "word": "recheck-1",
        "category": "general",
        "status": "archived",
        "priority": 80,
        "next_due_at": "2000-01-01T00:00:00+00:00",
        "last_validated": "2025-01-01T00:00:00+00:00",
    })

    batch = _select_batch(queue, batch_size=10)
    statuses = {it["status"] for it in batch}
    assert "pending" in statuses or "priority" in statuses
    assert sum(1 for it in batch if it["status"] == "retry") >= 2
    assert sum(1 for it in batch if it["status"] == "manual_review") >= 1


def test_source_diagnostics_distinguish_regression_from_drift():
    same = _classify_source_diagnostic("sha1", "sha1", "EXPECTED_FACT_MISSING")
    changed = _classify_source_diagnostic("sha1", "sha2", "EXPECTED_FACT_MISSING")
    assert same == "PARSER_REGRESSION"
    assert changed == "SOURCE_DRIFT"
    assert _classify_source_diagnostic(None, "sha2", "EXPECTED_FACT_MISSING") is None


def test_a_conjecture_must_be_a_hypothesis_and_not_a_link():
    """`dipelare` proposes dēpilō; drawing it as an ancestor is the defect.

    Both halves are needed. Asked only to appear among the hypotheses, the
    expectation is satisfied by a tool that also drew it in the chain — that
    is, by the very mistake the case exists to catch.
    """
    facts = {
        "forms": {"dipelare::it", "dēpilō::la"},
        "bare_forms": {"dipelare", "dēpilō"},
        "relations": {"inherited"},
        "terminals": {"uncertain_origin"},
        "hypotheses": {"dēpilō::la", "dēpilō"},
        "chains": [["dipelare::it", "dēpilō::la"]],
    }
    expected = {
        "must_include_hypotheses": ["dēpilō::la"],
        "must_not_include_forms": ["dēpilō::la"],
    }
    failures = _check_expected_facts(facts, expected)
    assert any("must not be" in f for f in failures)

    # With the conjecture kept out of the chain, the same expectation passes.
    facts["forms"] = {"dipelare::it"}
    facts["bare_forms"] = {"dipelare"}
    assert _check_expected_facts(facts, expected) == []


def test_required_facts_are_matched_by_equality_not_substring():
    """`unadapted borrowing` must not satisfy a requirement for `borrowed`.

    Substring matching for required facts, against equality for forbidden
    ones, made the seed assert less than it appeared to — and in the direction
    that acquits.
    """
    facts = {
        "forms": set(), "bare_forms": set(), "hypotheses": set(), "chains": [],
        "relations": {"unadapted borrowing", "unadapted_borrowing"},
        "terminals": set(),
    }
    assert _check_expected_facts(facts, {"must_include_relations": ["borrowed"]})


class TestSeedLoading:
    """The builder writes `items`, the hand-written seed writes `words`.

    Reading only one of the two made the catalog load as zero lemmas, and the
    run reported a tidy audit of nothing — the two scripts disagreed about the
    file passing between them and neither said so.
    """

    def test_both_shapes_are_accepted(self, tmp_path):
        for key in ("words", "items"):
            path = tmp_path / f"{key}.json"
            path.write_text(json.dumps({key: [{"word": "fuoco"}]}), encoding="utf-8")
            assert _load_word_list(path) == [{"word": "fuoco"}]

    def test_an_unrecognised_shape_is_an_error_not_an_empty_list(self, tmp_path):
        path = tmp_path / "odd.json"
        path.write_text(json.dumps({"lemmas": [{"word": "fuoco"}]}), encoding="utf-8")
        with pytest.raises(ValueError, match="no case list"):
            _load_word_list(path)

    def test_an_empty_corpus_is_refused(self, tmp_path):
        # Nought out of nought is 100% by arithmetic and nothing by meaning,
        # and it is the sort of figure that survives a long time unquestioned.
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"items": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="nothing to audit"):
            _load_word_list(path)


class TestExpectationVocabulary:
    """A misspelled name behaves differently on the two sides, and that is why
    it is checked at load time rather than left to the run.
    """

    def test_a_typo_in_a_negative_field_is_refused(self, tmp_path):
        # This is the dangerous one: it matches nothing, is never violated,
        # and would pass forever whatever the tool did.
        path = tmp_path / "seed.json"
        path.write_text(json.dumps({"words": [
            {"word": "x", "expected": {"must_not_include_relations": ["borowed"]}}
        ]}), encoding="utf-8")
        with pytest.raises(ValueError, match="not a known value"):
            _load_word_list(path)

    def test_a_typo_in_a_positive_field_is_refused_too(self, tmp_path):
        path = tmp_path / "seed.json"
        path.write_text(json.dumps({"words": [
            {"word": "x", "expected": {"must_include_terminals": ["uncertian"]}}
        ]}), encoding="utf-8")
        with pytest.raises(ValueError, match="not a known value"):
            _load_word_list(path)

    def test_both_spellings_of_a_name_are_accepted(self, tmp_path):
        # The enum name and the human label mean the same thing.
        path = tmp_path / "seed.json"
        path.write_text(json.dumps({"words": [
            {"word": "x", "expected": {
                "must_include_terminals": ["uncertain_origin", "uncertain origin"],
                "must_include_relations": [
                    "unadapted_borrowing",   # the enum name
                    "borrowed unadapted",    # the label printed on screen
                ],
            }}
        ]}), encoding="utf-8")
        assert len(_load_word_list(path)) == 1

    def test_forms_are_not_checked_against_a_vocabulary(self, tmp_path):
        # Lemmas are words in any language, not a closed set.
        path = tmp_path / "seed.json"
        path.write_text(json.dumps({"words": [
            {"word": "x", "expected": {"must_not_include_forms": ["τραπεζὰκιον::el"]}}
        ]}), encoding="utf-8")
        assert len(_load_word_list(path)) == 1

    def test_the_real_seed_passes(self):
        # The seed in the repository must always satisfy this.
        seed = Path(__file__).parents[1] / "tools" / "validation" / "sample_words.json"
        assert _load_word_list(seed)


class TestWhatTurnsTheRunRed:
    """Only our own defects should make the workflow fail.

    The batch used to exit zero whatever happened, so a run stayed green with
    a hundred failures in it — and GitHub notifies failed runs and nothing
    else. The opposite mistake is worse: a red that fires on every missing
    etymology trains whoever watches it to stop looking.
    """

    def test_a_broken_invariant_is_alarming(self):
        assert _alarming({"failure_class": "FIDELITY_INVARIANT_VIOLATION"})

    def test_a_crash_is_alarming(self):
        assert _alarming({"failure_class": "EXECUTION_EXCEPTION"})

    def test_an_expectation_failing_on_an_unchanged_page_is_alarming(self):
        # The source said the same thing yesterday and we read it differently.
        assert _alarming({
            "failure_class": "EXPECTED_FACT_MISSING",
            "diagnostic_class": "PARSER_REGRESSION",
        })

    def test_a_source_without_an_etymology_is_not_alarming(self):
        # A third of Italian entries, and no business of ours.
        assert not _alarming({"failure_class": "SOURCE_LIMIT"})

    def test_an_entry_changed_upstream_is_not_alarming(self):
        assert not _alarming({
            "failure_class": "EXPECTED_FACT_MISSING",
            "diagnostic_class": "SOURCE_DRIFT",
        })

    def test_a_network_error_is_not_alarming(self):
        assert not _alarming({"failure_class": "TRANSIENT_NETWORK_ERROR"})


class TestPassIsNotAbsorbing:
    """A lemma that passes must become due again, or nothing is ever re-checked.

    For the first 19 nightly runs it did not. `pass` was a status no pool
    asked for, so a passed lemma was never selected again; `consecutive_passes`
    could only hold 0 or 1, the threshold of 3 was unreachable, and `archived`,
    `next_due_at` and the re-check quota were dead by construction. The audit
    therefore had no way to notice that Wiktionary had changed under a lemma it
    had already seen — the one thing a continuous validation exists to do.
    """

    @staticmethod
    def _queue(n, days_ago):
        stamp = (_utc_now() - timedelta(days=days_ago)).isoformat()
        return [
            {
                "word": f"w{i}", "language": "it", "status": "pass", "priority": 50,
                "attempts": 1, "consecutive_passes": 1,
                "last_validated": stamp, "next_due_at": None,
            }
            for i in range(n)
        ]

    def test_a_stale_pass_is_selected_again(self):
        queue = self._queue(10, days_ago=40)
        batch = _select_batch(queue, 5, revalidate_days=30)
        assert len(batch) == 5
        assert all(item["status"] == "pass" for item in batch)

    def test_a_fresh_pass_is_left_alone(self):
        queue = self._queue(10, days_ago=2)
        assert _select_batch(queue, 5, revalidate_days=30) == []

    def test_the_period_is_what_decides(self):
        queue = self._queue(10, days_ago=10)
        assert _select_batch(queue, 5, revalidate_days=30) == []
        assert len(_select_batch(queue, 5, revalidate_days=7)) == 5

    def test_an_unaudited_lemma_is_new_work_not_a_recheck(self):
        # No last_validated means never seen: it belongs to the `new` pool, and
        # must not be swept up as though it had gone stale.
        queue = [{"word": "w", "language": "it", "status": "pending",
                  "priority": 50, "attempts": 0, "consecutive_passes": 0,
                  "last_validated": None, "next_due_at": None}]
        batch = _select_batch(queue, 5, revalidate_days=30)
        assert [i["word"] for i in batch] == ["w"]
        assert batch[0]["status"] == "pending"

    def test_the_lifecycle_reaches_archived_over_time(self):
        # The property that never held: run the real selector over simulated
        # days and check that an item can accumulate three passes.
        start = _utc_now() - timedelta(days=30)
        queue = [{"word": f"w{i}", "language": "it", "status": "pending",
                  "priority": 50, "attempts": 0, "consecutive_passes": 0,
                  "last_validated": None, "next_due_at": None}
                 for i in range(200)]
        for day in range(30):
            today = start + timedelta(days=day)
            for item in _select_batch(queue, 20, revalidate_days=5):
                item["attempts"] += 1
                item["consecutive_passes"] += 1
                item["last_validated"] = today.isoformat()
                if item["consecutive_passes"] >= 3:
                    item["status"] = "archived"
                    item["next_due_at"] = (today + timedelta(days=5)).isoformat()
                else:
                    item["status"] = "pass"

        assert any(i["status"] == "archived" for i in queue), "nothing archived"
        assert max(i["attempts"] for i in queue) >= 3
