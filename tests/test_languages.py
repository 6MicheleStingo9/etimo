"""Language naming and page-title resolution."""

from etimo.languages import (
    fallback_language,
    is_known_language,
    is_reconstructed,
    language_name,
    normalize_lemma,
    page_title,
)


class TestLanguageNames:
    def test_known_codes(self):
        assert language_name("la") == "Latin"
        assert language_name("ine-pro") == "Proto-Indo-European"
        assert language_name("ota") == "Ottoman Turkish"

    def test_unknown_code_stays_visible(self):
        # A raw code beats an invented name: the reader must be able to tell
        # that we do not know which language this is.
        assert language_name("omv") == "omv"
        assert not is_known_language("omv")

    def test_variant_falls_back_to_base_language(self):
        assert language_name("de-AT") == "German (de-AT)"


class TestReconstructedForms:
    def test_recognised_by_code(self):
        assert is_reconstructed("ine-pro")
        assert is_reconstructed("gem-pro")
        assert not is_reconstructed("la")

    def test_title_in_dedicated_namespace(self):
        assert (
            page_title("*dʰegʷʰ-", "ine-pro")
            == "Reconstruction:Proto-Indo-European/dʰegʷʰ-"
        )

    def test_asterisk_dropped_only_from_the_title(self):
        # The macron must stay: in proto-forms it is part of the title.
        assert page_title("*patēr", "itc-pro") == "Reconstruction:Proto-Italic/patēr"


class TestLemmaNormalisation:
    def test_latin_loses_vowel_length_marks(self):
        # Wiktionary titles the entry `labos`, but cites `labōs`.
        assert normalize_lemma("labōs", "itc-ola") == "labos"
        assert normalize_lemma("rēx", "la") == "rex"

    def test_arabic_loses_vocalisation(self):
        assert normalize_lemma("قَهْوَة", "ar") == "قهوة"

    def test_arabic_keeps_precomposed_letters(self):
        # Decomposing `أ` would reduce it to `ا`, changing the word: stripping
        # marks must never reach the consonants.
        assert normalize_lemma("أَحْمَر", "ar") == "أحمر"

    def test_greek_loses_length_but_keeps_accents_and_breathings(self):
        # `ὄρῡζα` belongs to the entry `ὄρυζα`: the macron on the upsilon goes,
        # the breathing and the accent stay, being part of the title.
        assert normalize_lemma("ὄρῡζα", "grc") == "ὄρυζα"
        assert normalize_lemma("ὄρυζα", "grc") == "ὄρυζα"

    def test_languages_outside_the_rule_are_untouched(self):
        assert normalize_lemma("œuf", "fr") == "œuf"
        assert normalize_lemma("*bʰeh₂-", "ine-pro") == "*bʰeh₂-"


class TestSectionFallback:
    def test_phases_of_latin(self):
        assert fallback_language("la-vul") == "la"
        assert fallback_language("itc-ola") == "la"

    def test_no_fallback_for_independent_languages(self):
        assert fallback_language("grc") is None
        assert fallback_language("it") is None
