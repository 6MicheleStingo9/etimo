"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from . import __version__
from .cache import DEFAULT_TTL_DAYS, DiskCache, clear
from .cache import default_path as default_cache_path
from .languages import is_known_language
from .models import Sense, Terminal
from .render import Style, as_json, chain, tree
from .render import pointer_choices as render_pointer_choices
from .render import senses as render_senses
from .walker import DEFAULT_MAX_DEPTH, Reconstructor
from .wiktionary import SourceError, WikitextSource, WiktionaryClient

_DESCRIPTION = """\
Reconstructs the formal history of a word by walking from ancestor to ancestor
until a terminal: a reconstructed root, a declared uncertain origin, or the
exhaustion of the available data.
"""

_EPILOGUE = """\
examples:
  etimo fuoco                  full tree
  etimo caffe --chain          main line only
  etimo riso --sense 3         the third etymology recorded for the entry
  etimo focus --language la    start from a Latin word
  etimo ciao --json            structured output

Data comes from en.wiktionary.org. Downloaded pages are kept locally for
thirty days.
"""

# Exit codes. 2 is left to argparse, which uses it for a misuse of the command
# line: a caller must be able to tell "you typed it wrong" from "the word is not
# there", and sharing a code would make the two indistinguishable.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2  # argparse's own; never returned by main()
EXIT_NOT_FOUND = 3
EXIT_UNREACHABLE = 4

# Beyond this the tree stops being readable and the recursion in the walker and
# in the renderer starts risking the interpreter's own limit.
MAX_DEPTH_ALLOWED = 100


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="etimo",
        description=_DESCRIPTION,
        epilog=_EPILOGUE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Optional because --clear-cache is maintenance and concerns no particular
    # word.
    parser.add_argument("word", nargs="?", help="the word whose history to reconstruct")
    parser.add_argument(
        "-l",
        "--language",
        default="it",
        metavar="CODE",
        help="starting language, in Wiktionary codes (default: it)",
    )
    parser.add_argument(
        "-s",
        "--sense",
        type=int,
        default=None,
        metavar="N",
        help="which etymology to follow, for spellings that cover several words",
    )
    parser.add_argument(
        "--senses",
        action="store_true",
        help="list the words this spelling covers, and exit",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        metavar="N",
        help=f"how many steps at most (default: {DEFAULT_MAX_DEPTH})",
    )

    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "-c",
        "--chain",
        dest="chain_view",
        action="store_true",
        help="show the main line only",
    )
    output.add_argument(
        "-j",
        "--json",
        dest="json_output",
        action="store_true",
        help="structured JSON output",
    )

    parser.add_argument(
        "--no-compounds",
        action="store_true",
        help="do not break down compounds and affixal derivations",
    )
    parser.add_argument(
        "--as",
        dest="as_lemma",
        metavar="LEMMA",
        help="when the form points at several words, follow this one",
    )
    parser.add_argument(
        "--as-written",
        action="store_true",
        help="do not resolve an inflected form to its lemma",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="always query the network, ignoring pages already downloaded",
    )
    parser.add_argument(
        "--cache-ttl",
        type=float,
        default=DEFAULT_TTL_DAYS,
        metavar="DAYS",
        help="after how many days an entry is fetched again "
             f"(default: {DEFAULT_TTL_DAYS:.0f})",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="delete the locally stored pages and exit",
    )
    parser.add_argument(
        "--prune-cache",
        action="store_true",
        help="drop expired pages from the cache and reclaim the space",
    )
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="report how much is stored locally and exit",
    )
    parser.add_argument("--no-color", action="store_true", help="disable colours")
    parser.add_argument(
        "-V", "--version", action="version", version=f"etimo {__version__}"
    )

    parsed = parser.parse_args(argv)
    # `--sense` given explicitly means "do not ask me": telling that apart from
    # the default is what lets the tool offer a choice only when it is needed.
    parsed.sense_given = parsed.sense is not None
    if parsed.sense is None:
        parsed.sense = 1
    return parsed


def _interactive() -> bool:
    """True when there is a person at the other end to answer a question.

    Both ends matter: without a terminal to read from there is nobody to ask,
    and without one to write to the question would end up inside a pipe.
    """
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):  # detached or closed streams
        return False


def _pick_sense(
    options: list[Sense],
    word: str,
    style: Style,
    ask: Callable[[str], str],
) -> int | None:
    """Let the reader choose between homographs. None means they gave up.

    The menu goes to stderr and the answer is read from stdin, so redirecting
    the output still yields a clean tree in the file and the question on screen.
    """
    print(render_senses(word, options, style), file=sys.stderr)
    allowed = {str(o.index) for o in options}
    prompt = f"\nChoose [{'/'.join(sorted(allowed))}], or q to quit: "

    while True:
        try:
            answer = ask(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return None
        if answer in ("q", "quit", "exit"):
            return None
        if answer in allowed:
            return int(answer)
        print("Please answer with one of the numbers above, or q.", file=sys.stderr)


def _pick_target(
    options: list, word: str, style: Style, ask: Callable[[str], str]
) -> str | None:
    """Let the reader choose which lemma to follow. None means they gave up.

    Answered by name, not by number: unlike homographs, these targets have
    names, and a name is what the reader recognises.
    """
    print(render_pointer_choices(word, options, style), file=sys.stderr)
    allowed = {o.forms[0].bare_lemma.casefold(): o.forms[0].bare_lemma for o in options}
    prompt = f"\nWhich one? [{'/'.join(allowed.values())}], or q to quit: "

    while True:
        try:
            answer = ask(prompt).strip().casefold()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return None
        if answer in ("q", "quit", "exit"):
            return None
        if answer in allowed:
            return allowed[answer]
        print("Please answer with one of the names above, or q.", file=sys.stderr)


def _explain_absence(word: str, language: str, terminal: Terminal | None) -> str:
    """A useful message when the starting word leads nowhere."""
    if terminal is Terminal.ENTRY_MISSING:
        return (
            f"«{word}» has no {language} entry on en.wiktionary.org.\n"
            "Check the spelling, or name another language with --language."
        )
    if terminal is Terminal.LANGUAGE_MISSING:
        return (
            f"The entry «{word}» exists on en.wiktionary.org but does not cover "
            f"the language «{language}».\nTry --language to name the right one."
        )
    if terminal is Terminal.FORM_NOT_GIVEN:
        return (
            f"The entry for «{word}» names where the word came from but not "
            "what it was.\nThat is as far as the source goes."
        )
    if terminal is Terminal.ETYMOLOGY_MISSING:
        # The second line used to read "this is not a gap in the tool: the
        # data is not in the source". That stopped being true when acronyms
        # went out of scope: `S.p.A.` does declare «società per azioni», and
        # it is this tool that leaves it alone. Claiming otherwise would be a
        # limit of ours dressed as silence from the source — the one thing the
        # output must never do.
        return (
            f"The entry «{word}» exists but records no etymology.\n"
            "The source may state none, or state it in a form not read here."
        )
    if terminal is Terminal.NOT_INTERPRETED:
        return (
            f"The entry «{word}» states its etymology in prose that this tool\n"
            "cannot turn into a chain. Its text is printed as the source gives it."
        )
    return f"No usable etymological information for «{word}»."


def main(argv: list[str] | None = None) -> int:
    """Entry point, with a last-resort handler so nothing escapes as a traceback."""
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except Exception as error:
        print(
            f"Unexpected failure ({type(error).__name__}: {error}).\n"
            "This is a bug in etimo, not a limit of the source.",
            file=sys.stderr,
        )
        return EXIT_ERROR


def _run(argv: list[str] | None) -> int:
    options = _arguments(argv)

    def warn(message: str) -> None:
        print(f"  … {message}", file=sys.stderr)

    if options.clear_cache:
        succeeded, message = clear()
        print(message, file=sys.stdout if succeeded else sys.stderr)
        return EXIT_OK if succeeded else EXIT_ERROR

    if options.prune_cache:
        with DiskCache(WiktionaryClient(warn=warn), warn=warn) as cache:
            removed, reclaimed = cache.prune()
        if removed:
            print(f"Dropped {removed} expired pages, reclaiming {reclaimed:.1f} MB.")
        else:
            print("Nothing to prune: no expired pages.")
        return EXIT_OK

    if options.cache_stats:
        with DiskCache(WiktionaryClient(warn=warn), warn=warn) as cache:
            entries, megabytes = cache.stats()
        print(f"{entries} pages stored in {default_cache_path()} ({megabytes:.1f} MB).")
        return EXIT_OK

    if not options.word:
        print("Name the word to reconstruct. Use --help for the options.",
              file=sys.stderr)
        return EXIT_ERROR

    if not 1 <= options.depth <= MAX_DEPTH_ALLOWED:
        print(f"Depth must be between 1 and {MAX_DEPTH_ALLOWED}.", file=sys.stderr)
        return EXIT_ERROR

    if options.cache_ttl < 0:
        print("The cache lifetime cannot be negative. Use --no-cache to skip it.",
              file=sys.stderr)
        return EXIT_ERROR

    # A wrong language code otherwise surfaces as a generic "no entry", sending
    # the user to check a spelling that was never the problem.
    if not is_known_language(options.language):
        print(
            f"«{options.language}» is not a language code we know.\n"
            "Use Wiktionary codes: it (Italian), la (Latin), grc (Ancient Greek)…",
            file=sys.stderr,
        )
        return EXIT_ERROR

    source: WikitextSource = WiktionaryClient(warn=warn)
    if not options.no_cache:
        source = DiskCache(source, ttl_days=options.cache_ttl, warn=warn)

    reconstructor = Reconstructor(
        source,
        max_depth=options.depth,
        follow_compounds=not options.no_compounds,
    )
    style = Style(enabled=not options.no_color)

    try:
        # Which word did they mean? Some spellings cover several unrelated
        # ones. This costs no extra request: the page is fetched once and the
        # walk below reuses it.
        chosen = options.sense
        ambiguous: list[Sense] | None = None
        if options.senses or not options.sense_given:
            everything = reconstructor.senses(options.word, options.language)
            ambiguous = [s for s in everything if s.carries_etymology]

            if options.senses:
                if not everything:
                    print(f"«{options.word}» records no separate etymologies.")
                else:
                    print(render_senses(options.word, everything, style))
                return EXIT_OK

            if len(ambiguous) > 1:
                if _interactive():
                    picked = _pick_sense(ambiguous, options.word, style, input)
                    if picked is None:
                        return EXIT_OK
                    chosen = picked
                else:
                    # Nothing to ask through: carry on with the first, but say
                    # so loudly, and put the alternatives where a script can
                    # find them — in the JSON, and on stderr.
                    chosen = ambiguous[0].index
                    print(render_senses(options.word, ambiguous, style), file=sys.stderr)
                    print(
                        f"\nNo one to ask, so following «{ambiguous[0].describe()}». "
                        f"Choose with --sense {ambiguous[0].index}"
                        f"…{ambiguous[-1].index}.",
                        file=sys.stderr,
                    )
            elif len(ambiguous) == 1:
                chosen = ambiguous[0].index

        result = reconstructor.reconstruct(
            options.word,
            options.language,
            sense=chosen,
            follow_lemma=not options.as_written,
            as_lemma=options.as_lemma,
        )

        # A form can point at several unrelated words. Asking is better than
        # choosing, and where there is nobody to ask, saying what was chosen —
        # and among what — is better than presenting one target as the only one.
        if result.ambiguous_pointer and not options.as_lemma:
            targets = result.pointer_options
            if _interactive():
                picked_target = _pick_target(targets, options.word, style, input)
                if picked_target is None:
                    return EXIT_OK
                result = reconstructor.reconstruct(
                    options.word,
                    options.language,
                    sense=chosen,
                    follow_lemma=True,
                    as_lemma=picked_target,
                )
            else:
                print(
                    render_pointer_choices(options.word, targets, style),
                    file=sys.stderr,
                )
                print(
                    f"\nNo one to ask, so following «{targets[0].forms[0].lemma}». "
                    f"Choose with --as {targets[0].forms[0].bare_lemma}.",
                    file=sys.stderr,
                )
        elif options.as_lemma and not result.resolved:
            print(
                f"«{options.word}» does not point at «{options.as_lemma}».",
                file=sys.stderr,
            )
            return EXIT_NOT_FOUND
    except SourceError as error:
        print(f"Could not reach the source: {error}", file=sys.stderr)
        return EXIT_UNREACHABLE
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_ERROR
    except RecursionError:
        print("The chain went deeper than the interpreter allows. "
              "Try a smaller --depth.", file=sys.stderr)
        return EXIT_ERROR
    finally:
        closing = getattr(source, "close", None)
        if closing is not None:
            closing()

    start = result.start
    # The starting word led nowhere. Where there is nothing to draw, a one-line
    # tree would be noise and a diagnosis is worth more; where the entry did say
    # something we could not read, the tree carries that text and is printed —
    # the exit code still reports that no chain was built.
    barren = (
        start.terminal is not None
        and not start.children
        and not start.terminal.is_linguistic
    )
    # A form the source declined to give is not nothing: the note names the
    # language it came from, and that belongs on screen rather than behind a
    # one-line diagnosis.
    if barren and not start.source_text and start.terminal is not Terminal.FORM_NOT_GIVEN:
        print(
            _explain_absence(options.word, options.language, start.terminal),
            file=sys.stderr,
        )
        # A reader is better served by the diagnosis alone — a one-line tree
        # would be noise. A program is not: printing nothing on stdout leaves
        # it unable to tell "the source records no etymology" from "the command
        # went wrong", and that is a third of Italian entries. So `--json`
        # always emits its object, the diagnosis stays on stderr for whoever is
        # watching, and the exit code goes on saying no chain was built.
        if options.json_output:
            print(as_json(result, options=ambiguous))
        return EXIT_NOT_FOUND

    if options.json_output:
        print(as_json(result, options=ambiguous))
        return EXIT_NOT_FOUND if barren else EXIT_OK

    print(chain(result, style) if options.chain_view else tree(result, style))

    if barren:
        print(
            _explain_absence(options.word, options.language, start.terminal),
            file=sys.stderr,
        )
        return EXIT_NOT_FOUND

    if result.available_senses > 1 and not options.chain_view and ambiguous is None:
        print(
            f"\nThis entry records {result.available_senses} distinct etymologies. "
            f"For the others: --sense 2 … --sense {result.available_senses}",
            file=sys.stderr,
        )

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
