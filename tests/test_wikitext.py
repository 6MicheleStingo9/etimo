"""Reading of the wikitext.

The fragments used here reproduce the structure of real en.wiktionary.org
entries at the time of writing. They are fixed on purpose: these tests must
validate our parser, not the present state of Wiktionary.
"""

import pytest

from etimo.models import Declaration, Relation
from etimo.wikitext import (
    _clean_target,
    definition_statement,
    etymology_sections,
    language_section,
    lemma_reference,
    parse,
)

MULTILINGUAL_PAGE = """\
{{also|Focus}}
==English==

===Etymology===
{{bor+|en|la|focus}}.

===Noun===
{{en-noun}}

==Latin==

===Etymology===
* The origin is {{unc|la|nocap=1}}. Usually connected with {{cog|xcl|բոց}}.
* Some connect this along with {{m|la|faciēs}} to {{der|la|ine-pro|*bʰeh₂-|t=to shine}}.
* Matasović opts to derive from {{der|la|ine-pro|*dʰegʷʰ-|t=to burn}}.

===Noun===
{{la-noun}}

==Dutch==

===Etymology===
{{bor+|nl|la|focus}}.
"""

ENTRY_WITH_TWO_ETYMOLOGIES = """\
==Italian==

===Etymology 1===
{{inh+|it|la|rīsus}}.

====Noun====
{{it-noun|m}}

===Etymology 2===
{{inh+|it|la-lat|oryza}}, from {{der|it|grc|ὄρυζα}}.

====Noun====
{{it-noun|m}}
"""


class TestSectionSelection:
    def test_isolates_the_requested_language(self):
        latin = language_section(MULTILINGUAL_PAGE, "la")
        assert latin is not None
        assert "Matasović" in latin
        # It must not spill into the neighbouring sections.
        assert "en-noun" not in latin
        assert "bor+|nl" not in latin

    def test_missing_language(self):
        assert language_section(MULTILINGUAL_PAGE, "grc") is None

    def test_several_etymologies_in_one_entry(self):
        section = language_section(ENTRY_WITH_TWO_ETYMOLOGIES, "it")
        etymologies = etymology_sections(section)
        assert [name for name, _ in etymologies] == ["Etymology 1", "Etymology 2"]
        # Each block includes its own subsections but not the next one.
        assert "rīsus" in etymologies[0][1]
        assert "oryza" not in etymologies[0][1]


class TestMainChain:
    def test_simple_inheritance(self):
        analysis = parse("From {{inh|it|la|focus|t=hearth}}.", "it")
        assert len(analysis.steps) == 1
        step = analysis.steps[0]
        assert step.relation is Relation.INHERITED
        assert step.forms[0].lemma == "focus"
        assert step.forms[0].language == "la"
        assert step.forms[0].gloss == "hearth"

    def test_textual_order_is_the_order_of_the_chain(self):
        # Both templates declare `it` as their starting language: only the
        # order in the text says which link comes first.
        analysis = parse(
            "{{bor+|it|ota|قهوه|tr=kahve}}, from {{der|it|ar|قَهْوَة}}.", "it"
        )
        assert [s.relation for s in analysis.steps] == [
            Relation.BORROWED,
            Relation.DERIVED,
        ]
        assert analysis.steps[0].forms[0].language == "ota"
        assert analysis.steps[0].forms[0].transliteration == "kahve"
        assert analysis.steps[1].forms[0].language == "ar"

    def test_gloss_as_fifth_positional(self):
        analysis = parse("{{der|it|la-med|sclavus||[[slave]]}}", "it")
        assert analysis.steps[0].forms[0].gloss == "slave"

    def test_mentions_do_not_become_ancestors(self):
        analysis = parse(
            "{{bor+|it|vec|s-ciao}}, {{m|vec|sciavo}} (whence {{cog|it|schiavo}}).",
            "it",
        )
        assert len(analysis.steps) == 1
        assert analysis.steps[0].forms[0].lemma == "s-ciao"

    def test_asterisk_kept_on_reconstructed_forms(self):
        analysis = parse("{{inh|la|itc-pro|*patēr}}", "la")
        form = analysis.steps[0].forms[0]
        assert form.lemma == "*patēr"
        assert form.reconstructed


class TestBranching:
    def test_compound_yields_several_forms(self):
        analysis = parse("{{af|it|capo|lavoro}}", "it")
        assert len(analysis.steps) == 1
        step = analysis.steps[0]
        assert step.branching
        assert [f.lemma for f in step.forms] == ["capo", "lavoro"]
        assert all(f.language == "it" for f in step.forms)

    def test_component_from_another_language(self):
        analysis = parse("{{af|it|auto-|la:mobilis}}", "it")
        assert [f.language for f in analysis.steps[0].forms] == ["it", "la"]


class TestUncertaintyAndHypotheses:
    def test_uncertainty_template(self):
        section = language_section(MULTILINGUAL_PAGE, "la")
        analysis = parse(etymology_sections(section)[0][1], "la")
        assert analysis.uncertain
        # Uncertainty is a terminal: no step may enter the chain.
        assert analysis.steps == []

    def test_hypotheses_collected_with_attribution(self):
        section = language_section(MULTILINGUAL_PAGE, "la")
        analysis = parse(etymology_sections(section)[0][1], "la")
        assert [h.form.lemma for h in analysis.hypotheses] == ["*bʰeh₂-", "*dʰegʷʰ-"]
        assert "Matasović" in analysis.hypotheses[1].attribution

    def test_mentions_rendered_readable_in_attributions(self):
        # Deleting the templates would leave "Some connect this along with to".
        section = language_section(MULTILINGUAL_PAGE, "la")
        analysis = parse(etymology_sections(section)[0][1], "la")
        assert "faciēs" in analysis.hypotheses[0].attribution

    def test_uncertainty_stated_in_words(self):
        assert parse("Of unknown origin.", "it").uncertain


class TestStructuredFormat:
    """Reading of {{ety}} and {{etymon}}, used where prose is absent."""

    def test_affixal_derivation(self):
        analysis = parse(
            "{{ety|la|title=paternus|:af|pater<t:father>|-nus<id:adjective>"
            "|text=+|tree=1}}",
            "la",
        )
        assert len(analysis.steps) == 1
        step = analysis.steps[0]
        assert step.relation is Relation.AFFIXATION
        assert [f.lemma for f in step.forms] == ["pater", "-nus"]
        assert step.forms[0].gloss == "father"
        # Unprefixed components belong to the language of the entry.
        assert all(f.language == "la" for f in step.forms)

    def test_borrowing_with_explicit_language(self):
        analysis = parse("{{etymon|la|:bor|grc:ἐκκλησία<id:assembly>}}", "la")
        form = analysis.steps[0].forms[0]
        assert analysis.steps[0].relation is Relation.BORROWED
        assert (form.language, form.lemma) == ("grc", "ἐκκλησία")

    def test_form_declared_in_the_alt_annotation(self):
        analysis = parse("{{etymon|grc|:der|ira-pro:<alt:*wrinǰiš><id:rice>}}", "grc")
        assert analysis.steps[0].forms[0].lemma == "*wrinǰiš"

    def test_nesting_does_not_confuse_the_first_level(self):
        # The `<ety:…>` continuation is ignored: we rebuild it by walking up to
        # the ancestor's entry, where the data is first-hand.
        analysis = parse(
            "{{ety|la|:inh|itc-pro:*akʷā<ety:inh<ine-pro:*h₂ekʷeh₂>>}}", "la"
        )
        assert len(analysis.steps) == 1
        assert analysis.steps[0].forms[0].lemma == "*akʷā"
        assert analysis.steps[0].forms[0].language == "itc-pro"

    def test_id_annotation_not_mistaken_for_an_italics_tag(self):
        # `<id:…>` is not `<i>`: deleting it would lose the form that follows.
        analysis = parse("{{ety|la|:bor|grc:ἐκκλησία<id:assembly>}}", "la")
        assert analysis.steps[0].forms[0].lemma == "ἐκκλησία"

    def test_prose_takes_precedence(self):
        # Where both are present prose declares more steps: using both would
        # produce duplicated links.
        analysis = parse(
            "{{etymon|it|id=coffee|:bor|ota:قهوه<id:coffee>}}\n"
            "{{bor+|it|ota|قهوه|tr=kahve}}, from {{der|it|ar|قَهْوَة}}.",
            "it",
        )
        assert [s.forms[0].language for s in analysis.steps] == ["ota", "ar"]

    def test_declared_uncertainty_is_not_overridden(self):
        analysis = parse("Of unknown origin. {{ety|la|:der|ine-pro:*bʰeh₂-}}", "la")
        assert analysis.uncertain
        assert analysis.steps == []


class TestAncillaryData:
    def test_root_does_not_enter_the_chain(self):
        # {{root}} states the ultimate root: treating it as a step would skip
        # every intermediate stage.
        analysis = parse("{{root|it|ine-pro|*bʰer-}} From {{inh|it|la|ferre}}.", "it")
        assert len(analysis.steps) == 1
        assert analysis.steps[0].forms[0].lemma == "ferre"
        assert analysis.root.lemma == "*bʰer-"

    def test_bibliographic_references_ignored(self):
        analysis = parse(
            "From {{inh|it|la|focus}}.<ref>{{R:itc:EDL|page=228}}</ref>", "it"
        )
        assert len(analysis.steps) == 1

    def test_named_and_self_closing_refs(self):
        analysis = parse(
            'From {{inh|it|la|focus}}<ref name=a>x</ref> then <ref name="a" />.', "it"
        )
        assert len(analysis.steps) == 1

    def test_etymon_syntax_is_not_a_ref_tag(self):
        # {{etymon}} writes `<ref:...>` in angle brackets: mistaking it for a
        # tag opening makes the cleanup delete everything up to the next
        # `</ref>`, leaving the etymology empty.
        analysis = parse(
            "{{etymon|grc|id=rice|:der|ira-pro:<alt:*wrinǰiš>"
            "<ref:{{R:grc:Beekes|pages=1112-3}}>|tree=+}}\n"
            "A borrowing from an Eastern {{der|grc|ira|-}} language, "
            "from {{der|grc|ira-pro|*wrinǰiš}}.<ref>Beekes</ref>",
            "grc",
        )
        assert [s.forms[0].lemma for s in analysis.steps] == ["", "*wrinǰiš"]

    def test_doublet_recorded_as_a_note(self):
        analysis = parse("{{doublet|it|chef}} From {{inh|it|la|caput}}.", "it")
        assert any("chef" in note for note in analysis.notes)


class TestLemmaReference:
    """Finding the lemma an inflected form points at."""

    PAGE = (
        "==Italian==\n\n===Verb===\n{{head|it|verb form}}\n\n"
        "# {{past participle of|it|andare}}\n"
    )

    def test_pointer_found_among_the_definitions(self):
        found = lemma_reference(self.PAGE, "it")
        assert found is not None
        form, wording = found
        assert (form.lemma, form.language) == ("andare", "it")
        assert wording == "past participle of"

    def test_only_part_of_speech_sections_are_searched(self):
        # A cross-reference under "Related terms" or "Descendants" is not a
        # statement that this page is a form of that word.
        page = (
            "==Italian==\n\n===Noun===\n{{it-noun|f}}\n\n# a house\n\n"
            "===Related terms===\n* {{plural of|it|casa}}\n"
        )
        assert lemma_reference(page, "it") is None

    def test_a_lemma_with_a_plain_definition_points_nowhere(self):
        page = "==Italian==\n\n===Verb===\n{{it-verb}}\n\n# to go\n"
        assert lemma_reference(page, "it") is None

    def test_older_entries_omit_the_language(self):
        page = (
            "==Italian==\n\n===Noun===\n{{head|it|noun form}}\n\n"
            "# {{plural of|casa}}\n"
        )
        found = lemma_reference(page, "it")
        assert found is not None
        assert found[0].lemma == "casa"
        assert found[0].language == "it"

    def test_nonlemma_marker_is_not_a_pointer(self):
        # {{nonlemma}} says "this is not a lemma" without naming one.
        page = "==Italian==\n\n===Verb===\n{{head|it|verb form}}\n\n# {{nonlemma}}\n"
        assert lemma_reference(page, "it") is None


class TestDefinitionStatements:
    """What a definition line declares, and how the target's shape decides it.

    Most Italian entries have no Etymology section: they state in the
    definition line that the page is a form of another word, or is formed from
    one. Reading that is not interpretation — it is a template.
    """

    @staticmethod
    def page(definition: str, part_of_speech: str = "Noun") -> str:
        return (
            f"==Italian==\n\n==={part_of_speech}===\n{{{{head}}}}\n\n"
            f"# {definition}\n"
        )

    def test_pointer_to_a_lemma(self):
        found = definition_statement(self.page("{{apoc of|it|fare}}"), "it")
        assert found.kind is Declaration.POINTER
        assert found.forms[0].lemma == "fare"
        assert found.wording == "apocopic form of"

    def test_short_alias_is_recognised(self):
        # `apoc of` is roughly as common as `apocopic form of`; missing it made
        # the scan fall through to a different part of speech entirely.
        assert definition_statement(self.page("{{apoc of|it|poco}}"), "it") is not None

    def test_diminutive_is_a_link_not_a_pointer(self):
        found = definition_statement(self.page("{{diminutive of|it|tubo}}"), "it")
        assert found.kind is Declaration.DERIVATION
        assert found.relation is Relation.DIMINUTIVE
        assert found.forms[0].lemma == "tubo"

    def test_contraction_keeps_both_sources(self):
        # `dal` is not a form of `da`: it is `da` + `il`. Picking one silently
        # is the mistake this whole area exists to remove.
        found = definition_statement(self.page("{{contraction of|it|da|il}}"), "it")
        assert found.kind is Declaration.CONTRACTION
        assert [f.lemma for f in found.forms] == ["da", "il"]

    def test_synonym_is_never_followed(self):
        # A synonym is a different word: following it would answer with someone
        # else's history.
        assert definition_statement(self.page("{{synonym of|it|cane}}"), "it") is None
        assert definition_statement(self.page("{{syn of|it|cane}}"), "it") is None


class TestTargetShape:
    """The decision rests on the target, not on the family of the template.

    Classifying by family gets the exceptions wrong both ways: some
    abbreviations expand to phrases, some initialisms point at a single word.
    A target that is not a lemma yields no declaration at all — since acronyms
    left the scope there is nothing an unfollowable target could produce.
    """

    @staticmethod
    def page(definition: str) -> str:
        return f"==Italian==\n\n===Noun===\n{{{{head}}}}\n\n# {definition}\n"

    def test_single_word_target_is_followed(self):
        found = definition_statement(self.page("{{abbreviation of|it|dottore}}"), "it")
        assert found.kind is Declaration.POINTER
        assert found.forms[0].lemma == "dottore"

    def test_phrase_target_yields_no_declaration(self):
        # «d.C.» stands for a phrase, not for a word with a history: nothing
        # to walk to, and nothing to state.
        assert (
            definition_statement(
                self.page("{{abbreviation of|it|[[dopo]] [[Cristo]]}}"), "it"
            )
            is None
        )

    def test_interwiki_target_never_becomes_a_page_request(self):
        # `w:it:…` is a link to Wikipedia. Asked of Wiktionary it would 404,
        # and the 404 would read as "no entry" — our limit dressed as silence.
        # The colon is what marks it unusable, which is why cleaning leaves it.
        assert (
            definition_statement(
                self.page("{{initialism of|it|w:it:Esercito Italiano}}"), "it"
            )
            is None
        )

    def test_two_spellings_are_one_target_with_variants(self):
        # `onza` and `oncia` are the same word written two ways, both from
        # Latin `uncia`; `onza` has no Italian section at all. A comma inside
        # one parameter is how Wiktionary writes "same slot, two spellings" —
        # where the targets are genuinely different words it uses separate
        # templates, as `po'` does.
        found = definition_statement(
            self.page("{{abbreviation of|it|onza,oncia}}"), "it"
        )
        assert found.kind is Declaration.POINTER
        assert found.forms[0].lemma == "onza"
        assert found.forms[0].variants == ("oncia",)

    def test_broken_wikilink_is_cleaned(self):
        # `[[regia` asked verbatim would 404.
        found = definition_statement(self.page("{{abbreviation of|it|[[regia}}"), "it")
        assert found.forms[0].lemma == "regia"

    def test_section_anchor_is_dropped(self):
        found = definition_statement(
            self.page("{{abbreviation of|it|[[Ente#Italian]]}}"), "it"
        )
        assert found.forms[0].lemma == "Ente"

    def test_nested_template_keeps_its_value(self):
        # Plain stripping would delete {{lw|…}} and leave an empty string.
        # Both an empty target and a phrase are dropped today, but for
        # different reasons, and the cleaning must keep them distinguishable
        # for whatever reads this next.
        assert _clean_target("{{lw|it|Banca Centrale Europea}}") == (
            "Banca Centrale Europea"
        )

    def test_hyphens_are_not_separators(self):
        # `Barletta-Andria-Trani` is one page title, not three targets.
        found = definition_statement(
            self.page("{{abbreviation of|it|Barletta-Andria-Trani}}"), "it"
        )
        assert found.forms[0].lemma == "Barletta-Andria-Trani"


class TestConnectives:
    """Adverbs that say how one link relates to the one before it.

    They are in the text, so reading them is evidence, not inference — which
    is why they are preferred to reordering the chain by a chronology of our
    own.
    """

    def test_ultimately_marks_the_link_as_distant(self):
        analysis = parse("Ultimately from {{der|it|la|focus}}.", "it")
        assert analysis.steps[0].skips_stages

    def test_a_plain_link_claims_adjacency(self):
        analysis = parse("From {{inh|it|la|focus}}.", "it")
        assert not analysis.steps[0].skips_stages

    def test_via_reverses_the_textual_order(self):
        # "From Arabic X via Spanish Y" reads: entry ← Y ← X. The form after
        # `via` is the nearer one, so it comes first in the chain.
        analysis = parse(
            "From {{der|it|ar|qahwa}} via {{bor|it|es|café}}.", "it"
        )
        assert [s.forms[0].language for s in analysis.steps] == ["es", "ar"]

    def test_via_is_reported(self):
        analysis = parse("From {{der|it|ar|qahwa}} via {{bor|it|es|café}}.", "it")
        assert any("intermediate stage" in note for note in analysis.notes)

    def test_itself_from_leaves_the_order_alone(self):
        # Positive evidence that the textual order is the order of the chain:
        # it confirms, so it must not disturb anything.
        analysis = parse(
            "From {{bor|it|ota|qahve}}, itself from {{der|it|ar|qahwa}}.", "it"
        )
        assert [s.forms[0].language for s in analysis.steps] == ["ota", "ar"]
        assert not any(s.skips_stages for s in analysis.steps)

    def test_originally_is_not_a_distance_marker(self):
        # In Wiktionary's prose it is nearly always semantic — "originally
        # meaning to strike" — and would flag a sentence about no stage at all.
        analysis = parse(
            "From {{inh|it|la|battuere}}, originally meaning to strike.", "it"
        )
        assert not analysis.steps[0].skips_stages

    def test_an_adverb_governs_only_the_template_it_introduces(self):
        analysis = parse(
            "Ultimately from {{der|it|ine-pro|*bʰer-}}. "
            "The word entered Italian from {{inh|it|la|ferre}}.",
            "it",
        )
        assert analysis.steps[0].skips_stages
        assert not analysis.steps[1].skips_stages


class TestFormLeftToTheProse:
    """A dash in the lemma slot means the form is named in the sentence.

    Wiktionary's documented idiom for "derived from this language, the form
    given separately". The mention repeats the same language code, and that is
    the whole of the link — no formula to interpret.
    """

    def test_the_mention_supplies_the_form(self):
        analysis = parse(
            "Ultimately from the {{der|it|la|-}} name of the location, "
            "{{m|la|Augusta Praetoria}}.",
            "it",
        )
        assert len(analysis.steps) == 1
        assert analysis.steps[0].forms[0].lemma == "Augusta Praetoria"
        assert analysis.steps[0].forms[0].language == "la"

    def test_two_mentions_are_two_parents(self):
        analysis = parse(
            "From the {{der|it|gem-pro|-}} elements {{m|gem-pro|*gunþiz||battle}} "
            "and {{m|gem-pro|*harduz||hard, brave}}.",
            "it",
        )
        step = analysis.steps[0]
        assert step.branching
        assert [f.lemma for f in step.forms] == ["*gunþiz", "*harduz"]
        assert step.forms[0].gloss == "battle"

    def test_a_different_language_code_supplies_nothing(self):
        # `brezza`: a Vulgar Latin derivation followed by {{m|it|…}}. The codes
        # disagree, so nothing is promoted — the entry yields no link rather
        # than a wrong one.
        analysis = parse(
            "From {{uder|it|la-vul|-}} {{m|it|*brevidia}}.", "it"
        )
        assert analysis.steps[0].forms[0].lemma == ""

    def test_cognates_are_not_collected(self):
        # `Aosta` lists cognates after the mention. Collection stops at the
        # first template that does not match, so they stay out.
        analysis = parse(
            "From the {{der|it|la|-}} name, {{m|la|Augusta}}. "
            "Cognate with {{cog|fr|Aoste}}, {{m|la|alius}}.",
            "it",
        )
        assert [f.lemma for f in analysis.steps[0].forms] == ["Augusta"]

    def test_a_dash_with_nothing_after_it_stays_empty(self):
        # `piranha`: the dash does not promise that a form follows.
        analysis = parse("From {{der|it|tpw|-}}.", "it")
        assert analysis.steps[0].forms[0].lemma == ""

    def test_declared_uncertainty_still_wins(self):
        # The promoted mention goes through the same order of authority as
        # everything else: promoting it around that machinery is how `bravo`
        # and `dado` were broken in the first place.
        analysis = parse(
            "The origin is {{unc|it|nocap=1}}. Alternatively from "
            "{{uder|it|la-vul|-}} {{m|la-vul|*brevidia}}.",
            "it",
        )
        assert analysis.uncertain
        assert analysis.steps == []
        assert [h.form.lemma for h in analysis.hypotheses] == ["*brevidia"]


class TestConditioningMarkers:
    """What the source proposes is not what the source states.

    An entry that offers two candidates without choosing has not declared a
    chain. Concatenating one picks a side the source declined to pick, and
    drops the other in silence — which is how `cavolo` came to show Neapolitan
    as the ancestor of Late Latin.
    """

    def test_a_proposal_is_not_a_link(self):
        analysis = parse("Possibly from {{bor|it|nap|cavolo}}.", "it")
        assert analysis.steps == []
        assert [h.form.lemma for h in analysis.hypotheses] == ["cavolo"]

    def test_the_marker_covers_every_candidate_it_introduces(self):
        # "Possibly X or Y" is one marker over two candidates: releasing it at
        # the comma would make the second one a fact.
        analysis = parse(
            "Possibly {{bor|it|nap|cavolo}} or {{bor|it|scn|cavulu}}.", "it"
        )
        assert analysis.steps == []
        assert [h.form.lemma for h in analysis.hypotheses] == ["cavolo", "cavulu"]

    def test_a_full_stop_releases_the_marker(self):
        analysis = parse(
            "Possibly {{bor|it|nap|cavolo}}. From {{inh|it|la|caulis}}.", "it"
        )
        assert [s.forms[0].lemma for s in analysis.steps] == ["caulis"]
        assert [h.form.lemma for h in analysis.hypotheses] == ["cavolo"]

    def test_the_certain_part_of_a_mixed_entry_survives(self):
        # `cavolo`: two asserted links, then two candidates for a stage.
        analysis = parse(
            "{{der+|it|la-lat|caulus}}, from {{der|it|la|caulis}}, through a "
            "southern Italian language. Possibly {{bor+|it|nap|cavolo}} or "
            "{{bor|it|scn|cavulu}}.",
            "it",
        )
        assert [s.forms[0].lemma for s in analysis.steps] == ["caulus", "caulis"]
        assert [h.form.lemma for h in analysis.hypotheses] == ["cavolo", "cavulu"]

    def test_a_bare_conjunction_is_not_worth_quoting(self):
        # The second candidate is introduced by nothing but "or": quoting that
        # as the source's reasoning says less than saying nothing.
        analysis = parse(
            "Possibly {{bor|it|nap|cavolo}} or {{bor|it|scn|cavulu}}.", "it"
        )
        assert analysis.hypotheses[1].attribution is None


class TestLemmaIsNeverCorrupted:
    """A lemma carrying our own markup becomes a page title that cannot exist.

    The request comes back 404 and the chain closes on a *false* "no entry" —
    our formatting mistaken for a fact about the language.
    """

    def test_inline_annotations_leave_the_lemma(self):
        analysis = parse("{{der|it|ine-pro|*h₂el-<t:to grow><id:grow>}}", "it")
        form = analysis.steps[0].forms[0]
        assert form.lemma == "*h₂el-"
        assert form.gloss == "to grow"

    def test_an_alt_annotation_supplies_the_form(self):
        analysis = parse("{{inh|it|la|forma<alt:formam>}}", "it")
        assert analysis.steps[0].forms[0].lemma == "forma"

    def test_named_parameters_still_win(self):
        analysis = parse("{{der|it|la|caulis|t=stalk}}", "it")
        form = analysis.steps[0].forms[0]
        assert (form.lemma, form.gloss) == ("caulis", "stalk")

    def test_an_unknown_language_code_is_still_split_off(self):
        # Keeping `pgd:𐨭𐨐𐨪` whole labelled the form with the *parent's*
        # language, which is an assertion, and a false one.
        analysis = parse("{{etymon|pal|:bor|pgd:𐨭𐨐𐨪}}", "pal")
        form = analysis.steps[0].forms[0]
        assert form.lemma == "𐨭𐨐𐨪"
        assert form.language == "pgd"

    def test_a_known_code_behaves_as_before(self):
        analysis = parse("{{etymon|la|:der|ine-pro:*keh₂ulis}}", "la")
        form = analysis.steps[0].forms[0]
        assert (form.lemma, form.language) == ("*keh₂ulis", "ine-pro")


class TestSeveralSpellingsInOneParameter:
    """One parameter can hold several spellings of the same form.

    `{{inh|en|enm|[[-ere]], [[-er]]}}` is one suffix written two ways, not two
    ancestors. Joined, the string becomes a page title that cannot exist and
    the chain closes on a false "no entry" — the same failure as `onza,oncia`,
    in the variant where the separator is a comma *and a space*, inside
    wikilinks.
    """

    def test_the_first_spelling_is_the_lemma(self):
        analysis = parse("{{inh+|en|enm|[[-ere]], [[-er]]|id=agentive}}", "en")
        form = analysis.steps[0].forms[0]
        assert form.lemma == "-ere"
        assert form.variants == ("-er",)

    def test_a_bare_comma_separates_too(self):
        analysis = parse("{{inh|it|la|forma, formam}}", "it")
        assert analysis.steps[0].forms[0].lemma == "forma"
        assert analysis.steps[0].forms[0].variants == ("formam",)

    def test_a_single_form_has_no_variants(self):
        analysis = parse("{{der|it|la|caulis}}", "it")
        assert analysis.steps[0].forms[0].variants == ()

    def test_the_lemma_never_carries_the_separator(self):
        # This is what made the title impossible.
        for source in (
            "{{inh+|en|enm|[[-ere]], [[-er]]}}",
            "{{inh|it|la|forma, formam}}",
        ):
            assert "," not in parse(source, "en").steps[0].forms[0].lemma


class TestQualifierNeverReachesTheTitle:
    """A parenthesised gloss disambiguates a form; it is not part of it.

    `*ḱel- (cover)` is the root `*ḱel-`, told apart from a homonym. Left in
    the lemma it goes into the page title, which then cannot exist — the same
    failure as the inline annotations, in the notation that predates them.
    """

    def test_a_root_keeps_only_its_form(self):
        analysis = parse("{{root|it|ine-pro|*ḱel- (cover)}}", "it")
        assert analysis.root.lemma == "*ḱel-"
        assert analysis.root.gloss == "cover"

    def test_a_derivation_too(self):
        analysis = parse("{{der|it|ine-pro|*keyh₂- (to lie down)}}", "it")
        form = analysis.steps[0].forms[0]
        assert form.lemma == "*keyh₂-"
        assert form.gloss == "to lie down"

    def test_a_form_without_brackets_is_untouched(self):
        analysis = parse("{{root|it|ine-pro|*h₂eḱs-}}", "it")
        assert analysis.root.lemma == "*h₂eḱs-"

    def test_the_title_becomes_reachable(self):
        from etimo.languages import page_title

        analysis = parse("{{root|it|ine-pro|*ḱel- (cover)}}", "it")
        title = page_title(analysis.root.lemma, analysis.root.language)
        assert title == "Reconstruction:Proto-Indo-European/ḱel-"
        assert "(" not in title


class TestConditioningReachesEveryShape:
    """The conditioning was wired for linear relations only.

    Every case we started from — `cavolo`, `pizza`, `bravo` — was a relation
    between languages, so "marker, then relation" was the only shape it knew.
    A proposal about how a word was *built* is the same claim in a different
    shape, and an alternative offered *between* two templates is a third.
    """

    def test_a_conditioned_word_formation_is_a_conjecture(self):
        # `rodomonte`: "apparently from rodo + monte" proposes an analysis
        # into parts; it does not assert one.
        analysis = parse(
            "From {{m|it|Rodomonte}}, apparently from "
            "{{af|it|rodo|monte|t1=I roll (away)|t2=mountain}}.",
            "it",
        )
        assert analysis.steps == []
        assert [h.form.lemma for h in analysis.hypotheses] == ["rodo", "monte"]

    def test_two_analyses_joined_by_or_are_both_conjectures(self):
        # `dipelare`: an Italian formation *or* an inherited Latin verb. The
        # entry declines to choose, so neither may be drawn as the chain.
        analysis = parse(
            "From {{af|it|di-|pelo|-are}} or from {{inh|it|la|dēpilō}}.", "it"
        )
        assert analysis.steps == []
        assert [h.form.lemma for h in analysis.hypotheses] == [
            "di-",
            "pelo",
            "-are",
            "dēpilō",
        ]

    def test_an_alternative_does_not_demote_an_asserted_chain(self):
        # `cavolo`: two asserted links, a full stop, then two candidates joined
        # by "or". The "or" belongs to the candidates, not to the chain.
        analysis = parse(
            "{{der+|it|la-lat|caulus}}, from {{der|it|la|caulis}}. "
            "Possibly {{bor+|it|nap|cavolo}} or {{bor|it|scn|cavulu}}.",
            "it",
        )
        assert [s.forms[0].lemma for s in analysis.steps] == ["caulus", "caulis"]
        assert [h.form.lemma for h in analysis.hypotheses] == ["cavolo", "cavulu"]

    def test_a_modal_on_a_circumstance_conditions_nothing(self):
        # `brindare`: "probably introduced by German mercenaries" qualifies
        # *how* the borrowing happened, not which word it came from. The chain
        # is asserted and stays a chain.
        analysis = parse(
            "{{bor+|it|es|brindar}}, from {{der|it|de|bring dir's}}, "
            "probably introduced by German mercenaries in the 16th c.",
            "it",
        )
        assert [f.lemma for s in analysis.steps for f in s.forms] == [
            "brindar",
            "bring dir's",
        ]
        assert analysis.hypotheses == []


class TestTheQuotedSentenceIsTheEntrysOwn:
    """What we print as the entry's words must be the entry's words.

    That line sits under a terminal saying "we could not read this — here is
    what it says". Deleting the templates leaves only the joints: `From
    {{af|it|di-|pelo|-are}} or from {{inh|it|la|dēpilō}}` became "From or
    from", a sentence nobody wrote — a false claim in the one place whose
    purpose is fidelity.
    """

    def test_templates_are_rendered_not_removed(self):
        analysis = parse(
            "From {{af|it|di-|pelo|-are}} or from {{inh|it|la|dēpilō}}.", "it"
        )
        assert analysis.text == "From di- + pelo + -are or from dēpilō."

    def test_a_mention_keeps_its_place_in_the_sentence(self):
        analysis = parse(
            "From {{m|it|Rodomonte}}, apparently from {{af|it|rodo|monte}}.", "it"
        )
        assert analysis.text == "From Rodomonte, apparently from rodo + monte."

    def test_prose_entries_are_unaffected(self):
        analysis = parse("From loglio.", "it")
        assert analysis.text == "From loglio."

    def test_rendering_does_not_turn_markup_into_unread_prose(self):
        # A section that is only templates we understood has no unread prose.
        # Judging that on the rendered text would count our own rendering as
        # something we failed to read.
        analysis = parse("{{doublet|itc-pro|x}}", "itc-pro")
        assert analysis.prose.strip() == ""
        assert analysis.text  # still shown, still readable


class TestCompositionWrittenWithSeparateTemplates:
    """`X + Y` between two relations is one compound, not two links.

    `Lygodium` is «{{der|mul|grc|λύγος}} + {{der|mul|grc|εἶδος}}» — willow plus
    form. Read as a chain it becomes "from willow, from form", and the second
    element, demoted to a reserve, is discarded by the next entry: the source
    named it and the output lost it.
    """

    def test_a_plus_joins_two_relations_of_the_same_kind(self):
        analysis = parse("{{der|mul|grc|λύγος}} + {{der|mul|grc|εἶδος}}", "mul")
        assert len(analysis.steps) == 1
        assert [f.lemma for f in analysis.steps[0].forms] == ["λύγος", "εἶδος"]
        assert analysis.steps[0].branching

    def test_different_relations_are_two_claims(self):
        # Inheriting from Latin and borrowing from German are different
        # statements; a `+` does not make them one compound.
        analysis = parse("{{inh|it|la|x}} + {{bor|it|de|y}}", "it")
        assert len(analysis.steps) == 2

    def test_different_languages_are_two_claims(self):
        analysis = parse("{{der|it|grc|a}} + {{der|it|la|b}}", "it")
        assert len(analysis.steps) == 2

    def test_a_plus_after_a_full_stop_belongs_to_another_sentence(self):
        analysis = parse("{{der|it|la|a}}. + {{der|it|la|b}}", "it")
        assert len(analysis.steps) == 2


class TestSurfaceAnalysisInProse:
    """«By surface analysis, X + Y» is not a step, whoever writes it.

    `{{surf}}` was already read as a remark. The same statement spelled out in
    prose was read as a link, so `strumentale` — inherited whole from Latin —
    also claimed descent from `strumento`.
    """

    def test_it_becomes_a_note_not_a_step(self):
        analysis = parse(
            "{{inh+|it|la|īnstrūmentālis}}. By surface analysis, "
            "{{af|it|strumento|-ale}}.",
            "it",
        )
        assert [f.lemma for step in analysis.steps for f in step.forms] == [
            "īnstrūmentālis"
        ]
        assert any("strumento" in note for note in analysis.notes)

    def test_an_ordinary_affixation_is_untouched(self):
        # The marker must not silence a composition that has none.
        analysis = parse("From {{af|it|capo|lavoro}}.", "it")
        assert [f.lemma for step in analysis.steps for f in step.forms] == [
            "capo",
            "lavoro",
        ]

    def test_the_marker_does_not_reach_past_a_full_stop(self):
        # "By surface analysis" belongs to its own sentence; a step in the
        # sentence after it was never qualified by it.
        analysis = parse(
            "By surface analysis, {{af|it|a-|mare}}. From {{af|it|capo|lavoro}}.",
            "it",
        )
        assert [f.lemma for step in analysis.steps for f in step.forms] == [
            "capo",
            "lavoro",
        ]


class TestSynchronicMarkersAndTheirLookalike:
    """The marker list, and the one that must stay off it."""

    def test_equivalent_to_is_synchronic(self):
        # The commonest of these formulas: `minigolf` is taken whole from
        # English, and mini- + golf is how it parses, not where it came from.
        analysis = parse(
            "{{ubor|it|en|minigolf}}, equivalent to {{af|it|mini-|golf}}.", "it"
        )
        assert [f.lemma for step in analysis.steps for f in step.forms] == ["minigolf"]

    def test_reanalysed_is_not_silenced(self):
        # A reanalysis is a diachronic event, not a synchronic description:
        # boundaries actually moved. It resembles the markers above and means
        # the opposite of them, so it must remain a step.
        analysis = parse("From {{inh|it|la|x}}, reanalysed as {{af|it|a|b}}.", "it")
        assert [f.lemma for step in analysis.steps for f in step.forms] == [
            "x",
            "a",
            "b",
        ]


@pytest.mark.xfail(
    strict=True,
    reason="known defect: a theory attributed to a named scholar is read as an "
    "asserted step. `dō` says «Another theory, advanced by the linguist Jay H. "
    "Jasanoff, suggests that the form derives from *dowjō», and *dowjō joins "
    "the chain as though the entry had claimed it. The conditioning markers "
    "cover possibly/perhaps/probably/maybe/apparently/alternatively and none "
    "of the ways an entry attributes a proposal to someone. Found because the "
    "reserve began carrying it across pages and `tradito` reported the two as "
    "disagreeing — the note was false, the step underneath it was too. Left "
    "for a decision on _CONDITIONING, which governs what counts as asserted "
    "and is not a thing to widen at the end of a day.\n\n"
    "Whoever takes it on: the marker is the **verb**, not the attribution. A "
    "name can qualify or support — «Jasanoff suggests» proposes, «According "
    "to Ernout-Meillet, from X» cites in support — and it is the verb that "
    "says which. Measured on Italian entries, `according to` appears in 2498 "
    "pages and 0 of 20 sampled had it in an Etymology section, so it earns "
    "nothing and risks demoting settled etymologies. Candidates worth having: "
    "suggests, proposes, has been proposed, argues, another theory, some "
    "scholars, posits, speculates, derived by others from — the last found on "
    "`*māros`, whose «Derived by others from *moh₁-ro-s» the walk carried "
    "along as though the entry had asserted it.\n\n"
    "Two traps, both from real entries. **Scope**: `frasca` mixes «A "
    "pre-Roman origin has been proposed» with firmly stated claims in one "
    "section, so the qualification must end at the full stop or it demotes "
    "everything after it. **Object**: `bravo` says «George Nicholson argues "
    "the opposite» — the verb qualifies, but what follows is a *contrary* "
    "thesis, so demoting what comes after would hit the wrong claim. The "
    "class this would genuinely add is ten to fifteen entries; on most of the "
    "rest an explicit {{unk}} already wins.",
)
def test_a_theory_attributed_to_a_scholar_is_not_a_step():
    analysis = parse(
        "From {{inh|la|itc-pro|*didō}}. Another theory, advanced by the "
        "linguist Jay H. Jasanoff, suggests that the form derives from "
        "{{inh|la|itc-pro|*dowjō}}.",
        "la",
    )
    assert [f.lemma for step in analysis.steps for f in step.forms] == ["*didō"]
    assert [h.form.lemma for h in analysis.hypotheses] == ["*dowjō"]


class TestTheTemplateNamesTheLanguage:
    """A component belongs to the language its template declares.

    Found through `dogaressa`, and it is a C2 violation of the plainest kind:
    the form was being labelled with the section's language instead of its
    own. The walk then read Venetan as standing above Latin and reported two
    entries as contradicting each other.
    """

    def test_a_foreign_analysis_keeps_its_own_language(self):
        analysis = parse("From {{uder|vec|la|x}}, from {{af|la|dux|-issa}}.", "vec")
        components = analysis.steps[1].forms
        assert [(f.lemma, f.language) for f in components] == [
            ("dux", "la"),
            ("-issa", "la"),
        ]

    def test_the_ordinary_case_is_unchanged(self):
        analysis = parse("From {{af|it|capo|lavoro}}.", "it")
        assert {f.language for f in analysis.steps[0].forms} == {"it"}

    def test_an_explicit_lang_parameter_still_wins(self):
        analysis = parse("From {{af|it|capo|lavoro|lang2=la}}.", "it")
        assert [(f.lemma, f.language) for f in analysis.steps[0].forms] == [
            ("capo", "it"),
            ("lavoro", "la"),
        ]
