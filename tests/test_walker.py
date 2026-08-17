"""The recursive walk and its stopping criteria.

Every test runs against `DictSource`, that is against fabricated pages: what
matters here is the walker's behaviour, not the content of Wiktionary.
"""

from typing import ClassVar

import pytest

from etimo.languages import impossible_order
from etimo.models import Relation, Terminal
from etimo.walker import Reconstructor
from etimo.wiktionary import DictSource


def entry(wiktionary_language: str, etymology: str, heading="Etymology") -> str:
    """Compose a minimal but structurally faithful page."""
    return (
        f"=={wiktionary_language}==\n\n==={heading}===\n{etymology}\n\n"
        "===Noun===\n{{head}}\n"
    )


COMPLETE_CHAIN = {
    "fuoco": entry("Italian", "From {{inh|it|la|focus|t=hearth}}."),
    "focus": entry("Latin", "The origin is {{unc|la|nocap=1}}."),
}


class TestSimpleWalk:
    def test_walks_to_the_terminal(self):
        result = Reconstructor(DictSource(COMPLETE_CHAIN)).reconstruct("fuoco")
        chain = result.start.main_chain()

        assert [n.form.lemma for n in chain] == ["fuoco", "focus"]
        assert chain[1].relation is Relation.INHERITED
        assert chain[1].terminal is Terminal.UNCERTAIN_ORIGIN
        assert result.steps == 1

    def test_uncertain_terminal_is_a_fact_not_a_limit(self):
        result = Reconstructor(DictSource(COMPLETE_CHAIN)).reconstruct("fuoco")
        assert result.start.terminals()[0].terminal.is_linguistic

    def test_missing_entry_is_a_limit_not_a_fact(self):
        source = DictSource({"x": entry("Italian", "From {{inh|it|la|nonexistent}}.")})
        result = Reconstructor(source).reconstruct("x")
        terminal = result.start.terminals()[0].terminal
        assert terminal is Terminal.ENTRY_MISSING
        assert not terminal.is_linguistic


class TestLinguisticTerminals:
    def test_proto_form_whose_entry_says_no_more_is_a_reconstructed_form(self):
        # Reading a proto-form's entry and finding nothing beyond is not a gap:
        # it is where comparative reconstruction stops.
        source = DictSource(
            {
                "pater": entry("Latin", "From {{inh|la|itc-pro|*patēr}}."),
                # The entry is there and says nothing further about the origin.
                "Reconstruction:Proto-Italic/patēr": entry(
                    "Proto-Italic", "{{doublet|itc-pro|x}}"
                ),
            }
        )
        leaf = Reconstructor(source).reconstruct("pater", "la").start.terminals()[0]
        assert leaf.form.lemma == "*patēr"
        assert leaf.terminal is Terminal.RECONSTRUCTED_FORM
        assert leaf.terminal.is_linguistic

    def test_proto_form_without_an_entry_is_a_limit_not_a_fact(self):
        # We never read anything: silence we did not hear is no evidence that
        # the language falls silent.
        source = DictSource({"pater": entry("Latin", "From {{inh|la|itc-pro|*patēr}}.")})
        leaf = Reconstructor(source).reconstruct("pater", "la").start.terminals()[0]
        assert leaf.terminal is Terminal.ENTRY_MISSING
        assert not leaf.terminal.is_linguistic

    def test_reconstruction_in_an_unregistered_language_is_not_a_root(self):
        # `Reconstruction:bnt-pro/...` cannot exist: the path needs the
        # canonical name. The gap is in our table, not in the language.
        source = DictSource({"x": entry("Italian", "From {{der|it|bnt-pro|*abc}}.")})
        leaf = Reconstructor(source).reconstruct("x").start.terminals()[0]
        assert leaf.terminal is Terminal.LANGUAGE_MISSING
        assert not leaf.terminal.is_linguistic

    def test_language_without_form_is_a_limit_of_the_source(self):
        # The entry does say where the word came from — it just does not say
        # what the word was. We read that correctly, so the terminal must not
        # claim the language had nothing left to give.
        source = DictSource({"caffè": entry("Italian", "From {{der|it|omv|-}}.")})
        result = Reconstructor(source).reconstruct("caffè")
        assert result.start.terminal is Terminal.FORM_NOT_GIVEN
        assert not result.start.terminal.is_linguistic
        assert "does not give" in result.start.note
        # No empty link may appear in the tree.
        assert result.start.children == []

    def test_stage_without_form_is_crossed_not_obeyed(self):
        # "from an Eastern Iranian language, from *wrinǰiš": the first template
        # cites no form but the second does, and stopping at the first would
        # lose the link.
        source = DictSource(
            {
                "ὄρυζα": entry(
                    "Ancient Greek",
                    "A borrowing from an Eastern {{der|grc|ira|-}} language, "
                    "from {{der|grc|ira-pro|*wrinǰiš}}.",
                )
            }
        )
        result = Reconstructor(source).reconstruct("ὄρυζα", "grc")
        assert result.start.children[0].form.lemma == "*wrinǰiš"
        # The crossed stage stays declared, so a passage the source describes
        # as mediated does not look direct.
        assert "does not give" in result.start.note


class TestBranching:
    def test_compound_yields_two_branches(self):
        source = DictSource(
            {
                "capolavoro": entry("Italian", "{{af|it|capo|lavoro}}"),
                "capo": entry("Italian", "From {{inh|it|la|caput}}."),
                "lavoro": entry("Italian", "From {{der|it|la|labor}}."),
            }
        )
        result = Reconstructor(source).reconstruct("capolavoro")
        assert [c.form.lemma for c in result.start.children] == ["capo", "lavoro"]
        assert len(result.start.terminals()) == 2

    def test_compounds_can_be_left_alone(self):
        source = DictSource({"capolavoro": entry("Italian", "{{af|it|capo|lavoro}}")})
        result = Reconstructor(source, follow_compounds=False).reconstruct("capolavoro")
        assert result.start.children == []
        assert result.start.terminal is Terminal.DATA_EXHAUSTED


class TestSafeguards:
    def test_circular_reference_interrupted(self):
        source = DictSource(
            {
                "a": entry("Italian", "From {{der|it|it|b}}."),
                "b": entry("Italian", "From {{der|it|it|a}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert result.start.terminals()[0].terminal is Terminal.CYCLE

    def test_maximum_depth_respected(self):
        # A long chain: every entry points to the next.
        pages = {
            f"p{i}": entry("Italian", f"From {{{{der|it|it|p{i + 1}}}}}.")
            for i in range(10)
        }
        result = Reconstructor(DictSource(pages), max_depth=3).reconstruct("p0")
        assert result.steps == 3
        assert result.start.terminals()[0].terminal is Terminal.DEPTH_LIMIT

    def test_one_request_per_form(self):
        # In-memory deduplication is what makes the walk affordable: within a
        # single run an entry is downloaded once.
        source = DictSource(
            {
                "x": entry("Italian", "{{af|it|y|y}}"),
                "y": entry("Italian", "From {{inh|it|la|ipsum}}."),
                "ipsum": entry("Latin", "Of unknown origin."),
            }
        )
        Reconstructor(source).reconstruct("x")
        assert source.requests_made == 3

    def test_page_shared_by_two_languages_downloaded_once(self):
        # "patria" is both Italian and Latin in the same document: two
        # sections, one page to fetch.
        page = (
            "==Italian==\n\n===Etymology===\nFrom {{der|it|la|patria}}.\n\n"
            "==Latin==\n\n===Etymology===\nOf uncertain origin.\n"
        )
        source = DictSource({"patria": page})
        result = Reconstructor(source).reconstruct("patria")
        assert source.requests_made == 1
        assert result.start.children[0].terminal is Terminal.UNCERTAIN_ORIGIN


class TestProvenance:
    """The carried chain and its attribution.

    When an ancestor has no entry of its own we continue with what the starting
    entry declares — but who declares it must be stated.
    """

    ENTRY: ClassVar[dict] = {
        "padre": entry(
            "Italian", "From {{der|it|roa-oit|patre}}, from {{inh|it|la|pater}}."
        )
    }

    def test_falls_back_to_the_reported_chain(self):
        result = Reconstructor(DictSource(self.ENTRY)).reconstruct("padre")
        chain = result.start.main_chain()
        assert [n.form.lemma for n in chain] == ["padre", "patre", "pater"]

    def test_credited_to_the_entry_that_states_it(self):
        result = Reconstructor(DictSource(self.ENTRY)).reconstruct("padre")
        pater = result.start.main_chain()[2]
        # It is "padre" that reports the passage, not "patre", which is silent.
        assert "«padre»" in pater.note

    def test_carried_chain_does_not_override_an_explicit_statement(self):
        # If the source declares the origin uncertain, that is the conclusion:
        # going on with second-hand information would replace a fact with a
        # conjecture.
        source = DictSource(
            {
                "x": entry(
                    "Italian", "From {{der|it|la|medius}}, from {{der|it|la|ultimus}}."
                ),
                "medius": entry("Latin", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("x")
        chain = result.start.main_chain()
        assert [n.form.lemma for n in chain] == ["x", "medius"]
        assert chain[-1].terminal is Terminal.UNCERTAIN_ORIGIN


class TestMultipleSenses:
    PAGE = (
        "==Italian==\n\n===Etymology 1===\n{{inh|it|la|rīsus}}.\n\n"
        "===Etymology 2===\n{{inh|it|la-lat|oryza}}.\n"
    )

    @pytest.mark.parametrize("sense, expected", [(1, "rīsus"), (2, "oryza")])
    def test_sense_selection(self, sense, expected):
        source = DictSource({"riso": self.PAGE})
        result = Reconstructor(source).reconstruct("riso", sense=sense)
        assert result.start.children[0].form.lemma == expected
        assert result.available_senses == 2

    def test_sense_out_of_range_falls_back_to_the_last(self):
        source = DictSource({"riso": self.PAGE})
        assert Reconstructor(source).reconstruct("riso", sense=99).chosen_sense == 2


def inflected(
    target: str, wording: str = "past participle of", etymology: str = ""
) -> str:
    """A page that is a form of another word.

    The pointer lives among the definitions, under the part-of-speech heading —
    never in an Etymology section, which is exactly why it used to be missed.
    """
    head = f"===Etymology===\n{etymology}\n\n" if etymology else ""
    return (
        f"==Italian==\n\n{head}===Verb===\n{{{{head|it|verb form}}}}\n\n"
        f"# {{{{{wording}|it|{target}}}}}\n"
    )


class TestLemmaResolution:
    """Inflected forms carry no etymology; they point at the one that does.

    Most Italian entries are inflected forms, so this is not an edge case: it
    is the shape of the majority of the dictionary.
    """

    def test_form_resolves_to_its_lemma(self):
        source = DictSource(
            {
                "andato": inflected("andare"),
                "andare": entry("Italian", "From {{inh|it|la|ambitare}}."),
            }
        )
        result = Reconstructor(source).reconstruct("andato")

        assert result.resolved
        assert result.asked_for.lemma == "andato"
        assert result.start.form.lemma == "andare"
        assert "past participle of «andare»" in result.resolution

    def test_the_form_is_not_a_link_of_the_chain(self):
        # `andato` does not descend from `andare`: it is the same word
        # inflected. Counting it as a step would be a category error.
        source = DictSource(
            {
                "andato": inflected("andare"),
                "andare": entry("Italian", "From {{inh|it|la|ambitare}}."),
            }
        )
        result = Reconstructor(source).reconstruct("andato")
        assert [n.form.lemma for n in result.start.main_chain()] == [
            "andare",
            "ambitare",
        ]

    def test_own_etymology_beats_the_pointer(self):
        # `detto` is both a past participle and a word with a history of its
        # own: direct evidence wins over a cross-reference.
        source = DictSource(
            {
                "detto": inflected("dire", etymology="From {{inh|it|la|dictus}}."),
                "dire": entry("Italian", "From {{inh|it|la|dicere}}."),
                "dictus": entry("Latin", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("detto")

        assert not result.resolved
        assert result.start.children[0].form.lemma == "dictus"

    def test_pointers_may_chain(self):
        # A feminine of a participle of a verb: only the last one has a history.
        source = DictSource(
            {
                "amata": inflected("amato", "feminine singular of"),
                "amato": inflected("amare"),
                "amare": entry("Italian", "From {{inh|it|la|amare}}."),
            }
        )
        result = Reconstructor(source).reconstruct("amata")

        assert result.start.form.lemma == "amare"
        assert "feminine singular of «amato»" in result.resolution
        assert "past participle of «amare»" in result.resolution

    def test_mutual_pointers_do_not_loop(self):
        source = DictSource(
            {
                "a": inflected("b"),
                "b": inflected("a"),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        # It stops rather than spinning; nothing was found, and it says so.
        assert result.start.terminal is not None
        assert not result.start.terminal.is_linguistic

    def test_resolution_can_be_declined(self):
        source = DictSource(
            {
                "andato": inflected("andare"),
                "andare": entry("Italian", "From {{inh|it|la|ambitare}}."),
            }
        )
        result = Reconstructor(source).reconstruct("andato", follow_lemma=False)

        assert not result.resolved
        assert result.start.form.lemma == "andato"
        assert result.start.terminal is Terminal.ETYMOLOGY_MISSING

    def test_missing_lemma_page_is_not_hidden(self):
        # The pointer is followed, the target has no entry: that is a limit of
        # the source and must be reported as one.
        source = DictSource({"andato": inflected("andare")})
        result = Reconstructor(source).reconstruct("andato")
        assert result.start.terminal is Terminal.ENTRY_MISSING
        assert not result.start.terminal.is_linguistic


class TestChronology:
    """An entry can state an order that cannot be.

    Modern German is not the ancestor of Lombardic. The tool reports the
    contradiction and leaves the chain as the source gave it: rearranging it
    would replace the source's claim with ours.
    """

    def test_an_impossible_link_is_not_drawn(self):
        # Knowing a link cannot have happened and drawing it anyway asserts a
        # descent the program has already refuted.
        source = DictSource(
            {
                "banca": entry("Italian", "From {{der|it|lng|banka}}."),
                "banka": entry("Lombardic", "From {{der|lng|de|Bank}}."),
            }
        )
        result = Reconstructor(source).reconstruct("banca")
        lombardic = result.start.main_chain()[1]
        assert lombardic.form.language == "lng"
        assert lombardic.children == [], "the German link must not be a child"

    def test_the_refused_form_is_kept_as_a_conjecture(self):
        # The entry does mention it; it just cannot be an ancestor.
        source = DictSource(
            {
                "banca": entry("Italian", "From {{der|it|lng|banka}}."),
                "banka": entry("Lombardic", "From {{der|lng|de|Bank}}."),
            }
        )
        result = Reconstructor(source).reconstruct("banca")
        lombardic = result.start.main_chain()[1]
        assert [h.form.lemma for h in lombardic.hypotheses] == ["Bank"]
        assert "not drawn as a link" in lombardic.hypotheses[0].attribution

    def test_the_chain_is_not_rearranged(self):
        # Refused, not reordered: we do not put the link somewhere else that we
        # find more plausible.
        source = DictSource(
            {
                "banca": entry("Italian", "From {{der|it|lng|banka}}."),
                "banka": entry("Lombardic", "From {{der|lng|de|Bank}}."),
            }
        )
        result = Reconstructor(source).reconstruct("banca")
        assert [n.form.lemma for n in result.start.main_chain()] == ["banca", "banka"]

    def test_a_normal_order_says_nothing(self):
        source = DictSource(
            {
                "fuoco": entry("Italian", "From {{inh|it|la|focus}}."),
                "focus": entry("Latin", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("fuoco")
        assert result.start.main_chain()[1].note is None

    def test_unrelated_families_are_never_compared(self):
        # Arabic and Latin have no common yardstick: the check must stay quiet.
        source = DictSource(
            {
                "x": entry("Italian", "From {{der|it|ar|qahwa}}."),
                "qahwa": entry("Arabic", "From {{der|ar|la|focus}}."),
            }
        )
        result = Reconstructor(source).reconstruct("x")
        latin = result.start.main_chain()[2]
        assert latin.note is None or "later of the two" not in latin.note


class TestDefinitionLineStatements:
    """The four things a definition line can say, and the four answers."""

    @staticmethod
    def page(definition: str, part_of_speech: str = "Noun") -> str:
        return (
            f"==Italian==\n\n==={part_of_speech}===\n{{{{head}}}}\n\n"
            f"# {definition}\n"
        )

    def test_diminutive_becomes_a_link(self):
        source = DictSource(
            {
                "tubicino": self.page("{{diminutive of|it|tubo}}"),
                "tubo": entry("Italian", "From {{inh|it|la|tubus}}."),
                "tubus": entry("Latin", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("tubicino")
        assert [n.form.lemma for n in result.start.main_chain()] == [
            "tubicino",
            "tubo",
            "tubus",
        ]

    def test_a_derivation_read_from_a_definition_is_marked(self):
        source = DictSource(
            {
                "tubicino": self.page("{{diminutive of|it|tubo}}"),
                "tubo": entry("Italian", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("tubicino")
        assert result.start.children[0].from_definition

    def test_a_contraction_is_not_marked(self):
        # `dal` *is* `da` + `il`: there is no synchronic/diachronic gap to warn
        # about, and marking it would cry wolf.
        source = DictSource(
            {
                "dal": self.page("{{contraction of|it|da|il}}", "Contraction"),
                "da": entry("Italian", "Of uncertain origin."),
                "il": entry("Italian", "Of uncertain origin."),
            }
        )
        result = Reconstructor(source).reconstruct("dal")
        assert [c.form.lemma for c in result.start.children] == ["da", "il"]
        assert not any(c.from_definition for c in result.start.children)

    def test_an_acronym_declares_no_etymology(self):
        # Acronyms are out of scope. `CEI` does not descend from «Conferenza
        # Episcopale Italiana»; it is a way of writing it, which is a question
        # about spelling and not about history. The entry is read, nothing
        # etymological is found, and the terminal says exactly that.
        source = DictSource(
            {"CEI": self.page("{{initialism of|it|Conferenza Episcopale Italiana}}")}
        )
        result = Reconstructor(source).reconstruct("CEI")
        assert result.start.terminal is Terminal.ETYMOLOGY_MISSING
        assert not result.start.terminal.is_linguistic
        assert result.start.children == []

    def test_a_shortening_of_one_word_is_still_a_pointer(self):
        # The family is the same, the target is not: an abbreviation naming a
        # single word points at something with a history, and is followed as
        # usual. Removing acronyms must not take this with it.
        source = DictSource(
            {
                "TV": self.page("{{abbreviation of|it|televisione}}"),
                "televisione": entry("Italian", "From {{der|it|en|television}}."),
            }
        )
        result = Reconstructor(source).reconstruct("TV")
        assert result.resolved
        assert result.start.form.lemma == "televisione"

    def test_an_entry_with_its_own_etymology_is_not_overridden(self):
        page = (
            "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|tubus}}.\n\n"
            "===Noun===\n{{head}}\n\n# {{diminutive of|it|tubo}}\n"
        )
        source = DictSource(
            {"tubicino": page, "tubus": entry("Latin", "Of uncertain origin.")}
        )
        result = Reconstructor(source).reconstruct("tubicino")
        assert result.start.children[0].form.lemma == "tubus"
        assert not result.start.children[0].from_definition


class TestChronologyDoesNotFireOnSisters:
    """Languages alive at the same time never contradict each other.

    The first version of this check ranked languages within families, which
    made Italian and French comparable — they are sisters, not stages — and so
    declared the well documented sixteenth-century borrowing of Italian words
    into French an impossibility. Dates carry no such assumption.
    """

    def test_italian_into_middle_french_is_not_a_contradiction(self):
        assert not impossible_order("it", "frm")
        assert not impossible_order("it", "fro")
        assert not impossible_order("es", "frm")

    def test_modern_coinages_from_living_languages_are_allowed(self):
        # New Latin is contemporary with Italian: scientific coinages from
        # Italian words exist.
        assert not impossible_order("it", "la-new")
        assert not impossible_order("pt", "la-new")

    def test_real_contradictions_still_fire(self):
        assert impossible_order("de", "lng")
        assert impossible_order("fr", "la")
        assert impossible_order("en", "ang")
        assert impossible_order("el", "grc")

    def test_unrelated_but_contemporary_languages_stay_quiet(self):
        # Arabic and Latin overlap in time: whatever their kinship, the check
        # has nothing to say.
        assert not impossible_order("ar", "la")

    def test_unknown_languages_are_never_judged(self):
        assert not impossible_order("omv", "la")
        assert not impossible_order("la", "omv")


class TestMultiplePointers:
    """One spelling, several unrelated lemmas.

    `po'` is the apocope of `poco` as a noun, of `puoi` as a verb, and an
    alternative form of `poi` as an adverb. Choosing one silently answers a
    question the reader did not ask.
    """

    PAGE: ClassVar[str] = (
        "==Italian==\n\n"
        "===Noun===\n{{head}}\n\n# {{apoc of|it|poco}}\n\n"
        "===Adverb===\n{{head}}\n\n# {{alt form|it|poi||then, later}}\n\n"
        "===Verb===\n{{head}}\n\n# {{apoc of|it|puoi||you can}}\n"
    )
    PAGES: ClassVar[dict] = {
        "po'": PAGE,
        "poco": entry("Italian", "From {{inh|it|la|paucus}}."),
        "poi": entry("Italian", "From {{inh|it|la|post}}."),
        "puoi": entry("Italian", "From {{inh|it|la|potes}}."),
    }

    def test_all_targets_are_offered(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("po'")
        assert result.ambiguous_pointer
        assert [o.forms[0].lemma for o in result.pointer_options] == [
            "poco",
            "poi",
            "puoi",
        ]

    def test_each_target_carries_what_tells_it_apart(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("po'")
        adverb = result.pointer_options[1]
        assert adverb.part_of_speech == "adverb"
        assert adverb.gloss == "then, later"

    def test_a_target_can_be_chosen_by_name(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("po'", as_lemma="puoi")
        assert result.start.form.lemma == "puoi"
        assert result.start.children[0].form.lemma == "potes"

    def test_the_name_is_matched_regardless_of_case(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("po'", as_lemma="POCO")
        assert result.start.form.lemma == "poco"

    def test_an_unknown_name_resolves_to_nothing(self):
        # Better to say the word does not point there than to fall back on a
        # target the reader did not ask for.
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("po'", as_lemma="cane")
        assert not result.resolved
        assert result.start.form.lemma == "po'"

    def test_targets_are_deduplicated_on_where_they_lead(self):
        # Noun and adjective pointing at the same lemma are two sections but a
        # single choice: offering it twice would invent an ambiguity.
        pages = {
            "x": (
                "==Italian==\n\n"
                "===Noun===\n{{head}}\n\n# {{plural of|it|y}}\n\n"
                "===Adjective===\n{{head}}\n\n# {{plural of|it|y}}\n"
            ),
            "y": entry("Italian", "Of uncertain origin."),
        }
        result = Reconstructor(DictSource(pages)).reconstruct("x")
        assert not result.ambiguous_pointer
        assert len(result.pointer_options) == 1

    def test_a_single_target_is_not_a_choice(self):
        pages = {
            "andato": (
                "==Italian==\n\n===Verb===\n{{head}}\n\n"
                "# {{past participle of|it|andare}}\n"
            ),
            "andare": entry("Italian", "Of uncertain origin."),
        }
        result = Reconstructor(DictSource(pages)).reconstruct("andato")
        assert not result.ambiguous_pointer


class TestSpellingVariants:
    """One form written several ways is tried spelling by spelling.

    `onza,oncia` is the same word twice, both from Latin `uncia`; `onza` has a
    page but no Italian section, `oncia` has both. Stopping at the first would
    abandon a chain the entry had fully described — and picking one silently
    would be worse.
    """

    PAGES: ClassVar[dict] = {
        "x": (
            "==Italian==\n\n===Noun===\n{{head}}\n\n"
            "# {{abbreviation of|it|onza,oncia}}\n"
        ),
        # a page that exists but says nothing in Italian
        "onza": "==Spanish==\n\n===Noun===\n{{head}}\n\n# an ounce\n",
        "oncia": entry("Italian", "From {{inh|it|la|uncia}}."),
        "uncia": entry("Latin", "Of uncertain origin."),
    }

    def test_the_second_spelling_is_tried(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("x")
        assert result.resolved
        assert result.start.form.lemma == "onza"
        assert result.start.children[0].form.lemma == "uncia"

    def test_the_spelling_actually_read_is_declared(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("x")
        assert "«oncia»" in (result.start.note or "")

    def test_both_spellings_stay_visible(self):
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("x")
        assert result.start.form.variants == ("oncia",)

    def test_when_no_spelling_has_an_entry_nothing_is_invented(self):
        pages = {
            "x": (
                "==Italian==\n\n===Noun===\n{{head}}\n\n"
                "# {{abbreviation of|it|aaa,bbb}}\n"
            )
        }
        result = Reconstructor(DictSource(pages)).reconstruct("x")
        assert result.start.terminal is Terminal.ENTRY_MISSING
        assert not result.start.terminal.is_linguistic


class TestUnattributableContinuation:
    """A compound splits the walk; a reserve cannot be handed to both branches.

    `obtūrō` is «ob- + *tūrō, the second component from *tūrāō, from *tewh₂-».
    Only the source knows which branch the continuation belongs to, and reading
    "the second component" would be interpretation. Discarding it, though, is
    worse: the entry says those forms plainly and the output showed neither.
    """

    PAGES: ClassVar[dict] = {
        "obturo": entry(
            "Latin",
            "From {{af|la|ob-|*tūrō}}, the second component from "
            "{{inh|la|itc-pro|*tūrāō}}, from {{der|la|ine-pro|*tewh₂-}}.",
        ),
        "ob-": entry("Latin", "Of uncertain origin."),
    }

    def test_the_continuation_is_declared(self):
        result = Reconstructor(self.PAGES and DictSource(self.PAGES)).reconstruct(
            "obturo", "la"
        )
        assert "*tūrāō" in result.start.note
        assert "*tewh₂-" in result.start.note

    def test_it_is_not_attached_to_either_branch(self):
        # Hanging it on one component would claim what the source did not say.
        result = Reconstructor(DictSource(self.PAGES)).reconstruct("obturo", "la")
        assert [c.form.lemma for c in result.start.children] == ["ob-", "*tūrō"]
        for child in result.start.children:
            assert "*tūrāō" not in (child.note or "")

    def test_a_single_component_still_receives_the_reserve(self):
        # With one branch there is no ambiguity: the reserve is walked, as
        # before. `y` has no entry of its own, so the reserve is what carries
        # the chain onward — had it declared an origin, its own word would win.
        pages = {"x": entry("Italian", "From {{der|it|la|y}}, from {{der|it|la|z}}.")}
        result = Reconstructor(DictSource(pages)).reconstruct("x")
        assert [n.form.lemma for n in result.start.main_chain()] == ["x", "y", "z"]


class TestReserveSurvivesAPageChange:
    """The reserve is a stack: a nearer entry speaking does not erase a farther
    one that still has something to say.

    `formaggio` is the case that made this necessary — see the fidelity suite,
    where it lived as a strict xfail for a day.
    """

    CHAIN: ClassVar[dict] = {
        # Names the whole path down to `forma`.
        "x": entry(
            "Italian",
            "From {{bor|it|fro|y}}, from {{der|it|la-med|z}}, from {{der|it|la|w}}.",
        ),
        # Restates the middle of it, and knows nothing further.
        "y": entry("Old French", "From {{inh|fro|la-eme|z}}."),
    }

    def test_the_farther_entry_still_carries_the_chain(self):
        result = Reconstructor(DictSource(self.CHAIN)).reconstruct("x")
        assert [n.form.lemma for n in result.start.main_chain()] == ["x", "y", "z", "w"]

    def test_the_attribution_survives_with_it(self):
        # `w` is known because «x» said so; `y` and `z` never mention it.
        result = Reconstructor(DictSource(self.CHAIN)).reconstruct("x")
        assert "«x»" in result.start.main_chain()[3].note

    def test_a_restated_stage_is_not_offered_twice(self):
        # Both entries name `z`. Matching is on the lemma alone: «la-med» to
        # one entry and «la-eme» to the other is the same stage under two
        # period labels, and requiring the codes to agree would break the
        # alignment exactly where it is needed.
        result = Reconstructor(DictSource(self.CHAIN)).reconstruct("x")
        assert [n.form.lemma for n in result.start.main_chain()].count("z") == 1


class TestEntriesThatDisagree:
    """Two entries describing the same stretch of path, differently.

    None of this is drawn. A branch would claim two ancestors; a hypothesis
    would call one of them a guess. They are two sources that do not say the
    same thing, and that is what the output says.
    """

    def test_a_contradicted_reserve_is_declared_not_drawn(self):
        source = DictSource(
            {
                "a": entry("Italian", "From {{inh|it|la|b}}, from {{inh|it|la|c}}."),
                "b": entry("Latin", "From {{inh|la|itc-pro|d}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        chain = [n.form.lemma for n in result.start.main_chain()]
        # `c` is not placed under `d`: that would invert the order «a» states.
        assert chain == ["a", "b", "d"]
        note = result.start.children[0].note or ""
        assert "«c»" in note and "«a»" in note

    def test_a_remote_ancestor_is_not_a_disagreement(self):
        # "ultimately from" says outright that stages lie between, so a stage
        # the next entry supplies is what the first predicted. This is the
        # common case, and it must stay quiet.
        source = DictSource(
            {
                "a": entry(
                    "Italian",
                    "From {{inh|it|la|b}}, ultimately from {{der|it|ine-pro|c}}.",
                ),
                "b": entry("Latin", "From {{inh|la|itc-pro|d}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert [n.form.lemma for n in result.start.main_chain()] == ["a", "b", "d", "c"]
        assert "continues instead" not in (result.start.children[0].note or "")

    def test_a_stage_the_entry_passes_over_is_declared(self):
        # «a» names c between b and d; b's own page jumps straight to d. Both
        # are entries, neither is guessing, and the reader is told which one
        # puts something in the gap.
        source = DictSource(
            {
                "a": entry(
                    "Italian",
                    "From {{der|it|la|b}}, from {{der|it|la|c}}, "
                    "from {{der|it|grc|d}}.",
                ),
                "b": entry("Latin", "From {{der|la|grc|d}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")

        # The walk follows the page it is standing on...
        assert [n.form.lemma for n in result.start.main_chain()] == ["a", "b", "d"]
        # ...and says what the other entry placed in the gap it jumped.
        note = result.start.children[0].note or ""
        assert "«c»" in note and "«a»" in note

    def test_agreement_leaves_no_note_at_all(self):
        # The overwhelmingly common case: two entries naming the same next
        # stage. Nothing to report, and reporting it would bury the cases that
        # matter. Measured over the frozen fixtures, this fires on all of them.
        source = DictSource(
            {
                "a": entry("Italian", "From {{der|it|la|b}}, from {{der|it|grc|c}}."),
                "b": entry("Latin", "From {{der|la|grc|c}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert [n.form.lemma for n in result.start.main_chain()] == ["a", "b", "c"]
        assert result.start.children[0].note is None


class TestWhatCountsAsDisagreement:
    """Chronology decides it, not how immediate the relation sounds.

    The first version judged by the relation and was wrong on real data: on
    sixty random entries it called three things disagreements, and two of them
    — `piede`, `disintossicato` — were a reserve holding Proto-Indo-European
    where the entry gave Proto-Italic. An ancestor further up is not a
    contradiction.
    """

    def test_an_older_reserve_is_not_a_contradiction(self):
        # `piede`, in miniature: the entry names the PIE form, the Latin page
        # supplies the Proto-Italic stage in between. Both are right.
        source = DictSource(
            {
                "a": entry(
                    "Italian", "From {{inh|it|la|b}}, from {{inh|it|ine-pro|*c}}."
                ),
                "b": entry("Latin", "From {{inh|la|itc-pro|*d}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert [n.form.lemma for n in result.start.main_chain()] == ["a", "b", "*d", "*c"]
        assert "continues instead" not in (result.start.children[0].note or "")

    def test_ablaut_grades_are_one_form_not_two(self):
        # `cuore` reported its sources as contradicting each other over a word
        # they agree on: «*ḱḗr ~ *ḱr̥d-» is one lemma in two grades, and the
        # entry giving only «*ḱḗr» says the same thing more briefly.
        source = DictSource(
            {
                "a": entry(
                    "Italian",
                    "From {{inh|it|la|b}}, from {{inh|it|ine-pro|*ḱḗr ~ *ḱr̥d-}}.",
                ),
                "b": entry("Latin", "From {{inh|la|ine-pro|*ḱḗr}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert "continues instead" not in (result.start.children[0].note or "")
        assert [n.form.lemma for n in result.start.main_chain()] == ["a", "b", "*ḱḗr"]


class TestSpellingDifferencesAreNotDisagreements:
    """Two entries naming one word rarely spell it the same way."""

    def test_marks_of_quantity_are_ignored(self):
        # `folcloristicamente` declared «-ιστής» and «-ῐστής» — one suffix,
        # the second written with the breve — as two entries contradicting
        # each other. The fidelity suite had this written down for πλατεῖα
        # against πλᾰτεῖᾰ, and comparing by casefold alone missed it.
        source = DictSource(
            {
                "a": entry("Italian", "From {{bor|it|grc|-ιστής}}."),
                "-ιστής": entry("Ancient Greek", "From {{af|grc|-ῐστής}}."),
                "-ῐστής": entry("Ancient Greek", "From {{inh|grc|grk-pro|*-tās}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        for node in [result.start, *result.start.main_chain()]:
            assert "continues instead" not in (node.note or "")


class TestNothingHeldIsDroppedInSilence:
    """Two ways a reserve used to vanish without leaving a mark.

    Both came from a random sample of 300 entries, and both are the same
    mistake: the walk was right not to *draw* the forms, and wrong to say
    nothing about them.
    """

    def test_a_reserve_the_walk_never_needed_is_declared(self):
        # `paraurti`: «parare» gives «from parō, from *per-»; the `parō` page
        # gives *perh₃- instead and ends on a root, so the reserve is never
        # spent. Two entries proposing two reconstructions of one root is
        # worth knowing — choosing silently between them is not ours to do.
        source = DictSource(
            {
                "a": entry(
                    "Italian", "From {{inh|it|la|b}}, from {{der|it|ine-pro|*x}}."
                ),
                "b": entry("Latin", "From {{der|la|ine-pro|*y}}."),
                "Reconstruction:Proto-Indo-European/y": entry(
                    "Proto-Indo-European", "{{rootsee|ine-pro|*y}}"
                ),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert "«*x»" in (result.start.main_chain()[-1].note or "")

    def test_half_a_compound_is_not_lost_to_a_partial_match(self):
        # `dogaressa`: the reserve holds «dux + -issa», the page reached names
        # only `-issa`, and matching on it used to take the whole step out —
        # carrying off `dux`, which is the half that means something.
        source = DictSource(
            {
                "a": entry("Italian", "From {{der|it|la|b}}, from {{af|la|dux|-issa}}."),
                "b": entry("Latin", "From {{suffix|la||-issa}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        assert "«dux»" in (result.start.children[0].note or "")

    def test_one_statement_made_by_two_entries_is_reported_once(self):
        # A word and the entry that borrowed it commonly declare the same
        # ancestry, and `dogaressa` said it twice in one breath.
        source = DictSource(
            {
                "a": entry(
                    "Italian", "From {{bor|it|vec|b}}, from {{af|la|dux|-issa}}."
                ),
                "b": entry(
                    "Venetan", "From {{uder|vec|la|c}}, from {{af|la|dux|-issa}}."
                ),
                "c": entry("Latin", "From {{suffix|la||-issa}}."),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        note = result.start.children[0].children[0].note or ""
        assert note.count("«dux»") == 1
        assert "the entries" in note and " give " in note

    def test_what_the_node_already_shows_is_not_called_lost(self):
        # `domato`: «domare» gives «from domō, from *domaō», and the `domō`
        # page carries *domaō as an attributed conjecture — on screen, under
        # this very node. Announcing it as not reached would be the tool
        # accusing itself of losing something the reader can see.
        source = DictSource(
            {
                "a": entry(
                    "Italian", "From {{der|it|la|b}}, from {{der|it|itc-pro|*x}}."
                ),
                "b": entry(
                    "Latin",
                    "Of uncertain origin. De Vaan suggests it derives from "
                    "{{der|la|itc-pro|*x}}.",
                ),
            }
        )
        result = Reconstructor(source).reconstruct("a")
        node = result.start.children[0]
        assert [h.form.lemma for h in node.hypotheses] == ["*x"]
        assert "not reached here" not in (node.note or "")
