"""The three views on a result."""

import json
from typing import ClassVar

from etimo.render import Style, as_json, chain, tree
from etimo.walker import Reconstructor
from etimo.wiktionary import DictSource

PLAIN = Style(enabled=False)


def entry(language: str, etymology: str) -> str:
    return f"=={language}==\n\n===Etymology===\n{etymology}\n"


SOURCE = DictSource(
    {
        "fuoco": entry("Italian", "From {{inh|it|la|focus|t=hearth}}."),
        "focus": entry(
            "Latin",
            "* The origin is {{unc|la|nocap=1}}.\n"
            "* Matasović opts to derive from {{der|la|ine-pro|*dʰegʷʰ-|t=to burn}}.",
        ),
    }
)

COMPOUND = DictSource(
    {
        "capolavoro": entry("Italian", "{{af|it|capo|lavoro}}"),
        "capo": entry("Italian", "Of uncertain origin."),
        "lavoro": entry("Italian", "Of uncertain origin."),
    }
)


def reconstruct(source, word="fuoco", language="it"):
    return Reconstructor(source).reconstruct(word, language)


class TestTree:
    def test_alternates_relation_and_form(self):
        lines = tree(reconstruct(SOURCE), PLAIN).splitlines()
        assert lines[0] == "fuoco (it)"
        assert "inherited from Latin" in lines[1]
        assert "focus (la) «hearth»" in lines[2]

    def test_terminal_shown_with_its_symbol(self):
        assert "⊗ uncertain origin" in tree(reconstruct(SOURCE), PLAIN)

    def test_hypotheses_kept_apart_from_the_chain(self):
        text = tree(reconstruct(SOURCE), PLAIN)
        # Conjectures appear, but marked as such and below the terminal.
        assert "perhaps *dʰegʷʰ- (ine-pro)" in text
        assert "Matasović" in text
        assert text.index("perhaps *dʰegʷʰ-") > text.index("uncertain origin")

    def test_summary_counts_jumps_not_lines(self):
        assert "1 step · terminal: uncertain origin" in tree(reconstruct(SOURCE), PLAIN)

    def test_shared_relation_written_once(self):
        text = tree(reconstruct(COMPOUND, "capolavoro"), PLAIN)
        assert text.count("formed with affixes from") == 1
        assert "├─ capo (it)" in text
        assert "└─ lavoro (it)" in text

    def test_summary_aggregates_multiple_terminals(self):
        text = tree(reconstruct(COMPOUND, "capolavoro"), PLAIN)
        assert "2 terminals: 2× uncertain origin" in text


class TestChain:
    def test_one_line_per_link(self):
        rendered = chain(reconstruct(SOURCE), PLAIN).splitlines()
        lines = [line for line in rendered if line.strip()]
        assert lines[0] == "fuoco (it)"
        assert "← focus (la) «hearth»" in lines[1]
        assert "inherited from Latin" in lines[1]

    def test_closes_with_the_terminal(self):
        lines = chain(reconstruct(SOURCE), PLAIN).splitlines()
        assert lines[2].strip().startswith("← ⊗")


class TestJson:
    def test_recursive_structure(self):
        data = json.loads(as_json(reconstruct(SOURCE)))
        assert data["word"] == "fuoco"
        assert data["steps"] == 1

        ancestor = data["tree"]["ancestors"][0]
        assert ancestor["lemma"] == "focus"
        assert ancestor["relation"] == "inherited"
        assert ancestor["gloss"] == "hearth"

    def test_terminal_states_whether_it_is_linguistic(self):
        data = json.loads(as_json(reconstruct(SOURCE)))
        terminal = data["tree"]["ancestors"][0]["terminal"]
        assert terminal["type"] == "uncertain_origin"
        assert terminal["linguistic"] is True

    def test_hypotheses_in_a_separate_field(self):
        # The fact/conjecture distinction must survive serialisation, or
        # whoever consumes the JSON loses it.
        data = json.loads(as_json(reconstruct(SOURCE)))
        ancestor = data["tree"]["ancestors"][0]
        assert ancestor["hypotheses"][0]["lemma"] == "*dʰegʷʰ-"
        assert "Matasović" in ancestor["hypotheses"][0]["attribution"]
        assert "ancestors" not in ancestor

    def test_reconstructed_forms_flagged(self):
        source = DictSource({"pater": entry("Latin", "From {{inh|la|itc-pro|*patēr}}.")})
        data = json.loads(as_json(reconstruct(source, "pater", "la")))
        assert data["tree"]["ancestors"][0]["reconstructed"] is True


class TestStyle:
    def test_no_escape_sequences_when_disabled(self):
        assert "\033[" not in tree(reconstruct(SOURCE), PLAIN)


class TestSkippedStages:
    """`{{der}}` claims an ultimate origin, not a direct passage.

    Drawn identically to inheritance, a run of them reads as successive stages
    when it may hide a dozen. The count must say so.
    """

    SOURCE: ClassVar[DictSource] = DictSource(
        {
            "riso": entry("Italian", "From {{inh|it|la-lat|oryza}}."),
            "oryza": entry("Latin", "From {{der|la|grc|ὄρυζα}}."),
            "ὄρυζα": entry("Ancient Greek", "From {{der|grc|ira-pro|*wrinǰiš}}."),
        }
    )

    def test_summary_counts_the_uncertain_links(self):
        text = tree(reconstruct(self.SOURCE, "riso"), PLAIN)
        assert "3 steps" in text
        assert "2 links may skip stages" in text

    def test_nothing_said_when_every_link_is_direct(self):
        source = DictSource(
            {
                "fuoco": entry("Italian", "From {{inh|it|la|focus}}."),
                "focus": entry("Latin", "Of uncertain origin."),
            }
        )
        text = tree(reconstruct(source, "fuoco"), PLAIN)
        assert "skip stages" not in text

    def test_singular_when_there_is_only_one(self):
        source = DictSource(
            {
                "x": entry("Italian", "From {{der|it|la|y}}."),
                "y": entry("Latin", "Of uncertain origin."),
            }
        )
        assert "1 link may skip stages" in tree(reconstruct(source, "x"), PLAIN)

    def test_json_flags_each_link(self):
        data = json.loads(as_json(reconstruct(self.SOURCE, "riso")))
        inherited = data["tree"]["ancestors"][0]
        derived = inherited["ancestors"][0]
        assert inherited["contiguous"] is True
        assert derived["contiguous"] is False

    def test_the_root_of_the_tree_has_no_flag(self):
        # The word asked about descends from nothing here: the key belongs to
        # links, and inventing one for the starting form would be noise.
        data = json.loads(as_json(reconstruct(self.SOURCE, "riso")))
        assert "contiguous" not in data["tree"]


class TestQuotationAndComment:
    """What the source says, kept apart from what etimo says about it.

    Both are in English, so without a visible difference a reader has no way
    of telling a citation from a comment — and that distinction is the premise
    the whole project rests on.
    """

    def test_quotations_are_coloured_differently_from_comments(self):
        coloured = Style(enabled=True)
        coloured.enabled = True  # force, regardless of the test's own tty
        text = tree(reconstruct(SOURCE), coloured)
        # The gloss is the source speaking; the terminal is the tool speaking.
        assert "\033[3;36m«hearth»" in text
        assert "\033[1;33m⊗ uncertain origin" in text

    def test_the_distinction_survives_without_colour(self):
        # On a monochrome terminal the guillemets carry it instead.
        text = tree(reconstruct(SOURCE), PLAIN)
        assert "«hearth»" in text
        assert "«Matasović opts to derive from»" in text
        assert "uncertain origin" in text  # ours, unquoted
