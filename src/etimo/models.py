"""Data model of the etymological graph.

The vocabulary here is deliberately that of historical linguistics rather than
of generic graphs: a `Step` is not merely an edge, it is a claim about *how* a
form reached the next language, and the difference between inheritance and
borrowing is the substance of the story, not an incidental attribute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .languages import is_known_language, is_reconstructed, language_name


class Relation(Enum):
    """How a form descends from the one preceding it.

    The enum value is (label, needs_language): the label is what the reader
    sees, and `needs_language` says whether the phrase must be completed with
    the source language ("inherited from Latin").
    """

    INHERITED = ("inherited", True)
    BORROWED = ("borrowed", True)
    UNADAPTED_BORROWING = ("borrowed unadapted", True)
    LEARNED_BORROWING = ("learned borrowing", True)
    SEMI_LEARNED_BORROWING = ("semi-learned borrowing", True)
    ORTHOGRAPHIC_BORROWING = ("orthographic borrowing", True)
    CALQUE = ("calqued", True)
    PARTIAL_CALQUE = ("partially calqued", True)
    SEMANTIC_LOAN = ("semantic loan", True)
    DERIVED = ("derived", True)
    ROOT = ("root in", True)
    COMPOUND = ("compound of", False)
    AFFIXATION = ("formed with affixes from", False)
    # Evaluative suffixation. Kept apart from plain affixation because the
    # source states it in the definition line rather than in an etymology, and
    # the output says so.
    DIMINUTIVE = ("diminutive of", False)
    AUGMENTATIVE = ("augmentative of", False)
    CLIPPING = ("clipping of", False)
    ABBREVIATION = ("abbreviation of", False)
    BACK_FORMATION = ("back-formation from", False)
    # Word formation that stays inside one language: the source names the base,
    # not another language, so no language is added to the phrase.
    DEVERBAL = ("deverbal of", False)
    DENOMINAL = ("denominal of", False)
    NOMINALIZATION = ("nominalization of", False)
    CAUSATIVE = ("causative of", False)
    REDUPLICATION = ("reduplication of", False)
    METATHESIS = ("metathesis of", False)
    REBRACKETING = ("rebracketing of", False)
    # A variant is not an ancestor in the strict sense, but the source uses it
    # to point at the form that carries the etymology.
    VARIANT = ("variant of", False)

    def __init__(self, label: str, needs_language: bool) -> None:
        self.label = label
        self.needs_language = needs_language

    def describe(self, language_code: str | None) -> str:
        """Render the relation as a phrase, naming the source language.

        For codes we do not know, saying so outright is better than printing a
        bare code where a language name is expected.
        """
        if not self.needs_language or not language_code:
            return self.label
        if is_known_language(language_code):
            return f"{self.label} from {language_name(language_code)}"
        return f"{self.label} from an unregistered language ({language_code})"

    @property
    def implies_contiguity(self) -> bool:
        """Whether the source asserts that no stage sits between the two forms.

        The distinction is Wiktionary's own, and it is easy to lose. `{{inh}}`
        claims unbroken transmission and `{{bor}}` a direct loan; `{{der}}`
        claims only that one form goes back to the other *ultimately*, saying
        nothing about what lies in between. Drawn identically, three `der` links
        read as three successive stages when they may hide a dozen.
        """
        return self not in _SKIPS_STAGES


# Relations that may hide intermediate stages. Everything else — inheritance,
# borrowing, calquing, word formation inside one language — names a passage the
# source presents as immediate.
#
# `ROOT` belongs here for the same reason as `DERIVED`: the ultimate root of a
# word is by definition reached across every stage in between, none of which
# the entry lists.
_SKIPS_STAGES = frozenset({Relation.DERIVED, Relation.ROOT})


class Terminal(Enum):
    """Why the walk stopped.

    The ones marked linguistic are facts about the language; the others are
    limits of the tool or of the source, and must be reported as such — a
    technical limit dressed up as the end of the story would be a lie.

    The rule that keeps the two apart: a linguistic terminal may be emitted
    only on *positive evidence* — the source said something we understood. Not
    finding what we can read is never, by itself, a fact about the language;
    that is what `NOT_INTERPRETED` is for.

    The enum value is (label, symbol, is_linguistic).
    """

    # A proto-form reached by walking up is a reconstructed *form* — a word or
    # an affix. Only what the source marks with {{root}} is a root proper, and
    # the distinction is not cosmetic: in Indo-European studies root, stem and
    # affix are different things.
    RECONSTRUCTED_FORM = ("reconstructed form", "√", True)
    # The one declared exception to "no linguistic terminal without reading the
    # page". A root is not a word with a history of its own — it is the abstract
    # element words are built from — so "what is the etymology of *ḱel-?" is not
    # a well-formed question the way it is for *patēr, and there is no page
    # whose silence we would be interpreting. The positive evidence is the
    # entry's own {{root}}, which asserts it outright; nothing further is
    # fetched, and nothing further needs to be.
    RECONSTRUCTED_ROOT = ("reconstructed root", "√", True)
    IMITATIVE = ("imitative origin", "≈", True)
    EPONYM = ("named after a person or place", "≡", True)
    UNCERTAIN_ORIGIN = ("uncertain origin", "⊗", True)
    DATA_EXHAUSTED = ("data exhausted", "·", True)
    # Not a limit: the branch converges on a form already reconstructed
    # elsewhere in the tree. Repeating the subtree would say nothing new.
    ALREADY_SHOWN = ("already shown above", "=", True)
    # The entry does say where the word came from — it just does not say what
    # the word was. Reading that correctly is not the same as the language
    # having nothing further to give, and for ~300 Italian entries the
    # difference is the whole point of keeping facts and limits apart.
    FORM_NOT_GIVEN = ("source names the language, not the form", "◌", False)
    ENTRY_MISSING = ("no Wiktionary entry", "?", False)
    LANGUAGE_MISSING = ("language not covered by the entry", "?", False)
    ETYMOLOGY_MISSING = ("no etymology recorded", "?", False)
    # The entry says something the parser could not turn into a step. The text
    # is reported verbatim rather than passed off as silence from the language.
    NOT_INTERPRETED = ("etymology not interpreted", "?", False)
    DEPTH_LIMIT = ("depth limit reached", "↓", False)
    CYCLE = ("circular reference", "↺", False)
    NETWORK_ERROR = ("data not retrievable", "!", False)

    def __init__(self, label: str, symbol: str, is_linguistic: bool) -> None:
        self.label = label
        self.symbol = symbol
        # True when the terminal is a fact about the language, False when it is
        # a limit of the tool or of the source.
        self.is_linguistic = is_linguistic


@dataclass(frozen=True)
class Form:
    """A lexical form, attested or reconstructed, in a given language."""

    lemma: str
    language: str  # Wiktionary code: "la", "grc", "ine-pro"
    gloss: str | None = None
    transliteration: str | None = None
    # Other spellings the entry gives for this same form, in one parameter:
    # `{{inh|en|enm|[[-ere]], [[-er]]}}` is one suffix written two ways, not two
    # ancestors. Kept beside the lemma rather than glued into it — joined, the
    # string becomes a page title that cannot exist, and the chain closes on a
    # false "no entry".
    variants: tuple[str, ...] = ()

    @property
    def reconstructed(self) -> bool:
        return self.lemma.startswith("*") or is_reconstructed(self.language)

    @property
    def language_name(self) -> str:
        return language_name(self.language)

    @property
    def bare_lemma(self) -> str:
        """The lemma without the reconstruction asterisk."""
        return self.lemma.lstrip("*")

    @property
    def key(self) -> tuple[str, str]:
        """Node identity, used for deduplication and cycle detection."""
        return (self.language, self.bare_lemma.casefold())

    def __str__(self) -> str:
        text = self.lemma
        if self.transliteration:
            text += f" /{self.transliteration}/"
        return text


@dataclass
class Step:
    """A single etymological jump read from the source.

    Forms are a list because a step can branch: a compound such as
    "capolavoro" goes back to both "capo" and "lavoro", and neither is the
    "real" ancestor at the expense of the other.
    """

    relation: Relation
    forms: list[Form] = field(default_factory=list)
    # Set when an adverb in the text says this link is not the immediate one:
    # "ultimately from X" states outright that stages lie in between.
    skips_stages: bool = False

    @property
    def branching(self) -> bool:
        return len(self.forms) > 1


@dataclass
class Hypothesis:
    """A derivation proposed but not accepted as certain by the source.

    Kept strictly out of the main chain: it is shown below the terminal, with
    its attribution, so the reader knows it is conjecture.
    """

    form: Form
    attribution: str | None = None


class Declaration(Enum):
    """What a definition line says the page is.

    Three different statements hide behind the same shape, and they need three
    different answers. Collapsing them was making the tool claim that ~2 400
    Italian entries had no data at all, while the data sat in a template one
    line below.

    A fourth was recognised until acronyms were taken out of scope: an entry
    unfolding into a phrase — `CEI` into «Conferenza Episcopale Italiana» —
    used to terminate on it. An acronym does not descend from its expansion;
    it is a way of writing it, which is a question about spelling and not
    about history.

    If they ever come back, design the ambiguity first. `CEI` has *two*
    expansions on Wiktionary — Conferenza Episcopale Italiana and Comitato
    Elettrotecnico Italiano — and the removed code took the first in silence,
    while pointers with several targets have been offered as a choice since
    `po'`. It was the same defect wearing a different template, and it stayed
    invisible for as long as it did because nothing ever printed the one it
    dropped.
    """

    # The same word, in another form or spelling: `far` is `fare` shortened.
    POINTER = "pointer"
    # A different word, formed from another: `tubicino` from `tubo`.
    DERIVATION = "derivation"
    # Two sources at once: `dal` is `da` + `il`.
    CONTRACTION = "contraction"


@dataclass
class DefinitionStatement:
    """A declaration read from a definition line, ready for the walker."""

    kind: Declaration
    wording: str
    forms: list[Form] = field(default_factory=list)
    relation: Relation | None = None
    # Where the declaration was read, and what the entry glosses it as. Both
    # exist for the reader's sake: when one spelling points at several lemmas,
    # these are what tells them apart — `po'` is `poco` as a noun and `puoi`
    # as a verb, and nobody recognises those by position.
    part_of_speech: str = ""
    gloss: str = ""

    @property
    def target(self) -> Form | None:
        return self.forms[0] if self.forms else None

    def describe(self) -> str:
        """A one-line summary, for choosing between several targets."""
        parts = [p for p in (self.part_of_speech, self.gloss) if p]
        return " · ".join(parts) if parts else self.wording


@dataclass
class Sense:
    """One of the several unrelated words a spelling can stand for.

    Italian "riso" is both the grain and the laughter, and they have nothing to
    do with each other. Asking a reader for "etymology number 3" assumes they
    already know what the third one is; what they can actually recognise is the
    meaning, and the ancestor it leads to.
    """

    index: int  # 1-based, as `--sense` expects it
    label: str  # the section heading: "Etymology 2"
    part_of_speech: str = ""
    definition: str = ""
    ancestor: Form | None = None
    # False when the section states no origin of its own — an inflected form, a
    # misspelling, a bare cross-reference. Those are not choices worth offering.
    carries_etymology: bool = False

    def describe(self) -> str:
        """A one-line summary, for a reader choosing between homographs."""
        parts = [p for p in (self.part_of_speech, self.definition) if p]
        return " · ".join(parts) if parts else self.label


@dataclass
class Node:
    """One link of the chain, with its branches."""

    form: Form
    relation: Relation | None = None  # how it descends from the parent node
    children: list[Node] = field(default_factory=list)
    terminal: Terminal | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    note: str | None = None
    # What the entry says, when we could not turn it into a step. Showing it is
    # the difference between "the language has nothing more" and "we did not
    # understand this" — and the reader can judge for themselves.
    source_text: str | None = None
    # True when this link was read from a definition line rather than from an
    # etymology section. The source states the derivation either way, but in
    # the definition it states it synchronically: `navicella` is analysable as
    # a diminutive of `nave` and yet came from Latin already formed. The guard
    # keeps those out — they have etymologies of their own — but the reader is
    # told where the claim was read, so a wrong one stays visible.
    from_definition: bool = False
    # True when this link may hide intermediate stages — either because the
    # relation never claimed adjacency, or because the text said so.
    skips_stages: bool = False

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def depth(self) -> int:
        """Number of steps along the longest branch."""
        if not self.children:
            return 0
        return 1 + max(child.depth() for child in self.children)

    def count_nodes(self) -> int:
        return 1 + sum(child.count_nodes() for child in self.children)

    def main_chain(self) -> list[Node]:
        """The primary branch: at every fork the first child is followed.

        Wiktionary lists the load-bearing element first by convention, so this
        is the main line of descent rather than an arbitrary pick.
        """
        path = [self]
        current = self
        while current.children:
            current = current.children[0]
            path.append(current)
        return path

    def terminals(self) -> list[Node]:
        """Every leaf of the tree, in visit order."""
        if not self.children:
            return [self]
        return [t for child in self.children for t in child.terminals()]
