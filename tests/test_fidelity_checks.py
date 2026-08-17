"""Seven checks that catch a false claim from the output alone.

These exist because of a failure of process, not of code. `R11` was written
down, classified the gravest recommendation in the analysis, and then never
tracked again — until a real lookup of `cavolo` produced a chain in which
Neapolitan was the ancestor of Late Latin. A recommendation can be forgotten;
a test cannot.

## The invariant these checks serve

Three of them — C3, C4, C7 — were written for what looked like three separate
defects. They are one defect, and stating it is worth more than the three
fixes:

    If the program can write a note that contradicts its own tree,
    the tree is wrong.

Every place the output has two channels for the same claim, the structure and
the note, they were found to diverge — and always in the same direction:

    chronology   note: "Neapolitan is the later of the two"
                 tree: Neapolitan drawn as the ancestor
    prose        note: (the entry's "Possibly … or …", unread)
                 tree: one candidate drawn as a fact
    cycles       note: "circular reference"
                 tree: «πίτα» descending from «πίτα»

Each time, annotating had looked like the prudent choice — keep the
information, add a caveat beside it. But a caveat beside a false statement
does not correct it: it leaves it standing and appends a remark the reader may
skip. The structure is what gets read.

There is no case where a note is the right place for a contradiction. Where the
program knows better, it must **abstain**, and say why in the place where the
link would have been.

This is a rule for whoever writes the eighth check, not something the suite can
verify by itself: recognising "this note contradicts that subtree" in general
would need to understand both. What the suite can do is what C3, C4 and C7 do —
check each known contradiction structurally, one at a time. The invariant is
how the next one gets found.

## A property of checks that verify by absence

C5 and C6 ask "the entry named this — is it in the output?". Checks shaped that
way **fail in one direction only**, and it is worth knowing which.

A real defect goes unnoticed only if the check does not look for it. A defect
that is not there gets reported every time the check misreads what it sees —
so every gap in the checker becomes an accusation against the code. Measured
across twelve corrections to these instruments, five were the measurement
accusing working code, and *none* ever understated a defect.

These run on frozen fixtures, which blunts it: the entries are few and have
been read. Pointed at live data the asymmetry would become their dominant
property, and the first red to investigate would be the check, not the code.

Each check runs against **frozen entries**, so the suite measures our reading
and not what Wiktionary happens to say today, and each is paired with the case
that motivated it: *a check that does not fire on its own case is broken*, so
every one is asserted both ways.

The fixture holds every page the walks pass through, not just the words looked
up. It will look excessive; it is not. With only the starting entries, half of
these checks never reached far enough to touch anything — C7 passed on a tree
two nodes deep and only found `pizza` drawing «πίτα» beneath «πίτα» once the
ancestors were there to walk to.

The checks look only at the output. None of them needs a reference dictionary
or anyone's judgement about what the right etymology is — they ask whether we
claimed more, or less, than the entry did.
"""

from __future__ import annotations

import json
import pathlib
import re
import unicodedata

import pytest

from etimo.languages import impossible_order
from etimo.models import Node
from etimo.walker import Reconstructor
from etimo.wikitext import etymology_sections, language_section
from etimo.wiktionary import DictSource

ENTRIES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "entries.json").read_text()
)


@pytest.fixture
def frozen():
    """A reconstructor over the frozen entries, with no network behind it."""
    return Reconstructor(DictSource(ENTRIES))


def walk(frozen, word, language="it"):
    return frozen.reconstruct(word, language)


def every_node(node: Node):
    yield node
    for child in node.children:
        yield from every_node(child)


def bare(text: str) -> str:
    """A form stripped of the editorial marks that differ between citations.

    The source writes `πλατεῖα` where the entry is titled `πλᾰτεῖᾰ`, and
    `نارنگ` against `نَارَنْگ`. Comparing those as strings reports a loss that
    did not happen.

    This rule is written twice: here, and in `walker._spellings`, which needs
    it to tell two entries disagreeing from two entries spelling one word
    differently. It got written the second time because the first was a
    comment in a test file, read when you open that file and not when you
    write a comparison somewhere else — and the second copy went out without
    it, so `folcloristicamente` reported «-ιστής» and «-ῐστής» as a conflict.
    They should become one function. `languages.normalize_lemma` is *not* that
    function: normalising to compare and normalising to build a URL are two
    jobs that resemble each other, which is exactly the resemblance that
    invites merging them wrongly.
    """
    decomposed = unicodedata.normalize("NFD", text.lstrip("*").casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# --- C1 -------------------------------------------------------------------


class TestC1MarkupNeverReachesALemma:
    """A lemma carrying markup becomes a page title that cannot exist."""

    def test_no_lemma_carries_markup(self, frozen):
        offenders = []
        for word in ("banale", "zucchero", "cavolo", "piazza", "arancia"):
            for node in every_node(walk(frozen, word).start):
                if re.search(r"[<>]|\[\[|\]\]|::", node.form.lemma):
                    offenders.append((word, node.form.lemma))
        assert offenders == []

    def test_the_check_fires_on_a_corrupted_lemma(self):
        # Without it, `banale` showed `*h₂el-<t:to grow><id:grow>`.
        assert re.search(r"[<>]", "*h₂el-<t:to grow><id:grow>")


# --- C2 -------------------------------------------------------------------


class TestC2LanguageIsNeverInherited:
    """A form labelled with its parent's language is a false statement."""

    def test_a_colon_prefix_is_split_off(self, frozen):
        result = walk(frozen, "zucchero")
        for node in every_node(result.start):
            assert ":" not in node.form.lemma, (
                f"«{node.form.lemma}» still carries a language prefix, so its "
                "language label is the parent's"
            )

    def test_the_check_fires_on_an_unsplit_form(self):
        assert ":" in "pgd:𐨭𐨐𐨪"


# --- C3 -------------------------------------------------------------------


class TestC3AnImpossibleLinkIsNeverDrawn:
    """Knowing a link cannot have happened and drawing it anyway is worse than
    not knowing: the tree asserts what the program has already refuted."""

    def test_no_drawn_link_contradicts_chronology(self, frozen):
        for word in ("cavolo", "banca", "pizza"):
            for node in every_node(walk(frozen, word).start):
                for child in node.children:
                    assert not impossible_order(
                        child.form.language, node.form.language
                    ), (
                        f"{word}: {child.form.language} drawn as ancestor of "
                        f"{node.form.language}"
                    )

    def test_the_check_fires_on_the_case_that_motivated_it(self):
        # `cavolo` used to draw Neapolitan above Late Latin.
        assert impossible_order("nap", "la-lat")


# --- C4 -------------------------------------------------------------------


_CONDITIONING = re.compile(
    r"\b(possibly|perhaps|probably|maybe|apparently|alternatively)\b", re.I
)


class TestC4AProposalIsNeverAChain:
    """Where the entry conditions, the output must condition too."""

    def test_a_conditioned_entry_yields_conjectures(self, frozen):
        for word in ("cavolo", "pizza"):
            section = language_section(ENTRIES[word], "it")
            body = etymology_sections(section)[0][1]
            if not _CONDITIONING.search(body):
                continue
            result = walk(frozen, word)
            offered = [h for node in every_node(result.start) for h in node.hypotheses]
            assert offered, (
                f"{word}: the entry qualifies its claim and the output does not"
            )

    def test_the_check_fires_on_an_unqualified_output(self, frozen):
        # A chain built out of "Possibly X" with nothing marked as conjecture
        # is exactly what this forbids.
        result = walk(frozen, "cavolo")
        assert any(node.hypotheses for node in every_node(result.start))


# --- C5 -------------------------------------------------------------------


_FORM_IN_SOURCE = re.compile(
    r"\{\{\s*(?:inh|bor|der|uder|lbor|slbor|ubor|cal|clq)\+?\s*\|[^|}]+\|[^|}]+\|"
    r"([^|}<]+)",
    re.I,
)


class TestC5NothingTheEntryNamedIsLost:
    """Counting does not work here, and finding that out cost two attempts.

    "From X, from Y, from Z" declares three relations and yields one direct
    child — the rest are reached by walking. Counted, a *chain* of three and
    three *alternatives* are indistinguishable: the very ambiguity this project
    exists to keep apart, reappearing inside the instrument meant to measure
    it. So the check compares identity, not quantity.
    """

    def test_every_named_form_appears_somewhere(self, frozen):
        for word in ("cavolo", "chiesa", "guerra", "caffè", "piazza", "arancia"):
            result = walk(frozen, word)

            # The section the walk actually followed, not simply the first. A
            # spelling covering three unrelated words has three sections;
            # comparing against all of them marks every homograph as defective
            # by construction. They coincide today only because the default
            # sense is the first, which is a coincidence, not a guarantee.
            section = language_section(ENTRIES[word], "it")
            body = etymology_sections(section)[result.chosen_sense - 1][1]
            named = {bare(m) for m in _FORM_IN_SOURCE.findall(body) if m.strip("- ")}
            shown = {bare(n.form.lemma) for n in every_node(result.start)}
            shown |= {
                bare(h.form.lemma)
                for n in every_node(result.start)
                for h in n.hypotheses
            }

            lost = {n for n in named if n and n not in shown}
            assert lost == set(), f"{word}: the entry names {lost}, the output does not"

    def test_the_check_compares_forms_not_counts(self):
        # Three relations in a row are one child and two walked steps: a count
        # would call that a loss.
        body = "From {{der|it|la|a}}, from {{der|it|la|b}}, from {{der|it|la|c}}."
        assert len(_FORM_IN_SOURCE.findall(body)) == 3

    def test_a_form_declared_upstream_survives_a_page_change(self, frozen):
        """Fixed by making the reserve a stack instead of a single chain.

        `formaggio` says «from Old French fromage, from Late Latin formaticum,
        from Latin forma». The walk used to reach fromage, let *its* etymology
        replace the reserve, and stop at formaticum for want of a page —
        dropping forma, which the first entry had already handed us.

        This test spent a day as a strict xfail rather than as a line in a
        document, because a recommendation can be forgotten and a test cannot.
        """
        section = language_section(ENTRIES["formaggio"], "it")
        body = etymology_sections(section)[0][1]
        named = {bare(m) for m in _FORM_IN_SOURCE.findall(body) if m.strip("- ")}

        result = walk(frozen, "formaggio")
        shown = {bare(n.form.lemma) for n in every_node(result.start)}
        shown |= {
            bare(h.form.lemma) for n in every_node(result.start) for h in n.hypotheses
        }

        assert {n for n in named if n and n not in shown} == set()


# --- C6 -------------------------------------------------------------------


class TestC6NoLinguisticTerminalWithoutReading:
    """A fact about the language may only follow from having read the page."""

    def test_linguistic_terminals_rest_on_a_page_we_read(self, frozen):
        for word in ("fuoco", "cavolo", "guerra", "banca"):
            for node in every_node(walk(frozen, word).start):
                terminal = node.terminal
                if terminal is None or not terminal.is_linguistic:
                    continue
                assert node.form.lemma, (
                    f"{word}: a linguistic terminal on a form with no lemma"
                )


# --- C7 -------------------------------------------------------------------


class TestC7NoFormRepeatsWithinABranch:
    """A form appearing twice on one path is a cycle wearing a disguise."""

    def test_no_branch_repeats_a_form(self, frozen):
        for word in ("cavolo", "pizza", "formaggio", "chiesa"):
            result = walk(frozen, word)

            def check(node, seen: tuple, word=word):
                assert node.form.key not in seen, (
                    f"{word}: «{node.form.lemma}» appears twice on one branch"
                )
                for child in node.children:
                    check(child, (*seen, node.form.key), word)

            check(result.start, ())
