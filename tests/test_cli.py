"""The command line: exit codes, validation, and what reaches the streams.

`main` takes argv and returns an exit code, so the whole interface can be
driven from here without a subprocess. The source is replaced by a fixture, so
nothing touches the network or the user's cache.
"""

import json

import pytest

from etimo import cli
from etimo.wiktionary import SourceError


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every test gets a fixed source and no on-disk cache."""
    pages = {
        "fuoco": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|focus}}.\n",
        "focus": "==Italian==\n\n===Etymology===\n{{unc|la}}\n",
        "allogliato": "==Italian==\n\n===Etymology===\nFrom loglio.\n",
    }

    class Fixture:
        requests_made = 0

        def wikitext(self, title):
            return pages.get(title)

    monkeypatch.setattr(cli, "WiktionaryClient", lambda **_kwargs: Fixture())
    monkeypatch.setattr(cli, "DiskCache", lambda source, **_kwargs: source)
    return pages


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestExitCodes:
    def test_success(self, capsys):
        code, out, _ = run(capsys, "fuoco", "--no-color")
        assert code == cli.EXIT_OK
        assert "focus" in out

    def test_word_not_found_is_distinct_from_a_usage_error(self, capsys):
        code, _, err = run(capsys, "inesistente")
        assert code == cli.EXIT_NOT_FOUND
        assert code != cli.EXIT_USAGE, "a caller must tell the two apart"
        assert "wiktionary" in err.lower()

    def test_argparse_keeps_code_two_for_misuse(self):
        with pytest.raises(SystemExit) as exit_info:
            cli.main(["fuoco", "--sense", "not-a-number"])
        assert exit_info.value.code == cli.EXIT_USAGE

    def test_unreachable_source_has_its_own_code(self, capsys, monkeypatch):
        class Broken:
            requests_made = 0

            def wikitext(self, title):
                raise SourceError("connection refused")

        monkeypatch.setattr(cli, "WiktionaryClient", lambda **_k: Broken())
        code, _, err = run(capsys, "fuoco")
        assert code == cli.EXIT_UNREACHABLE
        assert "reach" in err.lower()

    def test_no_word_given(self, capsys):
        code, _, err = run(capsys)
        assert code == cli.EXIT_ERROR
        assert "--help" in err


class TestValidation:
    @pytest.mark.parametrize("depth", ["0", "-3", "101", "100000"])
    def test_depth_must_be_within_bounds(self, capsys, depth):
        code, _, err = run(capsys, "fuoco", "--depth", depth)
        assert code == cli.EXIT_ERROR
        assert str(cli.MAX_DEPTH_ALLOWED) in err

    def test_an_unknown_language_says_so(self, capsys):
        # Otherwise it surfaces as "no entry", sending the user to check a
        # spelling that was never the problem.
        code, _, err = run(capsys, "fuoco", "--language", "italiano")
        assert code == cli.EXIT_ERROR
        assert "italiano" in err
        assert "code" in err.lower()

    def test_a_negative_cache_lifetime_is_refused(self, capsys):
        code, _, err = run(capsys, "fuoco", "--cache-ttl", "-1")
        assert code == cli.EXIT_ERROR
        assert "no-cache" in err


class TestOutput:
    def test_json_goes_to_stdout_and_parses(self, capsys):
        code, out, _ = run(capsys, "fuoco", "--json")
        assert code == cli.EXIT_OK
        data = json.loads(out)
        assert data["word"] == "fuoco"
        assert data["tree"]["ancestors"][0]["lemma"] == "focus"

    def test_chain_view(self, capsys):
        _, out, _ = run(capsys, "fuoco", "--chain", "--no-color")
        assert "focus" in out
        assert "└─" not in out, "the chain view is linear"

    def test_no_colour_leaves_no_escapes(self, capsys):
        _, out, _ = run(capsys, "fuoco", "--no-color")
        assert "\033[" not in out

    def test_prose_we_cannot_read_is_still_shown(self, capsys):
        # The point of the NOT_INTERPRETED terminal: the reader gets the text
        # instead of a bare claim that the language has nothing more to say.
        code, out, err = run(capsys, "allogliato", "--no-color")
        assert code == cli.EXIT_NOT_FOUND, "no chain was built, and callers must know"
        # The tree is printed all the same, because it carries the text.
        assert "allogliato (it)" in out
        assert "etymology not interpreted" in out
        assert "From loglio." in out
        assert "prose" in err.lower()

    def test_a_word_that_leads_nowhere_prints_no_stub_tree(self, capsys):
        # With nothing to show, a one-line tree would be noise: the diagnosis on
        # stderr is worth more.
        code, out, err = run(capsys, "inesistente", "--no-color")
        assert code == cli.EXIT_NOT_FOUND
        assert out == ""
        assert err

    def test_diagnostics_never_land_on_stdout(self, capsys):
        _, out, _ = run(capsys, "inesistente")
        assert out == "", "stdout must stay clean for pipes"


class TestLastResort:
    def test_an_unexpected_failure_is_not_a_traceback(self, capsys, monkeypatch):
        class Exploding:
            requests_made = 0

            def wikitext(self, title):
                raise RuntimeError("boom")

        monkeypatch.setattr(cli, "WiktionaryClient", lambda **_k: Exploding())
        code, _, err = run(capsys, "fuoco")
        assert code == cli.EXIT_ERROR
        assert "bug in etimo" in err
        assert "Traceback" not in err


PAGINA_AMBIGUA = """==Italian==

===Etymology 1===
From {{inh|it|la|rīsus}}.

====Noun====
{{it-noun|m}}

# [[laughter]], [[laugh]]

===Etymology 2===
{{nonlemma}}

====Participle====
{{it-pp}}

# {{past participle of|it|ridere}}

===Etymology 3===
From {{inh|it|la-lat|oryza}}.

====Noun====
{{it-noun|m}}

# [[rice]]
"""


@pytest.fixture
def ambiguous(monkeypatch):
    """A spelling covering two real words and one inflected form."""
    pages = {"riso": PAGINA_AMBIGUA, "rīsus": "", "oryza": ""}

    class Fixture:
        requests_made = 0

        def wikitext(self, title):
            return pages.get(title)

    monkeypatch.setattr(cli, "WiktionaryClient", lambda **_k: Fixture())
    monkeypatch.setattr(cli, "DiskCache", lambda source, **_k: source)


class TestChoosingBetweenHomographs:
    def test_listing_shows_meanings_not_bare_ordinals(self, capsys, ambiguous):
        code, out, _ = run(capsys, "riso", "--senses", "--no-color")
        assert code == cli.EXIT_OK
        assert "laughter" in out and "rice" in out
        assert "rīsus" in out, "the first ancestor is often clearer than the gloss"

    def test_a_person_is_asked_and_their_answer_is_followed(
        self, capsys, ambiguous, monkeypatch
    ):
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "3")
        code, out, err = run(capsys, "riso", "--no-color")
        assert code == cli.EXIT_OK
        assert "oryza" in out, "the chosen sense is the one walked"
        assert "rice" in err, "the menu goes to stderr, leaving stdout clean"
        assert "rice" not in out

    def test_quitting_produces_nothing(self, capsys, ambiguous, monkeypatch):
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "q")
        code, out, _ = run(capsys, "riso", "--no-color")
        assert code == cli.EXIT_OK
        assert out == ""

    def test_an_invalid_answer_is_asked_again(self, capsys, ambiguous, monkeypatch):
        answers = iter(["7", "banana", "1"])
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
        code, out, err = run(capsys, "riso", "--no-color")
        assert code == cli.EXIT_OK
        assert "rīsus" in out
        assert err.lower().count("please answer") == 2

    def test_inflected_forms_are_not_offered_as_a_choice(
        self, capsys, ambiguous, monkeypatch
    ):
        # Etymology 2 is the past participle of «ridere»: it has no origin of
        # its own, so it is not a decision anyone should be asked to make.
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "1")
        _, _, err = run(capsys, "riso", "--no-color")
        menu = [line for line in err.splitlines() if line.startswith("  ")]
        assert len(menu) == 2
        assert not any("participle" in line for line in menu)

    def test_an_explicit_sense_asks_nothing(self, capsys, ambiguous, monkeypatch):
        def refuse(_prompt):
            raise AssertionError("--sense was given: there is nothing to ask")

        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", refuse)
        code, out, _ = run(capsys, "riso", "--sense", "3", "--no-color")
        assert code == cli.EXIT_OK
        assert "oryza" in out


class TestScriptsKeepWorking:
    """With nobody to ask, the command still answers — and says what it chose."""

    def test_output_is_still_produced(self, capsys, ambiguous, monkeypatch):
        monkeypatch.setattr(cli, "_interactive", lambda: False)
        code, out, err = run(capsys, "riso", "--no-color")
        assert code == cli.EXIT_OK
        assert "rīsus" in out, "the first real sense is followed"
        assert "--sense" in err, "and the alternatives are named on stderr"

    def test_json_carries_the_ambiguity_into_the_data(
        self, capsys, ambiguous, monkeypatch
    ):
        # A program must be able to tell that a choice was made for it.
        monkeypatch.setattr(cli, "_interactive", lambda: False)
        _, out, _ = run(capsys, "riso", "--json")
        data = json.loads(out)
        assert data["ambiguous"] is True
        assert [s["definition"] for s in data["senses"]] == ["laughter, laugh", "rice"]
        assert [s["index"] for s in data["senses"]] == [1, 3]
        assert sum(s["chosen"] for s in data["senses"]) == 1

    def test_a_word_with_one_meaning_says_so_plainly(self, capsys):
        # The key is always there when the senses were looked at, so a script
        # can test it without having to tell "false" from "absent".
        _, out, err = run(capsys, "fuoco", "--json")
        data = json.loads(out)
        assert data["ambiguous"] is False
        assert len(data["senses"]) == 1
        assert err == "", "nothing to warn about"

    def test_an_explicit_sense_leaves_the_schema_alone(self, capsys, ambiguous):
        # Having chosen, the caller is not told about the alternatives.
        _, out, _ = run(capsys, "riso", "--sense", "1", "--json")
        assert "ambiguous" not in json.loads(out)


PAGE_WITH_SEVERAL_TARGETS = (
    "==Italian==\n\n"
    "===Noun===\n{{head}}\n\n# {{apoc of|it|poco}}\n\n"
    "===Adverb===\n{{head}}\n\n# {{alt form|it|poi||then, later}}\n\n"
    "===Verb===\n{{head}}\n\n# {{apoc of|it|puoi||you can}}\n"
)


@pytest.fixture
def several_targets(monkeypatch):
    """A form that is a form of three unrelated words."""
    pages = {
        "po'": PAGE_WITH_SEVERAL_TARGETS,
        "poco": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|paucus}}.\n",
        "poi": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|post}}.\n",
        "puoi": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|potes}}.\n",
    }

    class Fixture:
        requests_made = 0

        def wikitext(self, title):
            return pages.get(title)

    monkeypatch.setattr(cli, "WiktionaryClient", lambda **_k: Fixture())
    monkeypatch.setattr(cli, "DiskCache", lambda source, **_k: source)


class TestChoosingBetweenTargets:
    """A form pointing at several lemmas, chosen by name rather than by number.

    The twin of `TestChoosingBetweenHomographs`, with one surface that has no
    counterpart there: the answer is typed, not picked from a numbered list.
    """

    def test_the_menu_names_the_lemmas_and_what_tells_them_apart(
        self, capsys, several_targets
    ):
        code, _out, err = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert "poco" in err and "puoi" in err
        assert "you can" in err, "the gloss is what distinguishes the verb"
        assert "noun" in err, "and so is the part of speech"

    def test_a_person_is_asked_and_their_answer_is_followed(
        self, capsys, several_targets, monkeypatch
    ):
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "puoi")
        code, out, _err = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert "potes" in out, "the chosen target is the one walked"
        assert "paucus" not in out, "and the others are not"

    def test_the_answer_is_matched_regardless_of_case(
        self, capsys, several_targets, monkeypatch
    ):
        # Typed by hand, so the case is whatever the reader felt like.
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "POCO")
        code, out, _ = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert "paucus" in out

    def test_quitting_produces_nothing(self, capsys, several_targets, monkeypatch):
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: "q")
        code, out, _ = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert out.strip() == "", "no tree is drawn for a question left unanswered"

    def test_an_invalid_answer_is_asked_again(
        self, capsys, several_targets, monkeypatch
    ):
        answers = iter(["cane", "poi"])
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
        code, out, err = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert "one of the names above" in err
        assert "post" in out, "the second answer is honoured"

    def test_giving_up_on_the_prompt_is_not_a_crash(
        self, capsys, several_targets, monkeypatch
    ):
        def interrupted(_prompt):
            raise EOFError

        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", interrupted)
        code, out, _ = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert out.strip() == ""

    def test_an_explicit_target_asks_nothing(
        self, capsys, several_targets, monkeypatch
    ):
        def must_not_be_called(_prompt):
            raise AssertionError("--as was given; nothing should be asked")

        monkeypatch.setattr(cli, "_interactive", lambda: True)
        monkeypatch.setattr("builtins.input", must_not_be_called)
        code, out, _ = run(capsys, "po'", "--as", "poi", "--no-color")
        assert code == cli.EXIT_OK
        assert "post" in out

    def test_a_name_the_word_does_not_point_at_is_refused(
        self, capsys, several_targets
    ):
        # Better than quietly falling back on a target nobody asked for.
        code, _out, err = run(capsys, "po'", "--as", "cane", "--no-color")
        assert code == cli.EXIT_NOT_FOUND
        assert "does not point at" in err

    def test_scripts_are_told_what_was_chosen_for_them(
        self, capsys, several_targets, monkeypatch
    ):
        monkeypatch.setattr(cli, "_interactive", lambda: False)
        code, out, err = run(capsys, "po'", "--no-color")
        assert code == cli.EXIT_OK
        assert "paucus" in out, "the first target is followed"
        assert "--as poco" in err, "and the reader is told how to choose another"

    def test_the_json_records_every_alternative(self, capsys, several_targets):
        code, out, _ = run(capsys, "po'", "--json")
        assert code == cli.EXIT_OK
        data = json.loads(out)
        assert data["ambiguous_pointer"] is True
        chosen = [o for o in data["points_at"] if o["chosen"]]
        assert len(chosen) == 1
        assert {o["lemma"] for o in data["points_at"]} == {"poco", "poi", "puoi"}


class TestJsonIsAlwaysEmitted:
    """A program must be able to tell "no etymology" from "the run failed".

    A barren entry gets a diagnosis instead of a one-line tree, which is right
    for a reader and wrong for a consumer: with `--json` the object used to be
    suppressed along with the tree, leaving stdout empty and only the exit
    code to go on. That is roughly a third of Italian entries — the ones the
    audit most needs to record as a limit of the source.
    """

    def test_a_barren_entry_still_produces_json(self, capsys, no_network):
        no_network["vuoto"] = "==Italian==\n\n===Noun===\n{{head}}\n\n# a word\n"
        code, out, err = run(capsys, "vuoto", "--json")

        assert code == cli.EXIT_NOT_FOUND
        payload = json.loads(out)
        assert payload["word"] == "vuoto"
        assert payload["tree"]["terminal"]["linguistic"] is False
        # The human-facing diagnosis is not lost, it is on the other stream.
        assert "records no etymology" in err
