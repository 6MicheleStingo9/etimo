"""That what we report matches what the source says — no more, no less.

These tests guard the distinction the project is built on: a linguistic
terminal states a fact about the language, and may be emitted only on positive
evidence. Everything else must say that the limit is ours or the source's.

Each test here corresponds to a case where the tool used to claim more than the
entry supports, or less.
"""

import pytest

from etimo.languages import can_locate_reconstruction, page_title, wiktionary_name
from etimo.models import Relation, Terminal
from etimo.render import Style, tree
from etimo.walker import Reconstructor
from etimo.wikitext import etymology_sections, language_section, parse
from etimo.wiktionary import DictSource

PLAIN = Style(enabled=False)


def entry(language, etymology, extra=""):
    return (
        f"=={language}==\n\n===Etymology===\n{etymology}\n\n"
        f"===Noun===\n{{{{head}}}}\n{extra}"
    )


def walk(pages, word, language="it", **kwargs):
    return Reconstructor(DictSource(pages), **kwargs).reconstruct(word, language)


def leaves(result):
    return result.start.terminals()


class TestTemplateCoverage:
    """A template is read under every name it can be invoked with."""

    @pytest.mark.parametrize(
        "wikitext, relation",
        [
            ("{{ubor|it|en|computer}}", Relation.UNADAPTED_BORROWING),
            ("{{unadapted borrowing|it|en|computer}}", Relation.UNADAPTED_BORROWING),
            ("{{uder|it|la|ministerium}}", Relation.DERIVED),
            ("{{undefined derivation|it|la|x}}", Relation.DERIVED),
            ("{{learned borrowing|it|la|patientia}}", Relation.LEARNED_BORROWING),
            ("{{lbor|it|la|patientia}}", Relation.LEARNED_BORROWING),
            ("{{semantic loan|it|en|realize}}", Relation.SEMANTIC_LOAN),
            ("{{partial calque|it|de|x}}", Relation.PARTIAL_CALQUE),
        ],
    )
    def test_linear_relations_under_each_name(self, wikitext, relation):
        analysis = parse(wikitext, "it")
        assert len(analysis.steps) == 1
        assert analysis.steps[0].relation is relation

    @pytest.mark.parametrize(
        "wikitext, relation",
        [
            ("{{confix|it|gira|sole}}", Relation.AFFIXATION),
            ("{{con|it|gira|sole}}", Relation.AFFIXATION),
            ("{{clipping|it|automobile}}", Relation.CLIPPING),
            ("{{clip|it|automobile}}", Relation.CLIPPING),
            ("{{clipping of|it|automobile}}", Relation.CLIPPING),
            ("{{apocopic form of|it|automobile}}", Relation.CLIPPING),
            ("{{acronym|it|x}}", Relation.ABBREVIATION),
            ("{{initialism of|it|x}}", Relation.ABBREVIATION),
            ("{{it-deverbal|abbioccarsi}}", Relation.DEVERBAL),
            ("{{reduplication|it|fuggi}}", Relation.REDUPLICATION),
            ("{{univ|it|in|vece}}", Relation.COMPOUND),
            ("{{univerbation|it|in|vece}}", Relation.COMPOUND),
            ("{{alt form|it|padre}}", Relation.VARIANT),
        ],
    )
    def test_word_formation_under_each_name(self, wikitext, relation):
        analysis = parse(wikitext, "it")
        assert len(analysis.steps) == 1
        assert analysis.steps[0].relation is relation

    def test_the_same_fact_reads_the_same_under_either_name(self):
        # `con` and `confix` are the same template; recognising one and not the
        # other made the reading depend on which synonym an editor typed.
        a = parse("{{con|it|gira|sole}}", "it")
        b = parse("{{confix|it|gira|sole}}", "it")
        assert [f.lemma for f in a.steps[0].forms] == [f.lemma for f in b.steps[0].forms]


class TestPositiveTerminals:
    """Terminals the source states outright."""

    def test_requested_etymology_is_a_limit_of_the_source(self):
        # {{rfe}} means "nobody has written this yet". Reporting it as data
        # exhausted would turn an admission into a fact about the language.
        result = walk({"tintinnare": entry("Italian", "{{rfe|it}}")}, "tintinnare")
        terminal = result.start.terminal
        assert terminal is Terminal.ETYMOLOGY_MISSING
        assert not terminal.is_linguistic

    def test_imitative_origin_has_its_own_terminal(self):
        pages = {"miagolare": entry("Italian", "{{onomatopoeic|it}}.")}
        result = walk(pages, "miagolare")
        assert result.start.terminal is Terminal.IMITATIVE
        assert result.start.terminal.is_linguistic

    def test_an_eponym_names_whom_it_is_named_after(self):
        result = walk(
            {"paparazzo": entry("Italian", "{{named-after|it|Coriolano Paparazzo}}")},
            "paparazzo",
        )
        assert result.start.terminal is Terminal.EPONYM
        assert "Coriolano Paparazzo" in (result.start.note or "")

    def test_a_form_page_is_not_an_etymology(self):
        result = walk({"saetta": entry("Italian", "{{nonlemma}}")}, "saetta")
        assert result.start.terminal is Terminal.ETYMOLOGY_MISSING


class TestNoInventedFacts:
    """Where the tool used to assert more than the entry supports."""

    def test_a_missing_page_is_never_a_reconstructed_form(self):
        source = {"pater": entry("Latin", "From {{inh|la|itc-pro|*patēr}}.")}
        terminal = leaves(walk(source, "pater", "la"))[0].terminal
        assert terminal is Terminal.ENTRY_MISSING
        assert not terminal.is_linguistic

    def test_but_a_page_read_and_silent_is_where_reconstruction_stops(self):
        # The difference is whether we read anything. Wiktionary marks the end
        # of comparative reconstruction by writing no etymology at all, so for a
        # reconstructed form that silence *is* the answer — we heard it.
        source = {
            "pater": entry("Latin", "From {{inh|la|itc-pro|*patēr}}."),
            "Reconstruction:Proto-Italic/patēr": "==Proto-Italic==\n\n===Noun===\nx\n",
        }
        terminal = leaves(walk(source, "pater", "la"))[0].terminal
        assert terminal is Terminal.RECONSTRUCTED_FORM
        assert terminal.is_linguistic

    def test_an_attested_word_with_no_etymology_is_a_gap_in_the_source(self):
        source = {
            "x": entry("Italian", "From {{inh|it|la|verbum}}."),
            "verbum": "==Latin==\n\n===Noun===\nx\n",
        }
        terminal = leaves(walk(source, "x"))[0].terminal
        assert terminal is Terminal.ETYMOLOGY_MISSING
        assert not terminal.is_linguistic

    def test_an_unregistered_proto_language_is_not_a_reconstructed_form(self):
        # `Reconstruction:bnt-pro/x` cannot exist: the path needs the canonical
        # name. The gap is in our table.
        assert not can_locate_reconstruction("bnt-pro")
        pages = {"x": entry("Italian", "From {{der|it|bnt-pro|*abc}}.")}
        terminal = leaves(walk(pages, "x"))[0].terminal
        assert terminal is Terminal.LANGUAGE_MISSING

    def test_declared_uncertainty_survives_the_proposals_that_follow_it(self):
        # "Of uncertain origin. Probably from X" is a doubt with a suggestion,
        # not a chain. Walking the suggestion would replace the source's own
        # verdict with one of its guesses.
        page = entry(
            "Italian",
            "{{unc|it}} Probably from {{der|it|la|*bravus}}. "
            "Less likely from {{der|it|pro|brau}}.",
        )
        result = walk({"bravo": page}, "bravo")
        assert result.start.terminal is Terminal.UNCERTAIN_ORIGIN
        assert result.start.children == [], "no proposal may become a link"

    def test_uncertainty_about_the_ancestor_is_not_uncertainty_about_the_word(self):
        # The doubt qualifies the Arabic word just cited, not the Italian entry.
        analysis = parse(
            "Borrowed from {{bor|it|ar|x}}, a word of uncertain origin.", "it"
        )
        assert not analysis.uncertain
        assert len(analysis.steps) == 1

    def test_uncertainty_opening_the_section_is_the_entry_s_own(self):
        assert parse("Of unknown origin.", "it").uncertain
        assert parse("Uncertain.", "it").uncertain
        assert parse("Disputed.", "it").uncertain

    def test_prose_we_cannot_read_is_reported_as_ours_to_fix(self):
        result = walk({"allogliato": entry("Italian", "From loglio.")}, "allogliato")
        terminal = result.start.terminal
        assert terminal is Terminal.NOT_INTERPRETED
        assert not terminal.is_linguistic
        assert result.start.source_text == "From loglio."
        assert "From loglio." in tree(result, PLAIN)


class TestDescendantsAreNotAncestors:
    def test_the_body_stops_at_the_first_subheading(self):
        # A section formally contains the Noun and Descendants that follow it;
        # reading them turns a descendant into a supposed ancestor.
        page = (
            "==Italian==\n\n===Etymology 1===\nFrom {{inh|it|la|focus}}.\n\n"
            "====Noun====\n{{it-noun|m}}\n\n"
            "====Descendants====\n* {{der|scn|it|focu}}\n"
        )
        _, body = etymology_sections(language_section(page, "it"))[0]
        assert "focus" in body
        assert "Descendants" not in body
        assert "it-noun" not in body
        assert parse(body, "it").hypotheses == []

    def test_comparisons_are_not_collected_as_proposed_ancestors(self):
        analysis = parse(
            "{{unc|it}}\n"
            "* Compare {{der|it|es|fuego}}, a cognate.\n"
            "* Matasović derives it from {{der|it|ine-pro|*dhegwh-}}.\n",
            "it",
        )
        assert [h.form.lemma for h in analysis.hypotheses] == ["*dhegwh-"]

    def test_commentary_sections_do_not_count_as_etymologies(self):
        page = (
            "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|focus}}.\n\n"
            "===Etymology notes===\nDisputed.\n"
        )
        assert len(etymology_sections(language_section(page, "it"))) == 1


class TestConvergenceIsNotACycle:
    def test_two_branches_meeting_is_not_a_circular_reference(self):
        pages = {
            "xy": entry("Italian", "{{af|it|x|y}}"),
            "x": entry("Italian", "From {{inh|it|la|avus}}."),
            "y": entry("Italian", "From {{inh|it|la|avus}}."),
            "avus": entry("Latin", "{{doublet|la|z}}"),
        }
        terminals = {leaf.terminal for leaf in leaves(walk(pages, "xy"))}
        assert Terminal.CYCLE not in terminals
        assert Terminal.ALREADY_SHOWN in terminals

    def test_a_real_cycle_is_still_caught(self):
        pages = {
            "a": entry("Italian", "From {{der|it|it|b}}."),
            "b": entry("Italian", "From {{der|it|it|a}}."),
        }
        assert leaves(walk(pages, "a"))[0].terminal is Terminal.CYCLE

    def test_a_page_is_still_fetched_only_once(self):
        source = DictSource(
            {
                "x": entry("Italian", "{{af|it|y|y}}"),
                "y": entry("Italian", "From {{inh|it|la|ipsum}}."),
                "ipsum": entry("Latin", "Of unknown origin."),
            }
        )
        Reconstructor(source).reconstruct("x")
        assert source.requests_made == 3


class TestStartingWordIsNotSecondClass:
    def test_hypotheses_are_kept_when_the_starting_word_is_the_uncertain_one(self):
        # `etimo focus --language la` used to lose the conjectures that
        # `etimo fuoco` displayed, for the same entry.
        page = entry(
            "Latin",
            "* The origin is {{unc|la|nocap=1}}.\n"
            "* Some connect this to {{der|la|ine-pro|*bʰeh₂-|t=to shine}}.\n",
        )
        result = walk({"focus": page}, "focus", "la")
        assert result.start.terminal is Terminal.UNCERTAIN_ORIGIN
        assert [h.form.lemma for h in result.start.hypotheses] == ["*bʰeh₂-"]
        assert "*bʰeh₂-" in tree(result, PLAIN)


class TestLanguageCodes:
    def test_gaulish_is_looked_up_under_its_own_name(self):
        # Falling back on the base `cel` sent us to a "Celtic" section that does
        # not exist, while the real one is "Gaulish".
        assert wiktionary_name("cel-gau") == "Gaulish"

    def test_an_unknown_code_is_never_guessed_from_its_base(self):
        assert wiktionary_name("xyz-abc") == "xyz-abc"

    def test_early_medieval_latin_falls_back_to_latin(self):
        pages = {
            "bianco": entry("Italian", "From {{inh|it|la-eme|blancus}}."),
            "blancus": entry("Latin", "From {{der|la|frk|*blank}}."),
        }
        chain = walk(pages, "bianco").start.main_chain()
        assert [n.form.lemma for n in chain][:3] == ["bianco", "blancus", "*blank"]

    def test_several_codes_at_once_use_the_first(self):
        analysis = parse("{{der|it|roa-oca,oc-pro|escac}}", "it")
        assert analysis.steps[0].forms[0].language == "roa-oca,oc-pro"
        assert page_title("escac", "roa-oca,oc-pro") == "escac"


class TestComponentsKeepCleanLemmas:
    def test_inline_annotations_do_not_end_up_in_the_page_title(self):
        analysis = parse("{{af|it|pós<t:afterwards; by>|domani}}", "it")
        lemmas = [f.lemma for f in analysis.steps[0].forms]
        assert lemmas == ["pós", "domani"]
        assert analysis.steps[0].forms[0].gloss == "afterwards; by"


class TestTellingHomographsApart:
    """A spelling can stand for several unrelated words; the reader must be
    able to tell which is which without knowing the numbering in advance."""

    PAGE = (
        "==Italian==\n\n"
        "===Etymology 1===\nFrom {{inh|it|la|rīsus}}.\n\n"
        "====Noun====\n{{it-noun|m}}\n\n# [[laughter]], [[laugh]]\n\n"
        "===Etymology 2===\n{{nonlemma}}\n\n"
        "====Participle====\n{{it-pp}}\n\n# {{past participle of|it|ridere}}\n\n"
        "===Etymology 3===\nFrom {{inh|it|la-lat|oryza}}.\n\n"
        "====Noun====\n{{it-noun|m}}\n\n# [[rice]]\n"
    )

    def found(self):
        return Reconstructor(DictSource({"riso": self.PAGE})).senses("riso")

    def test_each_sense_carries_its_meaning_and_its_first_ancestor(self):
        one, _, three = self.found()
        assert (one.part_of_speech, one.definition) == ("noun", "laughter, laugh")
        assert one.ancestor.lemma == "rīsus"
        assert (three.part_of_speech, three.definition) == ("noun", "rice")
        assert three.ancestor.lemma == "oryza"

    def test_indexes_match_what_sense_expects(self):
        # The number shown must be the number that works, including for the
        # senses that are skipped when offering a choice.
        assert [s.index for s in self.found()] == [1, 2, 3]

    def test_an_inflected_form_is_not_a_choice(self):
        two = self.found()[1]
        assert not two.carries_etymology
        assert two.definition == "past participle of «ridere»"

    def test_definitions_of_inflected_forms_are_rendered_not_dropped(self):
        # Written entirely in templates, they would otherwise come out empty —
        # exactly where the reader needs to know what to skip.
        page = self.PAGE.replace(
            "# {{past participle of|it|ridere}}",
            "# {{misspelling of|it|risò}}",
        )
        two = Reconstructor(DictSource({"riso": page})).senses("riso")[1]
        assert two.definition == "misspelling of «risò»"

    def test_a_word_with_one_history_offers_nothing_to_choose(self):
        page = entry("Italian", "From {{inh|it|la|focus}}.")
        found = Reconstructor(DictSource({"fuoco": page})).senses("fuoco")
        assert len([s for s in found if s.carries_etymology]) == 1

    def test_listing_the_senses_costs_no_extra_request(self):
        source = DictSource({"riso": self.PAGE, "rīsus": "", "oryza": ""})
        walker = Reconstructor(source)
        walker.senses("riso")
        before = source.requests_made
        walker.reconstruct("riso", sense=1)
        assert source.requests_made == before + 1, "only the ancestor is new"
