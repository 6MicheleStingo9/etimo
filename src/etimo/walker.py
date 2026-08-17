"""Recursive walk up the etymological chain.

The task is simple to state and treacherous to carry out: given a form, ask the
source where it came from, then ask the same question of the answer. There are
three pitfalls.

**Cycles.** Wiktionary entries refer to one another; without a memory of the
forms already seen, a pair of mutual references sends the program round
forever.

**Honest termination.** A chain can stop because the language has nothing more
to say — a reconstructed root, a declared uncertain origin — or because the
tool could not go on. These are different things and must stay distinct in the
result, otherwise a technical limit disguises itself as a linguistic fact.

**Provenance.** When an ancestor has no entry of its own, the starting entry
often already carries the rest of the chain inline ("from Ottoman Turkish, in
turn from Arabic"). Using that is legitimate, provided it is declared as
second-hand information.
"""

from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass, field, replace

from .languages import (
    can_locate_reconstruction,
    fallback_language,
    impossible_order,
    language_name,
    page_title,
)
from .models import (
    Declaration,
    DefinitionStatement,
    Form,
    Hypothesis,
    Node,
    Relation,
    Sense,
    Step,
    Terminal,
)
from .wikitext import (
    Analysis,
    definition_statements,
    etymology_sections,
    language_section,
    parse,
)
from .wikitext import senses as wikitext_senses
from .wiktionary import SessionMemory, SourceError, WikitextSource

DEFAULT_MAX_DEPTH = 12

# How many "form of" pointers to follow before the walk begins. The longest
# real chain measured in Italian is three — `amatissime` reaches `amare`
# through `amatissimo` and `amato` — so three would pass with no margin at all.
# Four costs nothing: the loop stops at the first entry that has a history, so
# the fourth hop is only ever paid where it is needed.
_MAX_LEMMA_HOPS = 4

# Terminals that merely signal silence from the source. Only these may be
# superseded by falling back to the chain carried from a previous entry: when
# the source does speak — declaring an uncertain origin or a reconstructed root
# — that declaration is the result, and overriding it would replace a fact with
# a conjecture.
_TERMINALS_FROM_ABSENCE = frozenset(
    {
        Terminal.ENTRY_MISSING,
        Terminal.LANGUAGE_MISSING,
        Terminal.ETYMOLOGY_MISSING,
        Terminal.FORM_NOT_GIVEN,
        Terminal.NOT_INTERPRETED,
        Terminal.DATA_EXHAUSTED,
        Terminal.NETWORK_ERROR,
    }
)


@dataclass(frozen=True)
class _Reserve:
    """What one entry declared beyond the link currently being walked.

    `source_entry` records *which* entry states it, so the result can declare
    where the information comes from instead of crediting it to the wrong link.
    """

    steps: tuple[Step, ...] = ()
    source_entry: str = ""


@dataclass(frozen=True)
class CarriedChain:
    """Chains already declared by the entries passed through, kept in reserve.

    Needed when an ancestor has no entry of its own: the starting entry often
    describes the whole path.

    It is a *stack* rather than a single chain, and that is the whole point.
    Entries overlap: `formaggio` describes the path down to `fōrma`, and
    `fromage` — reached along the way — describes part of it again. Keeping
    only the nearest reserve loses the rest of the farther one, which is how
    `fōrma` used to disappear from a walk whose first entry had named it.

    The nearest entry is consulted first; what the farther ones still have to
    say waits behind it, and is used when the walk runs out of pages before it
    runs out of declared history.
    """

    reserves: tuple[_Reserve, ...] = ()

    @staticmethod
    def of(*reserves: _Reserve) -> CarriedChain:
        """Build a stack, dropping the reserves that have nothing left.

        An entry that restates the path without extending it leaves an empty
        reserve behind, and every link of the walk would add another. They
        change no outcome — `take` skips them — but they turn a two-deep stack
        into a twelve-deep one, and a structure that grows with the walk is
        one nobody can reason about later.
        """
        return CarriedChain(tuple(r for r in reserves if r.steps))

    def __bool__(self) -> bool:
        return any(reserve.steps for reserve in self.reserves)

    @property
    def steps(self) -> list[Step]:
        """Everything still held, nearest entry first."""
        return [step for reserve in self.reserves for step in reserve.steps]

    def take(self) -> tuple[Step | None, list[Step], str, CarriedChain]:
        """The first step held that cites a form, with what remains after it.

        Reserves that name only languages are not walkable, but they are stages
        the source describes: they come back as `skipped` rather than being
        dropped, so a mediated passage is not shown as a direct one.
        """
        skipped: list[Step] = []
        for index, reserve in enumerate(self.reserves):
            step, held_back, rest = _first_usable(list(reserve.steps))
            skipped.extend(held_back)
            if step is None:
                continue
            remaining = CarriedChain.of(
                _Reserve(tuple(rest), reserve.source_entry),
                *self.reserves[index + 1:],
            )
            return step, skipped, reserve.source_entry, remaining
        return None, skipped, "", CarriedChain()


@dataclass
class _Choice:
    """Which step to walk, and at what informational cost."""

    step: Step | None = None
    carried: CarriedChain = field(default_factory=CarriedChain)
    reported_by: str | None = None
    # Steps naming a language without citing a form: not walkable links, but
    # real stages of the path, and so worth declaring.
    skipped: list[Step] = field(default_factory=list)
    # Set when the entry just read and an entry passed earlier say different
    # things about the same stretch of the path.
    divergence: str | None = None


def _distinct_targets(
    statements: list[DefinitionStatement],
) -> list[DefinitionStatement]:
    """The pointers among these declarations, one per target lemma.

    Deduplicated on where they lead, not on where they were read: a word that
    is both noun and adjective of the same lemma is two sections but a single
    choice, and offering it twice would invent an ambiguity the entry does not
    have.
    """
    seen: set[tuple[str, str]] = set()
    distinct: list[DefinitionStatement] = []

    for statement in statements:
        if statement.kind is not Declaration.POINTER or not statement.forms:
            continue
        key = statement.forms[0].key
        if key in seen:
            continue
        seen.add(key)
        distinct.append(statement)

    return distinct


def _first_usable(steps: list[Step]) -> tuple[Step | None, list[Step], list[Step]]:
    """The first step citing a form, with what precedes and follows it.

    An entry may name an intermediate stage without a form — "a borrowing from
    an Eastern Iranian language, from *wrinǰiš" — and stopping at the first
    template would lose the next link, which does have one.
    """
    skipped: list[Step] = []
    for index, step in enumerate(steps):
        if any(form.lemma for form in step.forms):
            return step, skipped, steps[index + 1:]
        skipped.append(step)
    return None, skipped, []


def _named_forms(step: Step) -> str:
    return ", ".join(f"«{form.lemma}»" for form in step.forms if form.lemma)


def _attribution(entries: list[str], verb: str) -> str:
    """Name the entries making one statement, with the verb agreeing.

    `verb` comes in the third person singular — «gives», «places» — and drops
    its -s when more than one entry says the same thing.
    """
    unique = list(dict.fromkeys(entries))
    joined = ", ".join(f"«{name}»" for name in unique)
    if len(unique) == 1:
        return f"the entry {joined} {verb}"
    return f"the entries {joined} {verb.removesuffix('s')}"


def _unspent(carried: CarriedChain, shown: frozenset[str] = frozenset()) -> str:
    """What entries behind us still declared when the walk stopped.

    A reserve is used only where the source falls silent. Where it does not —
    a reconstructed root, a declared uncertainty — the reserve is right to go
    unused, and used to be dropped without trace: `parare` gives «from parō,
    from *per-», the `parō` page gives `*perh₃-` instead, the chain ends on a
    root, and `*per-` left no mark anywhere. Two entries proposing two
    reconstructions of one root is worth knowing; a silent choice between them
    is not something we may make on the reader's behalf.

    It is deliberately reported at the end rather than where the disagreement
    appears. Half way up there is no telling whether the reserve is a rival
    claim or an ancestor further along the same path — and only the end of the
    walk knows which it turned out to be.

    `shown` holds what this node already displays, and skipping it matters:
    `domare` gives «from domō, from *domaō», and the `domō` page carries
    *domaō as an attributed conjecture. It is on the screen, under this very
    node. Announcing it as *not reached* would be the tool accusing itself of
    losing something the reader can see — which is the failure mode of every
    check that verifies by absence, arriving here from the inside.
    """
    by_entry: dict[str, list[str]] = {}
    for reserve in carried.reserves:
        named = [
            f"«{form.lemma}»"
            for step in reserve.steps
            for form in step.forms
            if form.lemma and not _spellings(form) & shown
        ]
        if named:
            by_entry.setdefault(reserve.source_entry, []).extend(named)

    return "; ".join(
        f"the entry «{entry}» also gives {', '.join(forms)}, not reached here"
        for entry, forms in by_entry.items()
    )


def _spellings(form: Form) -> set[str]:
    """Every shape under which a citation may name this one form.

    Two entries naming the same word rarely spell it identically, and both ways
    they differ produced a false disagreement on real data.

    **Ablaut grades cited together.** `*ḱḗr ~ *ḱr̥d-` is a single lemma written
    in two grades, and an entry giving only `*ḱḗr` says the same thing more
    briefly. `cuore` reported its two sources as contradicting each other over
    a word they agree on.

    **Marks of quantity.** `-ιστής` and `-ῐστής` are one suffix, the second
    written with the breve; `πλατεῖα` and `πλᾰτεῖᾰ` likewise. Editors add them
    where a reader might need them and leave them off elsewhere, so they are
    noise for comparison and are stripped.

    The direction is safe: extra matches mean fewer disagreements declared, and
    a disagreement we fail to declare costs a note, while one we invent puts a
    falsehood in front of the reader.
    """
    return {
        "".join(
            character
            for character in unicodedata.normalize("NFD", piece.strip().lstrip("*"))
            if not unicodedata.combining(character)
        ).casefold()
        for whole in (form.bare_lemma, *form.variants)
        for piece in whole.split("~")
        if piece.strip().strip("*-")
    }


def _reconcile(carried: CarriedChain, step: Step) -> tuple[CarriedChain, str | None]:
    """Line the reserve up with the step the entry has just given on its own.

    Two entries describing the same path do not describe it identically, and
    the three ways they differ need three different answers.

    **They agree.** `formaggio` holds «fōrmāticum, fōrma» in reserve and
    `fromage` names fōrmāticum on its own: the reserve advances past it, so the
    walk does not offer a form it has just drawn. Matching is on the lemma
    alone, not on lemma and language — the same stage is «la-med» to one entry
    and «la-eme» to the other, and requiring the codes to agree would defeat
    the alignment exactly where it is needed.

    **The entry skips a stage the reserve named.** The reserve is advanced to
    where the two meet again, and what was passed over is declared: it is a
    real stage, stated by a real entry, and silently dropping it would make a
    path the source describes as mediated look direct.

    **They disagree.** Here the reserve is *discarded*, and this is the one
    case where discarding is right. Keeping it would place its forms below the
    ones the current entry gives — that is, invert the order one of the two
    entries states — and a tree that inverts is worse than a note that admits.
    So the forms are declared without being drawn.

    What counts as disagreement is decided by **chronology**, not by how
    immediate the relation sounds. Judging it by the relation was wrong, and
    measurably so: on sixty random entries it reported three disagreements, of
    which two were `piede` and `disintossicato`, where the reserve held
    Proto-Indo-European and the entry gave Proto-Italic. That is not a
    contradiction, it is an ancestor further up — and treating it as one was
    the tool contradicting a source that had said nothing wrong.

    So a reserve is only in conflict when it could not stand above the form the
    entry gives, which is what `impossible_order` already decides for links.
    Where the languages are unknown or compatible, the reserve waits: if it
    later lands somewhere it cannot belong, the same check catches it at the
    point of use and demotes it to a conjecture.

    **The wording of these notes must stay flat**, and two real cases show why.
    `porno` is a genuine scientific disagreement — `pornografia` derives the
    Latin from an attested Greek compound, `pornographia` has it assembled in
    Latin from Greek parts, and which is right is an open question. `biglia`
    looks identical and is almost certainly an editing mistake: French `bille`
    routes the marble through a Mediaeval Latin `billia` glossed *tree-trunk*,
    which belongs to the homonym meaning timber and has nothing to do with a
    Frankish word for a knucklebone.

    Nothing available here tells those two apart. So the note says what each
    entry says and stops. "Two accounts exist" would be true of the first and
    false of the second, and we would have no way of knowing which one we had.
    """
    named = {name for form in step.forms if form.lemma for name in _spellings(form)}
    kept: list[_Reserve] = []
    # Grouped by what is being reported, not by which reserve reported it: a
    # word and the entry that borrowed it often declare the same ancestry, and
    # `dogaressa` said «also gives dux» twice in one breath — once for its own
    # reserve and once for `dogaresa`'s.
    diverging: dict[tuple[str, str], list[str]] = {}
    passed: dict[str, list[str]] = {}
    dropped: dict[str, list[str]] = {}

    for reserve in carried.reserves:
        meeting = next(
            (
                index
                for index, held in enumerate(reserve.steps)
                if any(f.lemma and _spellings(f) & named for f in held.forms)
            ),
            None,
        )

        if meeting is None:
            leading = next(
                (
                    form
                    for held in reserve.steps
                    for form in held.forms
                    if form.lemma
                ),
                None,
            )
            contradicts = leading is not None and any(
                impossible_order(leading.language, form.language)
                for form in step.forms
                if form.lemma
            )
            if not contradicts:
                kept.append(reserve)
                continue
            forms = ", ".join(
                _named_forms(held) for held in reserve.steps if _named_forms(held)
            )
            diverging.setdefault(
                (forms, _named_forms(step)), []
            ).append(reserve.source_entry)
            continue

        passed_over = ", ".join(
            _named_forms(held) for held in reserve.steps[:meeting] if _named_forms(held)
        )
        if passed_over:
            passed.setdefault(passed_over, []).append(reserve.source_entry)

        # The two entries met on *one* form of a step that named several, and
        # the rest of that step goes out with it. `dogaressa` derives from
        # «ducarissa, from dux + -issa»; the `ducarissa` page names only
        # `-issa`, the match fired on it, and `dux` — half of a compound, and
        # the half that carries the meaning — disappeared without a word.
        left_behind = ", ".join(
            f"«{form.lemma}»"
            for form in reserve.steps[meeting].forms
            if form.lemma and not _spellings(form) & named
        )
        if left_behind:
            dropped.setdefault(left_behind, []).append(reserve.source_entry)

        kept.append(
            _Reserve(tuple(reserve.steps[meeting + 1:]), reserve.source_entry)
        )

    notes = [
        f"{_attribution(entries, 'continues')} instead with {forms}: "
        f"not drawn, this entry gives {given}"
        for (forms, given), entries in diverging.items()
    ]
    notes += [
        f"{_attribution(entries, 'places')} {forms} at this point, "
        "which this entry does not"
        for forms, entries in passed.items()
    ]
    notes += [
        f"{_attribution(entries, 'also gives')} {forms} here, "
        "which this entry does not"
        for forms, entries in dropped.items()
    ]
    return CarriedChain.of(*kept), "; ".join(notes) or None


@dataclass
class Result:
    """The reconstructed tree, with what is needed to read it."""

    start: Node
    available_senses: int = 1
    chosen_sense: int = 1
    sense_label: str = ""
    requests: int = 0
    cache_hits: int = 0
    duration: float = 0.0
    # Set when the word asked for was an inflected form and the history shown
    # is its lemma's. Deliberately not a link of the chain: `andato` does not
    # *descend* from `andare`, it is the same word inflected, and presenting
    # the two as an etymological step would be a category error.
    asked_for: Form | None = None
    resolution: str = ""
    # Every lemma the entry pointed at, when it pointed at more than one.
    # Populated even after a choice is made, so the answer can say what it
    # chose among instead of presenting one target as if it were the only one.
    pointer_options: list[DefinitionStatement] = field(default_factory=list)

    @property
    def ambiguous_pointer(self) -> bool:
        return len(self.pointer_options) > 1

    @property
    def steps(self) -> int:
        """Length of the longest branch, in number of jumps."""
        return self.start.depth()

    @property
    def resolved(self) -> bool:
        return self.asked_for is not None


class Reconstructor:
    """Walks the etymological graph from a starting form.

    It knows neither the network nor the output format: it takes a
    `WikitextSource` and produces a tree of `Node`. That separation is what
    allows it to be tested against fixed text and, one day, to change source
    without being rewritten.
    """

    def __init__(
        self,
        source: WikitextSource,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        follow_compounds: bool = True,
    ) -> None:
        # Session memory adds no persistence: it only prevents the same page
        # from being requested more than once during a single walk.
        self.source = SessionMemory(source)
        self.max_depth = max_depth
        self.follow_compounds = follow_compounds

    # -- Public interface ----------------------------------------------------

    def senses(self, lemma: str, language: str = "it") -> list[Sense]:
        """The distinct words this spelling stands for, as far as we can tell.

        Costs nothing beyond the page itself, which the walk needs anyway: the
        summaries and the first ancestor of each are read from the same text.
        Returns an empty list when there is nothing to choose between.
        """
        form = Form(lemma=lemma, language=language)
        try:
            wikitext = self.source.wikitext(page_title(form.lemma, form.language))
        except SourceError:
            return []
        if wikitext is None:
            return []

        section = language_section(wikitext, form.language)
        if section is None:
            fallback = fallback_language(form.language)
            section = language_section(wikitext, fallback) if fallback else None
        if section is None:
            return []

        summaries = wikitext_senses(section)
        bodies = etymology_sections(section)
        found: list[Sense] = []
        for index, ((label, part, definition), (_, body)) in enumerate(
            zip(summaries, bodies, strict=True), start=1
        ):
            analysis = parse(body, form.language)
            ancestor = next(
                (f for step in analysis.steps for f in step.forms if f.lemma), None
            )
            found.append(
                Sense(
                    index=index,
                    label=label,
                    part_of_speech=part,
                    definition=definition,
                    ancestor=ancestor,
                    # An inflected form or a misspelling states no origin of its
                    # own: it is not a choice a reader should be asked to make.
                    carries_etymology=bool(
                        analysis.steps or analysis.uncertain or analysis.root
                        or analysis.imitative or analysis.eponym
                        or (analysis.text.strip() and not analysis.not_a_lemma)
                    ),
                )
            )
        return found

    def reconstruct(
        self,
        lemma: str,
        language: str = "it",
        *,
        sense: int = 1,
        follow_lemma: bool = True,
        as_lemma: str | None = None,
        variants: tuple[str, ...] = (),
    ) -> Result:
        """Reconstruct the history of a form down to its terminals.

        When the word asked for is an inflected form with no etymology of its
        own, the lemma it points to is consulted instead. That resolution
        happens once, before the walk starts, and is reported in the result: it
        is a choice of *what to look up*, not a step of the history.
        """
        started = time.monotonic()
        # `variants` carries the other spellings the source gave for this same
        # form. Dropping them here would undo the whole point of keeping them:
        # the walk could no longer fall back on the spelling that has an entry.
        form = Form(lemma=lemma, language=language, variants=tuple(variants))

        reading = self._read(form, sense=sense)

        if follow_lemma:
            resolved = self._resolve_to_lemma(form, reading, sense, started, as_lemma)
            if resolved is not None:
                return resolved

        node = Node(form=form)
        seen = {form.key}

        if reading.terminal is not None:
            node.terminal = reading.terminal
            node.note = self._join("; ".join(reading.analysis.notes) or None,
                                   reading.note)
            if reading.terminal is Terminal.NOT_INTERPRETED:
                node.source_text = reading.analysis.text
            # The starting word deserves its hypotheses as much as any node
            # further up: when it is the uncertain one, they are the whole
            # point of asking.
            node.hypotheses = reading.analysis.hypotheses
        else:
            self._expand_node(node, reading, seen, (form.key,), depth=0,
                              carried=CarriedChain())

        return Result(
            start=node,
            available_senses=reading.total_senses,
            chosen_sense=reading.effective_sense,
            sense_label=reading.sense_label,
            requests=getattr(self.source, "requests_made", 0),
            cache_hits=getattr(self.source, "cache_hits", 0),
            duration=time.monotonic() - started,
        )

    def _resolve_to_lemma(
        self,
        form: Form,
        reading: _Reading,
        sense: int,
        started: float,
        as_lemma: str | None = None,
    ) -> Result | None:
        """Redo the walk on the lemma, when the word asked for is only a form.

        Pointers can chain: `amata` is the feminine of `amato`, which is the
        past participle of `amare`, and only the last of the three carries a
        history. The hops are followed until one of them does, within a short
        limit and never revisiting a form — a pair of entries pointing at each
        other would otherwise loop.

        Two conditions guard each hop. The entry must have produced no history
        of its own, because direct evidence always beats a pointer; and it must
        point somewhere new.
        """
        options = reading.targets
        if as_lemma:
            # Named rather than numbered: the targets have names, so asking for
            # one by position would make the reader learn an order first.
            wanted = as_lemma.casefold()
            chosen = [
                option
                for option in options
                if option.forms[0].bare_lemma.casefold() == wanted
            ]
            if not chosen:
                return None
            reading = replace(reading, points_to=(chosen[0].forms[0],
                                                  chosen[0].wording))

        hops: list[tuple[Form, str]] = []
        visited = {form.key}
        current = reading

        while len(hops) < _MAX_LEMMA_HOPS:
            if current.points_to is None:
                break
            if current.terminal not in _TERMINALS_FROM_ABSENCE:
                break

            target, wording = current.points_to
            if not target.lemma or target.key in visited:
                break

            visited.add(target.key)
            hops.append((target, wording))
            current = self._read(target, sense=sense, propagate=False)

        if not hops:
            return None

        destination = hops[-1][0]
        result = self.reconstruct(
            destination.lemma,
            destination.language,
            sense=sense,
            follow_lemma=False,
            variants=destination.variants,
        )
        result.asked_for = form
        result.resolution = ", ".join(f"{word} «{f.lemma}»" for f, word in hops)
        result.pointer_options = options
        result.duration = time.monotonic() - started
        result.requests = getattr(self.source, "requests_made", 0)
        result.cache_hits = getattr(self.source, "cache_hits", 0)
        return result

    # -- Reading a single form ----------------------------------------------

    @dataclass
    class _Reading:
        """Outcome of querying the source about one form."""

        analysis: Analysis = field(default_factory=Analysis)
        terminal: Terminal | None = None
        note: str | None = None
        total_senses: int = 0
        effective_sense: int = 1
        sense_label: str = ""
        # The lemma this entry declares itself a form of, when it does.
        points_to: tuple[Form, str] | None = None
        # Every distinct lemma the definition lines point at. More than one
        # means the spelling stands for unrelated words, and choosing silently
        # would answer a question the reader did not ask.
        targets: list[DefinitionStatement] = field(default_factory=list)
        # True when the steps below were read from a definition line.
        from_definition: bool = False

    def _read(self, form: Form, *, sense: int = 1, propagate: bool = True) -> _Reading:
        """Query the source and classify the outcome.

        A set terminal means "the walk stops here", and the reason says whether
        it was the language that stopped or the tool.
        """
        if not form.lemma:
            # The entry named a language and gave no word. We read that
            # correctly; it is the source that stops short, so the terminal
            # must say so rather than claim the language had nothing left.
            return self._Reading(terminal=Terminal.FORM_NOT_GIVEN)

        # A reconstructed form in a language we do not have in our table cannot
        # be looked up: the `Reconstruction:` path needs the canonical name, and
        # the code alone builds a title that cannot exist. Asking anyway and
        # reading the 404 as the end of the chain would blame the language for a
        # gap in our own data.
        if form.reconstructed and not can_locate_reconstruction(form.language):
            return self._Reading(
                terminal=Terminal.LANGUAGE_MISSING,
                note=f"«{form.language}» is not in our table of languages, "
                     "so its reconstructions cannot be looked up",
            )

        # An entry may give one form in several spellings — `[[-ere]], [[-er]]`,
        # `onza,oncia`. Each is named by the source, so following any of them is
        # following what the source says; they are tried in order and the first
        # with an entry of its own is the one read. `onza` has a page but no
        # Italian section, `oncia` has both — stopping at the first would leave
        # a chain the entry had fully described.
        section: str | None = None
        section_language = form.language
        section_note: str | None = None
        found_a_page = False

        for spelling in (form.lemma, *form.variants):
            try:
                wikitext = self.source.wikitext(page_title(spelling, form.language))
            except SourceError:
                if propagate:
                    raise
                return self._Reading(terminal=Terminal.NETWORK_ERROR)

            if wikitext is None:
                continue
            found_a_page = True

            section = language_section(wikitext, form.language)
            if section is None:
                fallback = fallback_language(form.language)
                if fallback:
                    section = language_section(wikitext, fallback)
                    if section is not None:
                        section_language = fallback
                        section_note = (
                            f"the entry does not separate {form.language_name}: "
                            f"read under {language_name(fallback)}"
                        )

            if section is not None:
                if spelling != form.lemma:
                    section_note = self._join(
                        section_note, f"read under the spelling «{spelling}»"
                    )
                break

        if not found_a_page:
            return self._Reading(terminal=self._data_end(form, Terminal.ENTRY_MISSING))

        if section is None:
            return self._Reading(
                terminal=self._data_end(form, Terminal.LANGUAGE_MISSING),
                note=f"the page exists but does not cover {form.language_name}",
            )

        # Read before deciding: an entry can declare itself a form of another
        # word *and* carry an etymology of its own, and when it does its own is
        # the better evidence.
        statements = definition_statements(section, section_language)
        declared = statements[0] if statements else None
        pointers = _distinct_targets(statements)
        pointer = (
            (pointers[0].forms[0], pointers[0].wording) if pointers else None
        )

        etymologies = etymology_sections(section)
        if not etymologies:
            # We did read the entry, and it records no origin. For a
            # reconstructed form that is the answer: comparative reconstruction
            # goes no further, and Wiktionary marks it by writing nothing. For
            # an attested word it is a gap in the source.
            terminal = (
                Terminal.RECONSTRUCTED_FORM
                if form.reconstructed
                else Terminal.ETYMOLOGY_MISSING
            )
            reading = self._Reading(
                terminal=terminal,
                note=section_note,
                points_to=pointer,
                targets=pointers,
            )
            return self._apply_declaration(reading, declared)

        index = min(max(sense, 1), len(etymologies)) - 1
        label, text = etymologies[index]
        analysis = parse(text, section_language)
        if section_note:
            analysis.notes.insert(0, section_note)

        reading = self._Reading(
            analysis=analysis,
            total_senses=len(etymologies),
            effective_sense=index + 1,
            sense_label=label,
            points_to=pointer,
            targets=pointers,
        )

        reading.terminal = self._classify(form, analysis)
        return self._apply_declaration(reading, declared)

    @staticmethod
    def _apply_declaration(
        reading: _Reading, declared: DefinitionStatement | None
    ) -> _Reading:
        """Let a definition line speak where the etymology section is silent.

        Only where it is silent: an entry that states its own history has said
        the better thing, and a definition line is a synchronic statement — it
        describes what the word *is*, not necessarily how it got here.

        Pointers are left alone; they are resolved before the walk starts, and
        turning one into a link would claim that a word descends from its own
        lemma.
        """
        if declared is None or reading.terminal not in _TERMINALS_FROM_ABSENCE:
            return reading

        if declared.kind is Declaration.POINTER:
            return reading

        if declared.relation is not None and declared.forms:
            reading.analysis.steps = [
                Step(relation=declared.relation, forms=list(declared.forms))
            ]
            reading.terminal = None
            # Only evaluative derivation carries a judgement of ours: a word
            # analysable as a diminutive of X may have been inherited already
            # formed. A contraction has no such alternative — `dal` *is*
            # `da` + `il` — so marking it would cry wolf.
            reading.from_definition = declared.kind is Declaration.DERIVATION

        return reading

    @staticmethod
    def _classify(form: Form, analysis: Analysis) -> Terminal | None:
        """The terminal implied by a reading, or None to keep walking.

        Order matters, and it is an order of authority. What the source states
        outright comes first; what we merely failed to read comes last, and says
        so.
        """
        # A declared uncertainty is the conclusion, even when proposals follow
        # it. "Of uncertain origin. Perhaps from X" is not a chain: it is a
        # doubt with a suggestion, and walking the suggestion would replace the
        # source's own verdict with one of its guesses.
        if analysis.uncertain:
            return Terminal.UNCERTAIN_ORIGIN
        if analysis.no_etymology_yet:
            return Terminal.ETYMOLOGY_MISSING
        if analysis.not_a_lemma:
            return Terminal.ETYMOLOGY_MISSING
        if analysis.steps:
            return None
        if analysis.eponym is not None:
            return Terminal.EPONYM
        if analysis.imitative:
            return Terminal.IMITATIVE
        if analysis.root is not None:
            return None
        # Nothing readable. If the section nevertheless said something, that is
        # a failure of ours and must be reported as such, with the text, rather
        # than as the language having nothing left to say.
        if analysis.prose.strip():
            return Terminal.NOT_INTERPRETED
        return Reconstructor._data_end(form, Terminal.DATA_EXHAUSTED)

    @staticmethod
    def _data_end(form: Form, default: Terminal) -> Terminal:
        """Reclassify *exhausted data* when the form is already reconstructed.

        Reading a proto-form's entry and finding nothing beyond it is not a gap
        in the source: it is where comparative reconstruction stops, and one of
        the terminals we set out to recognise.

        The reclassification applies to that case only. Not having found the
        page, or the language section, or any etymology at all, means we did not
        read anything — and silence we never heard is not evidence that the
        language falls silent. Those keep their own terminal, which says the
        limit is ours or the source's.
        """
        if default is Terminal.DATA_EXHAUSTED and form.reconstructed:
            return Terminal.RECONSTRUCTED_FORM
        return default

    # -- Recursive expansion of the tree -------------------------------------

    def _expand_node(
        self,
        node: Node,
        reading: _Reading,
        seen: set[tuple[str, str]],
        path: tuple[tuple[str, str], ...],
        depth: int,
        carried: CarriedChain,
    ) -> None:
        """Attach to `node` the children implied by the reading, recursively."""
        analysis = reading.analysis
        node.hypotheses = analysis.hypotheses
        notes = list(analysis.notes)

        if reading.total_senses > 1:
            notes.append(
                f"the entry records {reading.total_senses} distinct etymologies; "
                f"following «{reading.sense_label}»"
            )
        if reading.note:
            notes.append(reading.note)

        choice = self._next_step(analysis, node, carried)

        # Stages named without a form do not become links, but they remain part
        # of the story: omitting them would make a passage the source describes
        # as mediated look direct.
        for skipped in choice.skipped:
            notes.append(
                f"{skipped.relation.describe(skipped.forms[0].language)}, "
                "whose form the source does not give"
            )

        # Two entries disagreeing is a fact about the sources, and belongs
        # where the reader is looking. It is deliberately not a branch — that
        # would claim two ancestors — nor a hypothesis: neither entry is
        # guessing, they simply do not say the same thing.
        if choice.divergence:
            notes.append(choice.divergence)

        if notes:
            node.note = "; ".join(notes)

        step = choice.step
        if step is None:
            if choice.skipped:
                node.terminal = Terminal.FORM_NOT_GIVEN
                return
            self._close(node, analysis)
            return

        if (
            step.relation in (Relation.COMPOUND, Relation.AFFIXATION)
            and not self.follow_compounds
        ):
            node.terminal = Terminal.DATA_EXHAUSTED
            node.note = self._join(
                node.note, f"{step.relation.label} several elements (not followed)"
            )
            return

        # A compound may be missing the form of just one component: follow what
        # is cited, without giving graphical body to a link that does not exist.
        usable = [form for form in step.forms if form.lemma]
        # Forms the entry points back to, already on this branch.
        looping: list[Form] = []

        # A compound splits the walk in two, and a reserve cannot be handed to
        # both: `obtūrō` is «ob- + *tūrō, the second component from *tūrāō, from
        # *tewh₂-», and only the source knows which branch the continuation
        # belongs to. Reading "the second component" would be interpretation,
        # which this version keeps out — but discarding what the entry plainly
        # states is worse than declaring it unattached.
        if choice.carried and len(usable) > 1:
            continuation = [
                f"{form.lemma} ({form.language})"
                for carried_step in choice.carried.steps
                for form in carried_step.forms
                if form.lemma
            ]
            if continuation:
                node.note = self._join(
                    node.note,
                    f"the entry continues with {', '.join(continuation)}, "
                    "without saying which component from",
                )

        for index, form in enumerate(usable):
            # Knowing a link is impossible and drawing it anyway is the worst of
            # both: the tree asserts a descent the program has already proved
            # cannot have happened, and the note beneath it is read as a caveat
            # rather than as a refutation. The form is kept — the entry does
            # mention it — but as a conjecture, where a claim we disbelieve
            # belongs.
            if impossible_order(form.language, node.form.language):
                node.hypotheses.append(
                    Hypothesis(
                        form=form,
                        attribution=(
                            f"the entry gives {form.language_name} as the ancestor "
                            f"of {node.form.language_name}, which is later: not "
                            "drawn as a link"
                        ),
                    )
                )
                continue

            # The carried chain applies to the main line only: on a side branch
            # of a compound it would be information out of place.
            child_carried = (
                choice.carried if index == 0 and len(usable) == 1 else CarriedChain()
            )
            child = self._expand(
                form, step.relation, seen, path, depth + 1, child_carried
            )
            if child is None:
                # A circular reference: reported on the form that closes the
                # loop, never drawn as a descent.
                looping.append(form)
                continue
            child.from_definition = reading.from_definition
            # Either the relation never claimed adjacency, or the text said so.
            child.skips_stages = (
                not step.relation.implies_contiguity or step.skips_stages
            )
            if choice.reported_by and index == 0:
                child.note = self._join(
                    child.note, f"step reported by the entry «{choice.reported_by}»"
                )
            node.children.append(child)

        if looping:
            names = ", ".join(f"«{form.lemma}»" for form in looping)
            node.note = self._join(
                node.note, f"the entry points back to {names}, already on this branch"
            )
            if not node.children:
                node.terminal = Terminal.CYCLE

    def _expand(
        self,
        form: Form,
        relation: Relation,
        seen: set[tuple[str, str]],
        path: tuple[tuple[str, str], ...],
        depth: int,
        carried: CarriedChain,
    ) -> Node | None:
        """Create the node for a form and continue the walk from it.

        `path` holds the ancestors of the current branch, `seen` every form met
        anywhere in the tree. The two answer different questions, and conflating
        them was making convergence look like a fault: a form already in `path`
        is a real circular reference in the source, while one merely in `seen`
        is a branch rejoining another — which in etymology is not an anomaly but
        the normal shape of a family.

        Returns None on a circular reference. Drawing the repeated form as a
        child would put «πίτα ← πίτα» in the tree — a word descending from
        itself, which is not a thing that can be true — and would make the
        chain look one link longer than the source claims. The caller reports
        the loop instead.
        """
        node = Node(form=form, relation=relation)

        if form.key in path:
            return None
        if form.key in seen:
            node.terminal = Terminal.ALREADY_SHOWN
            return node
        if depth >= self.max_depth:
            node.terminal = Terminal.DEPTH_LIMIT
            return node

        seen.add(form.key)
        path = (*path, form.key)
        reading = self._read(form, propagate=False)

        if reading.terminal is not None:
            recoverable = reading.terminal in _TERMINALS_FROM_ABSENCE and carried
            if not recoverable:
                node.terminal = reading.terminal
                node.note = self._join("; ".join(reading.analysis.notes) or None,
                                       reading.note)
                if reading.terminal is Terminal.NOT_INTERPRETED:
                    node.source_text = reading.analysis.text
                node.hypotheses = reading.analysis.hypotheses
                # The chain ends here and an earlier entry was still holding
                # forms. Right not to walk them — this source has spoken — but
                # dropping them in silence loses what that entry declared.
                # What this node already shows is not lost, and must not be
                # reported as such.
                displayed = frozenset(
                    name
                    for candidate in (node.form, *(h.form for h in node.hypotheses))
                    for name in _spellings(candidate)
                )
                node.note = self._join(node.note, _unspent(carried, displayed) or None)
                return node
            node.note = self._join(
                reading.note, f"{reading.terminal.label}: continuing indirectly"
            )

        self._expand_node(node, reading, seen, path, depth, carried)
        return node

    def _next_step(
        self, analysis: Analysis, node: Node, carried: CarriedChain
    ) -> _Choice:
        """Pick the step to walk, with its possible continuation.

        If the source speaks, follow the source and let its further steps become
        the reserve, credited to the entry that states them. If it is silent,
        fall back on what was declared upstream, keeping the original
        attribution: it is that entry, not the current link, that asserts the
        passage.

        What the entry says does not *replace* the reserve, it goes in front of
        it. The two are about different stretches of the same path — the entry
        knows the next link, the entry that sent us here often knows further —
        and dropping the reserve on the grounds that someone nearer has spoken
        loses history that was already in hand.
        """
        skipped: list[Step] = []

        if analysis.steps:
            step, skipped, rest = _first_usable(analysis.steps)
            if step is not None:
                behind, divergence = _reconcile(carried, step)
                return _Choice(
                    step=step,
                    carried=CarriedChain.of(
                        _Reserve(tuple(rest), node.form.lemma), *behind.reserves
                    ),
                    skipped=skipped,
                    divergence=divergence,
                )
            # The entry named stages and no form for any of them. It has not
            # said where to go next, so the reserve is still the best we have.

        step, held_back, reported_by, remaining = carried.take()
        return _Choice(
            step=step,
            carried=remaining,
            reported_by=reported_by or None,
            skipped=skipped + held_back,
        )

    def _close(self, node: Node, analysis: Analysis) -> None:
        """Close a branch that has no continuation.

        A declared uncertainty prevails over everything: if the source says it
        does not know, the chain ends there even when roots are ventured
        elsewhere.
        """
        if analysis.uncertain:
            node.terminal = Terminal.UNCERTAIN_ORIGIN
            return

        if analysis.root is not None:
            # The entry declares the ultimate root without spelling out the
            # intermediate stages: we append it as a terminal, which is what it
            # is. This one really is a root — the source says so — unlike the
            # proto-forms we reach by walking, which are words or affixes.
            node.children.append(
                Node(
                    form=analysis.root,
                    relation=Relation.ROOT,
                    terminal=Terminal.RECONSTRUCTED_ROOT,
                )
            )
            return

        node.terminal = self._classify(node.form, analysis) or self._data_end(
            node.form, Terminal.DATA_EXHAUSTED
        )
        if node.terminal is Terminal.NOT_INTERPRETED:
            node.source_text = analysis.text

    @staticmethod
    def _join(existing: str | None, addition: str | None) -> str | None:
        if not addition:
            return existing
        return f"{existing}; {addition}" if existing else addition
