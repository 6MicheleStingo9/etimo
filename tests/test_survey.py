"""The corpus survey: where etimo reaches, counted rather than sampled.

Offline like the rest of the suite. What is tested here is the bookkeeping —
resumption, classification of outcomes, tolerance of a half-written file —
because a run that lasts weeks will be interrupted, and an interruption must
cost the entry in flight and nothing else.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etimo.wiktionary import DictSource  # noqa: E402
from tools.survey_corpus import (  # noqa: E402
    _already_done,
    _summarise,
    _survey_one,
)


def entry(language: str, etymology: str) -> str:
    return (
        f"=={language}==\n\n===Etymology===\n{etymology}\n\n===Noun===\n{{{{head}}}}\n"
    )


class TestOutcomes:
    """Four outcomes, and the line between them is the project's own.

    A branch that ends because the language has nothing more to give is a
    finding; one that ends because the source or the program could not go on is
    a limit. A tree can do both, so `partial` is not a rounding of the other
    two — it is the honest answer for a compound whose halves fared differently.
    """

    def test_a_chain_ending_on_a_finding_is_complete(self):
        source = DictSource({
            "x": entry("Italian", "From {{inh|it|la|y}}."),
            "y": entry("Latin", "Of uncertain origin."),
        })
        assert _survey_one("x", source)["outcome"] == "complete"

    def test_a_chain_ending_on_a_limit_is_limited(self):
        source = DictSource({"x": entry("Italian", "From {{inh|it|la|missing}}.")})
        row = _survey_one("x", source)
        assert row["outcome"] == "limited"
        assert row["terminals"] == ["entry_missing"]

    def test_a_compound_faring_both_ways_is_partial(self):
        source = DictSource({
            "x": entry("Italian", "{{af|it|a|b}}"),
            "a": entry("Italian", "Of uncertain origin."),
            # `b` has no page: that branch stops at a limit of the source.
        })
        assert _survey_one("x", source)["outcome"] == "partial"

    def test_an_entry_going_nowhere_has_no_chain(self):
        source = DictSource({"x": "==Italian==\n\n===Noun===\n{{head}}\n\n# a word\n"})
        row = _survey_one("x", source)
        assert row["outcome"] == "no chain"
        assert row["steps"] == 0

    def test_an_unreadable_entry_does_not_stop_the_survey(self):
        # One bad entry in 127101 must not end a run that has taken days.
        class Exploding:
            def wikitext(self, title):
                raise RuntimeError("boom")

        row = _survey_one("x", Exploding())
        assert row["outcome"] == "exception"
        assert "boom" in row["error"]


class TestResumption:
    def test_finished_words_are_remembered(self, tmp_path):
        log = tmp_path / "survey.jsonl"
        log.write_text(
            '{"word": "a", "outcome": "complete"}\n'
            '{"word": "b", "outcome": "limited"}\n',
            encoding="utf-8",
        )
        assert _already_done(log) == {"a", "b"}

    def test_a_half_written_line_is_skipped_not_fatal(self, tmp_path):
        # The process was killed mid-write. That entry is surveyed again; the
        # rest of the file is intact and must stay usable.
        log = tmp_path / "survey.jsonl"
        log.write_text(
            '{"word": "a", "outcome": "complete"}\n{"word": "trunc',
            encoding="utf-8",
        )
        assert _already_done(log) == {"a"}
        assert _summarise(log)["surveyed"] == 1

    def test_an_absent_log_means_nothing_done(self, tmp_path):
        assert _already_done(tmp_path / "nothing.jsonl") == set()


class TestSummary:
    def test_counts_outcomes_and_terminals(self, tmp_path):
        log = tmp_path / "survey.jsonl"
        log.write_text(
            "\n".join(
                json.dumps(row)
                for row in (
                    {"word": "a", "outcome": "complete", "steps": 3,
                     "terminals": ["uncertain_origin"]},
                    {"word": "b", "outcome": "limited", "steps": 1,
                     "terminals": ["entry_missing"]},
                    {"word": "c", "outcome": "complete", "steps": 2,
                     "terminals": ["uncertain_origin", "reconstructed_form"]},
                )
            ) + "\n",
            encoding="utf-8",
        )
        summary = _summarise(log)
        assert summary["surveyed"] == 3
        assert summary["outcomes"]["complete"] == 2
        assert summary["terminals"]["uncertain_origin"] == 2
        assert summary["mean_steps"] == 2.0


class TestAnchoring:
    """Every form drawn must be one the source actually wrote.

    This is the only check in the project that does not go through the
    parser's tables: it asks a flat textual question — does this lemma appear
    anywhere in the pages the walk read? — so a form the tool manufactured has
    nowhere to hide, even when the manufacture came from a table that a
    table-driven check would agree with.

    It says nothing about whether an etymology is true. That is Wiktionary's
    business. It says the tree is *anchored*: everything in it was taken from
    the source rather than invented — the only correctness this tool can be
    held to, and one it can be held to absolutely.
    """

    def test_a_tree_taken_from_the_source_is_anchored(self):
        source = DictSource({
            "x": entry("Italian", "From {{inh|it|la|focus}}."),
            "focus": entry("Latin", "Of uncertain origin."),
        })
        row = _survey_one("x", source)
        assert row["anchored"] is True
        assert row["forms_unanchored"] == 0

    def test_a_manufactured_form_is_caught(self):
        # The check must be able to fail, or it is decoration. A walker that
        # invents `phantasma` out of a table nobody checked would pass every
        # structural invariant; it does not pass this.
        from etimo.models import Form, Node
        from tools.survey_corpus import _anchoring

        root = Node(form=Form(lemma="x", language="it"))
        root.children.append(Node(form=Form(lemma="phantasma", language="la")))
        # `seen()` prepends the page titles; here the haystack is written out,
        # so "x" stands for the title the walk started from.
        result = _anchoring(root, "x\n==Italian==\nFrom {{inh|it|la|focus}}.")

        assert result["forms_unanchored"] == 1
        assert result["unanchored"] == ["phantasma::la"]

    def test_the_word_looked_up_is_not_called_invented(self):
        # An entry rarely repeats its own name in its etymology: `dipelare`
        # says «From {{af|it|di-|pelo|-are}}» and never writes "dipelare".
        # Comparing against the body alone reported the starting word as
        # unanchored on every entry of that shape — the check accusing the tool
        # of inventing the question it had been asked.
        source = DictSource({"dipelare": entry("Italian", "From {{af|it|di-|pelo}}.")})
        assert _survey_one("dipelare", source)["anchored"] is True

    def test_editorial_marks_do_not_count_as_invention(self):
        # An entry writes `πλατεῖα` where the page is titled `πλᾰτεῖᾰ`. The
        # same normalisation the walker uses to reconcile two entries applies
        # here, for the same reason: a difference of diacritics is a spelling,
        # not a fabrication.
        from etimo.models import Form, Node
        from tools.survey_corpus import _anchoring

        root = Node(form=Form(lemma="πλᾰτεῖᾰ", language="grc"))
        haystack = "πλᾰτεῖᾰ\nfrom {{der|it|grc|πλατεῖα}}"
        assert _anchoring(root, haystack)["forms_unanchored"] == 0
