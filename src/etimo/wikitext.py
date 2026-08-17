"""Reading etymology sections from Wiktionary wikitext.

Three principles guide this module.

**Whitelist, not blacklist.** Only templates we know how to interpret produce a
step of the chain; everything else is ignored. Wiktionary holds hundreds of
templates and keeps adding more: trying to enumerate the ones to discard would
sooner or later mistake something for an ancestor that is not one.

**Textual order is the order of the chain.** Wiktionary marks every relation
relative to the language of the entry, not to the previous link: in `caffè`
both the borrowing from Ottoman Turkish and the derivation from Arabic declare
`it` as their starting point. The sequence must therefore be read from the
order of the templates in the sentence.

**Conjectures stay conjectures.** Derivations proposed in bulleted lists
("Some connect this to…", "Matasović opts to derive from…") never enter the
chain: they are collected separately as hypotheses, with their attribution.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import mwparserfromhell
from mwparserfromhell.nodes import Template

from .languages import is_known_language, wiktionary_name
from .models import (
    Declaration,
    DefinitionStatement,
    Form,
    Hypothesis,
    Relation,
    Step,
)

# --- Templates describing a passage from one language to another ----------
# Common signature: {{name|entry_language|source_language|lemma|alt|gloss}}
# Every template is listed under *all* the names it can be invoked with:
# Wiktionary redirects `lbor` to `learned borrowing` and both appear in entries,
# so recognising one and not the other would make the same fact readable or
# invisible depending on which synonym an editor happened to type.
_LINEAR_RELATIONS: dict[str, Relation] = {
    "inh": Relation.INHERITED,
    "inherited": Relation.INHERITED,
    "bor": Relation.BORROWED,
    "borrowed": Relation.BORROWED,
    "ubor": Relation.UNADAPTED_BORROWING,
    "unadapted borrowing": Relation.UNADAPTED_BORROWING,
    "abor": Relation.BORROWED,
    "adapted borrowing": Relation.BORROWED,
    "lbor": Relation.LEARNED_BORROWING,
    "learned borrowing": Relation.LEARNED_BORROWING,
    "slbor": Relation.SEMI_LEARNED_BORROWING,
    "slb": Relation.SEMI_LEARNED_BORROWING,
    "semi-learned borrowing": Relation.SEMI_LEARNED_BORROWING,
    "obor": Relation.ORTHOGRAPHIC_BORROWING,
    "orthographic borrowing": Relation.ORTHOGRAPHIC_BORROWING,
    "cal": Relation.CALQUE,
    "calque": Relation.CALQUE,
    "clq": Relation.CALQUE,
    "pcal": Relation.PARTIAL_CALQUE,
    "pclq": Relation.PARTIAL_CALQUE,
    "partial calque": Relation.PARTIAL_CALQUE,
    "sl": Relation.SEMANTIC_LOAN,
    "semantic loan": Relation.SEMANTIC_LOAN,
    "psm": Relation.BORROWED,
    "phono-semantic matching": Relation.BORROWED,
    "translit": Relation.BORROWED,
    "transliteration": Relation.BORROWED,
    "der": Relation.DERIVED,
    "derived": Relation.DERIVED,
    # `uder` is "undefined derivation": the source asserts the origin without
    # dating the passage. It is a link all the same, and a frequent one.
    "uder": Relation.DERIVED,
    "der?": Relation.DERIVED,
    "undefined derivation": Relation.DERIVED,
}

# --- Templates for word formation inside the language ---------------------
# Components sit in the positional parameters from the second onwards.
_WORD_FORMATION_RELATIONS: dict[str, Relation] = {
    "af": Relation.AFFIXATION,
    "affix": Relation.AFFIXATION,
    "suf": Relation.AFFIXATION,
    "suffix": Relation.AFFIXATION,
    "pre": Relation.AFFIXATION,
    "pref": Relation.AFFIXATION,
    "prefix": Relation.AFFIXATION,
    "infix": Relation.AFFIXATION,
    "con": Relation.AFFIXATION,
    "confix": Relation.AFFIXATION,
    "com": Relation.COMPOUND,
    "compound": Relation.COMPOUND,
    "blend": Relation.COMPOUND,
    "blend of": Relation.COMPOUND,
    "univerbation": Relation.COMPOUND,
    "univ": Relation.COMPOUND,
    "clipped compound": Relation.COMPOUND,
    "clipcomp": Relation.COMPOUND,
    "clipping": Relation.CLIPPING,
    "clip": Relation.CLIPPING,
    "clipping of": Relation.CLIPPING,
    "short for": Relation.CLIPPING,
    "shortening": Relation.CLIPPING,
    "sh": Relation.CLIPPING,
    "ellipsis": Relation.CLIPPING,
    "ellip": Relation.CLIPPING,
    "ellipsis of": Relation.CLIPPING,
    "apheretic form": Relation.CLIPPING,
    "apocopic form": Relation.CLIPPING,
    "apocopic form of": Relation.CLIPPING,
    "syncopic form": Relation.CLIPPING,
    "sync": Relation.CLIPPING,
    "prothetic form": Relation.CLIPPING,
    "contraction": Relation.CLIPPING,
    "contr": Relation.CLIPPING,
    "contraction of": Relation.CLIPPING,
    "abbreviation": Relation.ABBREVIATION,
    "abbrev": Relation.ABBREVIATION,
    "abbreviation of": Relation.ABBREVIATION,
    "acronym": Relation.ABBREVIATION,
    "acro": Relation.ABBREVIATION,
    "acronym of": Relation.ABBREVIATION,
    "initialism": Relation.ABBREVIATION,
    "init": Relation.ABBREVIATION,
    "initialism of": Relation.ABBREVIATION,
    "syllabic abbreviation": Relation.ABBREVIATION,
    "sylabbr": Relation.ABBREVIATION,
    "back-form": Relation.BACK_FORMATION,
    "backform": Relation.BACK_FORMATION,
    "backformation": Relation.BACK_FORMATION,
    "back-formation": Relation.BACK_FORMATION,
    "back formation": Relation.BACK_FORMATION,
    "back-formation of": Relation.BACK_FORMATION,
    "bf": Relation.BACK_FORMATION,
    "b-f": Relation.BACK_FORMATION,
    "deverbal": Relation.DEVERBAL,
    "deverbative": Relation.DEVERBAL,
    "it-deverbal": Relation.DEVERBAL,
    "it-deverbal fpp": Relation.DEVERBAL,
    "it-verb-obj": Relation.COMPOUND,
    "it-verb-verb": Relation.COMPOUND,
    "denominal verb": Relation.DENOMINAL,
    "nominalization": Relation.NOMINALIZATION,
    "nom": Relation.NOMINALIZATION,
    "causative": Relation.CAUSATIVE,
    "reduplication": Relation.REDUPLICATION,
    "rdp": Relation.REDUPLICATION,
    "redup": Relation.REDUPLICATION,
    "metathesis": Relation.METATHESIS,
    "rebracketing": Relation.REBRACKETING,
    "alt form": Relation.VARIANT,
    "alternative form of": Relation.VARIANT,
}

# --- Templates declaring an unknown or doubtful origin --------------------
_UNCERTAINTY = {"unk", "unknown", "unc", "uncertain", "unknown origin"}

# --- Templates declaring an imitative origin ------------------------------
_ONOMATOPOEIA = {"onom", "onomatopoeic", "onomatopeic", "onomatopoeia", "imitative",
                 "sound symbolic", "sound-symbolic"}

# --- Templates naming the person or place a word comes from ---------------
_EPONYM = {"named after", "named-after", "eponym"}

# --- Templates by which the source declares it has no etymology yet -------
# This is not silence from the language: it is the source saying, explicitly,
# that the work has not been done. It deserves a terminal of its own.
_NO_ETYMOLOGY_YET = {"rfe", "request for etymology", "rfetym", "rfety", "etystub"}

# --- Templates saying the page is a form, not a lemma ---------------------
_NOT_A_LEMMA = {"nonlemma", "nonlemmas", "non-lemma", "nl"}

# --- Templates carrying an ancillary remark, never a link -----------------
_REMARKS: dict[str, str] = {
    "surf": "synchronically analysable as",
    "surface analysis": "synchronically analysable as",
    "surface etymology": "synchronically analysable as",
    "pseudo-loan": "pseudo-loan modelled on",
    "pl": "pseudo-loan modelled on",
    "pseudoloan": "pseudo-loan modelled on",
    "pseudo-acronym": "pseudo-acronym",
    "internationalism": "an internationalism",
    "intnat": "an internationalism",
    "coinage": "deliberately coined",
    "coin": "deliberately coined",
    "coined": "deliberately coined",
    "genericized trademark": "from a genericised trademark",
    "gentrade": "from a genericised trademark",
    "displaced": "displaced an earlier term",
    "semantic shift": "with a shift in meaning",
    "ss": "with a shift in meaning",
    "false cognate": "resembles, without being related to",
    "fcog": "resembles, without being related to",
    "piecewise doublet": "partial doublet of",
    "pw dbt": "partial doublet of",
    "pwdbt": "partial doublet of",
    "rfv-etym": "etymology under discussion",
    "rfve": "etymology under discussion",
    "rfv-ety": "etymology under discussion",
    "lit": "literally",
    "literally": "literally",
}

# --- Plain mention templates: informative, never ancestors ----------------
_MENTION = {"m", "l", "mention", "link", "cog", "cognate", "ncog", "noncog",
            "noncognate", "cog-lite", "ncog-lite", "noncog-lite"}

# --- Doublet, under both its names ----------------------------------------
_DOUBLET = {"doublet", "dbt"}

# --- Structured format ----------------------------------------------------
# Wiktionary is replacing prose etymologies with templates that describe the
# tree as data:
#
#     {{ety|la|:af|pater<t:father>|-nus<id:adjective>}}
#
# Parameters starting with `:` name the relation; the others are terms shaped
# `[language:]lemma<key:value>…`.
#
# This is not the primary source, because the migration is half done: it
# appears in about one Italian entry in five, and where it coexists with prose
# it declares fewer steps, keeping the continuation inside recursive `<ety:…>`
# annotations we do not interpret. It is, however, the only source in roughly
# one Latin entry in five — `paternus`, `ecclesia`, `liber` — and without it
# those chains break.
_STRUCTURED = {"ety", "etymon"}

# Phrasings by which entries declare uncertainty in words rather than markup.
# Only sentence-initial forms count: further down, "of unknown origin" almost
# always qualifies the *ancestor* just cited, not the word of the entry, and
# reading it as the entry's own uncertainty invents a terminal.
_UNCERTAINTY_IN_PROSE = re.compile(
    r"^\W*(?:of\s+)?(?:unknown|uncertain|obscure|disputed|debated|unclear)\b"
    r"|^\W*(?:the\s+)?(?:origin|etymology|derivation)\s+(?:is\s+)?"
    r"(?:unknown|uncertain|obscure|disputed|debated|unclear)\b"
    r"|^\W*(?:of\s+)?(?:unknown|uncertain|obscure|disputed|debated)\s+"
    r"(?:and\s+\w+\s+)?(?:origin|etymology|derivation)\b",
    re.I,
)

_LIST_MARKERS = ("*", "#", ":", ";")


@dataclass
class Analysis:
    """What we managed to read from one "Etymology" section."""

    steps: list[Step] = field(default_factory=list)
    uncertain: bool = False
    # True when the uncertainty was inferred from prose rather than declared by
    # a template. It is weaker evidence: it must not silence other readings.
    uncertain_from_prose: bool = False
    root: Form | None = None
    hypotheses: list[Hypothesis] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Two readings of the same section, for two different jobs. `text` is what
    # gets shown — templates rendered as the forms they name, so the sentence
    # reads as the entry wrote it. `prose` is what decides whether anything was
    # left unread: it keeps only the words *outside* the templates, because a
    # section made entirely of markup we understood has no unread prose, and
    # judging that on the rendered version would count our own rendering as
    # something we failed to read.
    prose: str = ""
    # Positive declarations that close the chain by saying *how* the word was
    # formed, rather than by running out of data.
    imitative: bool = False
    eponym: str | None = None
    # The source states it has not written the etymology yet, or that the page
    # is an inflected form: both are facts about the source, not the language.
    no_etymology_yet: bool = False
    not_a_lemma: bool = False
    # Text of the section, kept so that what we could not interpret can still
    # be shown to the reader instead of being silently dropped.
    text: str = ""

    @property
    def empty(self) -> bool:
        return (not self.steps and not self.uncertain and self.root is None
                and not self.imitative and self.eponym is None)


# ---------------------------------------------------------------------------
# Navigating the section structure
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(={2,6})\s*(.+?)\s*\1[ \t]*$", re.M)


def _headings(text: str) -> list[tuple[int, int, int, str]]:
    """Every heading as (start, end, level, title)."""
    return [
        (m.start(), m.end(), len(m.group(1)), m.group(2).strip())
        for m in _HEADING.finditer(text)
    ]


def extract_sections(
    text: str,
    accept: Callable[[str], bool],
    level: int | None = None,
) -> list[tuple[str, str]]:
    """Sections whose title satisfies `accept`, with their content.

    A section ends where another of equal or higher rank begins, so
    "Etymology 1" contains its own subsections but does not spill into
    "Etymology 2".
    """
    found = _headings(text)
    results: list[tuple[str, str]] = []

    for index, (_start, title_end, lvl, title) in enumerate(found):
        if level is not None and lvl != level:
            continue
        if not accept(title):
            continue

        end = len(text)
        for next_start, _, next_level, _ in found[index + 1:]:
            if next_level <= lvl:
                end = next_start
                break
        results.append((title, text[title_end:end].strip()))

    return results


def language_section(wikitext: str, language_code: str) -> str | None:
    """The part of the page devoted to one language.

    Wiktionary pages are multilingual: "focus" hosts Latin, English and Dutch
    under the same entry. Picking the wrong section would mean telling the
    etymology of a different word.
    """
    expected = wiktionary_name(language_code)
    sections = extract_sections(wikitext, lambda t: t == expected, level=2)
    return sections[0][1] if sections else None


_SUBHEADING = re.compile(r"^={3,6}\s*\S", re.M)

# "Etymology", "Etymology 1", "Etymology 2"… but not "Etymology notes" or
# "Etymology of the suffix", which are commentary and would inflate the count
# of distinct etymologies the entry is said to record.
_ETYMOLOGY_TITLE = re.compile(r"^etymology(?:\s+\d+)?$", re.I)


def etymology_blocks(section: str) -> list[tuple[str, str]]:
    """The "Etymology" sections with everything that hangs below them.

    This is the whole block — etymology, part of speech, definitions — and it
    is what tells a reader *which* of several homographs they are looking at.
    """
    return extract_sections(section, lambda t: bool(_ETYMOLOGY_TITLE.match(t.strip())))


def etymology_sections(section: str) -> list[tuple[str, str]]:
    """The "Etymology" sections, in the order they appear.

    There is more than one when the same spelling covers words of different
    history: Italian "riso" (the grain and the laughter) is the textbook case.

    The body is cut at the first subheading. A section formally contains its
    own subsections — "Etymology 1" holds the "Noun" and "Descendants" that
    follow it — but those are the rest of the entry, not the etymology, and
    reading them turns a descendant into a supposed ancestor.
    """
    trimmed = []
    for title, body in etymology_blocks(section):
        cut = _SUBHEADING.search(body)
        trimmed.append((title, body[: cut.start()].strip() if cut else body))
    return trimmed


# Headings that name a part of speech, as opposed to Pronunciation, Descendants,
# Related terms and the other apparatus that surrounds a definition.
_PARTS_OF_SPEECH = frozenset(
    {
        "noun", "verb", "adjective", "adverb", "pronoun", "preposition",
        "conjunction", "interjection", "article", "numeral", "determiner",
        "particle", "prefix", "suffix", "infix", "interfix", "circumfix",
        "proper noun", "participle", "contraction", "abbreviation", "acronym",
        "initialism", "symbol", "letter", "phrase", "proverb", "idiom",
        "prepositional phrase", "adjectival phrase", "adverbial phrase",
        "postposition", "classifier", "counter", "root", "affix",
    }
)

_DEFINITION_LINE = re.compile(r"^#(?![#*:])\s*(.+)$", re.M)

# --- What a definition line declares about the page -----------------------
#
# Most Italian entries have no Etymology section at all: they state, in the
# definition line, that the page is a form of another word, or is formed from
# one. That is data, written in a template — reading it is not interpretation.
#
# Four things get declared, and they need four different answers. Every
# template is listed under all the names it can be invoked with, because the
# short alias is not a rare tail: `alt sp` appears on 321 Italian entries
# against 368 for `alternative spelling of`, `apoc of` on 307 against 524.
# Roughly half the usage goes through the abbreviation.

# 1. POINTERS — the page is the same word, in another form or spelling.
#    `far` is `fare` shortened; asking for its history means asking for
#    `fare`'s. Resolved before the walk begins, never drawn as a link.
_POINTER_OF: dict[str, str] = {
    # inflection
    "past participle of": "past participle of",
    "present participle of": "present participle of",
    "plural of": "plural of",
    "singular of": "singular of",
    "feminine of": "feminine of",
    "feminine singular of": "feminine singular of",
    "feminine plural of": "feminine plural of",
    "masculine plural of": "masculine plural of",
    "female equivalent of": "female equivalent of",
    "inflection of": "inflection of",
    "infl of": "inflection of",
    "verb form of": "verb form of",
    "adj form of": "adjective form of",
    "gerund of": "gerund of",
    "verbal noun of": "verbal noun of",
    "superlative of": "superlative of",
    "elative of": "elative of",
    # shortening that does not make a new lexeme: `far` is still `fare`
    "apocopic form of": "apocopic form of",
    "apoc of": "apocopic form of",
    "syncopic form of": "syncopic form of",
    "sync of": "syncopic form of",
    "apheretic form of": "apheretic form of",
    "contraction of": "contraction of",  # single-target uses; see _CONTRACTION
    "abbreviation of": "abbreviation of",
    "abbr of": "abbreviation of",
    "short for": "short for",
    "ellipsis of": "ellipsis of",
    "ellip of": "ellipsis of",
    # spelling and register variants
    "alternative form of": "alternative form of",
    "alt form": "alternative form of",
    "alternative spelling of": "alternative spelling of",
    "alt sp": "alternative spelling of",
    "alt sp of": "alternative spelling of",
    "alternative case form of": "alternative case form of",
    "medieval spelling of": "medieval spelling of",
    "obsolete spelling of": "obsolete spelling of",
    "obs sp": "obsolete spelling of",
    "obsolete form of": "obsolete form of",
    "obs form of": "obsolete form of",
    "archaic spelling of": "archaic spelling of",
    "archaic form of": "archaic form of",
    "pronunciation spelling of": "pronunciation spelling of",
    "misspelling of": "misspelling of",
    "informal form of": "informal form of",
    "euphemistic form of": "euphemistic form of",
    "form of": "form of",
    "nonlemma": "not a lemma",
}

# 2. DERIVATIONS — a *different* word, formed from another one. These become
#    real links of the chain. The statement comes from the definition line
#    rather than from an etymology, and the output says so.
_DERIVED_FROM: dict[str, Relation] = {
    "diminutive of": Relation.DIMINUTIVE,
    "dim of": Relation.DIMINUTIVE,
    "augmentative of": Relation.AUGMENTATIVE,
    "aug of": Relation.AUGMENTATIVE,
}

# 3. CONTRACTIONS — two sources at once. `dal` is not "a form of `da`": it is
#    `da` + `il`. Picking one of the two silently would be the very mistake
#    this work exists to remove.
_CONTRACTION_OF = {"contraction of", "contr of"}

# NEVER FOLLOWED. A synonym is a *different word*, so following it would
# answer with someone else's history. The template has the same shape as the
# ones above and is common enough to matter: `synonym of` on 2 365 Italian
# entries, `syn of` on a further 621. Both names, and the reason, are written
# here so that nobody widens the tables by pattern and lets them back in.
_NEVER_FOLLOWED = frozenset({"synonym of", "syn of", "syn"})


# All the wordings, for rendering a definition line as prose.
#
# `acronym of` and its kin are deliberately absent. An acronym unfolds into a
# phrase rather than descending from a word, so it says nothing about history
# and is out of scope: entries whose only declaration is an expansion now
# report no recorded etymology, which is what they have.
_DEFINITION_WORDINGS: dict[str, str] = {
    **_POINTER_OF,
    **{name: relation.label for name, relation in _DERIVED_FROM.items()},
    **dict.fromkeys(_CONTRACTION_OF, "contraction of"),
}

# What a Wiktionary language code looks like: `la`, `grc`, `ine-pro`, `la-vul`.
# Used to tell a code prefix from a colon that belongs to the word itself.
_LANGUAGE_CODE = re.compile(r"[a-z]{2,3}(?:-[a-z]{2,4})?")

_STRAY_BRACKETS = re.compile(r"\[\[|\]\]")
_SECTION_ANCHOR = re.compile(r"#.*$")

def _clean_target(raw: str) -> str:
    """Reduce a definition-line parameter to the word it names.

    These parameters are not clean lemmas. Observed in the wild: an unclosed
    wikilink (`[[regia`), two links in one value (`[[dopo]] [[Cristo]]`), a
    section anchor (`Ente#Italian`), a nested template (`{{lw|it|…}}`). Left
    alone, the first would be asked of Wiktionary verbatim and come back 404 —
    our own limit dressed up as silence from the source, in the very family
    where we are removing exactly that.

    Nested templates keep their last positional parameter rather than being
    deleted: `{{lw|it|Banca Centrale Europea}}` carries the expansion, and
    plain stripping would leave an empty string.

    Inline annotations go too. `{{alt form|la|caput<t:[[head]]><g:n>}}` names
    one word and two remarks about it; kept together they contain a colon and
    a space, so the target reads as a phrase and the declaration is dropped —
    `capus` is an alternative spelling of `caput` and would have been lost.
    The shape test is only as good as what it is shown.

    Interwiki prefixes are deliberately *not* stripped. `w:it:Roma` is a link
    to Wikipedia; the colon is what marks it as unusable, and removing it
    would turn the target into a lemma this tool would then request from
    Wiktionary.
    """
    code = mwparserfromhell.parse(raw)
    for tpl in list(code.filter_templates(recursive=False)):
        positional = [str(p.value) for p in tpl.params if not p.showkey]
        try:
            code.replace(tpl, positional[-1] if positional else "")
        except ValueError:
            continue

    text = code.strip_code(normalize=True, collapse=True)
    text = _STRAY_BRACKETS.sub("", text)
    text = _SECTION_ANCHOR.sub("", text)
    text, _ = _split_annotations(text)
    return " ".join(text.split())


def _target_shape(value: str) -> str:
    """Whether a target is a lemma we can look up, or something else.

    The decision rests on the shape of the target, not on the family of the
    template, and that is deliberate. Classifying by family gets the exceptions
    wrong in both directions — eight abbreviations point at phrases
    (`S.p.A.` → "società per azioni"), twelve initialisms point at single
    words. Judging the target itself gets those right, and protects every
    family added in future: whatever template someone adds tomorrow, a target
    that is not a lemma will never become a request to Wiktionary.
    """
    if not value:
        return "none"
    if "," in value:
        # Several spellings of one word — `onza,oncia`, both from Latin `uncia`.
        # A comma inside a single parameter is how Wiktionary writes "the same
        # slot, two spellings"; where the targets are genuinely different words
        # the source uses separate templates or separate sections, as `po'`
        # does. So this is a lemma with variants, not an ambiguity.
        return "lemma"
    if " " in value or ":" in value:
        return "phrase"
    return "lemma"


def _readable_definition(line: str) -> str:
    """A definition line as prose, rendering the "form of" templates."""
    text = _plain_text(line).strip(" ;:,")
    if text:
        return text
    for tpl in mwparserfromhell.parse(line).filter_templates():
        wording = _DEFINITION_WORDINGS.get(_normalize_name(tpl.name))
        if wording is None:
            continue
        target = _clean_target(_raw_param(tpl, "2") or _raw_param(tpl, "1"))
        return f"{wording} «{target}»" if target else wording
    return ""


def _raw_param(tpl: Template, key: str) -> str:
    """A parameter's value before any cleaning, or the empty string."""
    return str(tpl.get(key).value).strip() if tpl.has(key) else ""


def _first_definition(block: str) -> tuple[str, str]:
    """The part of speech and the first definition found in a block.

    Definitions are the lines starting with a single `#`. Nested ones (`##`) are
    sub-senses and the ones with `#:` or `#*` are examples and quotations:
    neither is what a reader needs to recognise the word.
    """
    for title, body in extract_sections(block, lambda t: True):
        if title.strip().lower() not in _PARTS_OF_SPEECH:
            continue
        for match in _DEFINITION_LINE.finditer(body):
            text = _readable_definition(match.group(1))
            if text:
                return title.strip().lower(), text
        return title.strip().lower(), ""
    return "", ""


def _statement_from_template(
    tpl: Template, entry_language: str
) -> DefinitionStatement | None:
    """Interpret one definition-line template, or return None to ignore it."""
    name = _normalize_name(tpl.name)

    if name in _NEVER_FOLLOWED or name in _NOT_A_LEMMA:
        return None

    language = _param(tpl, "1") or entry_language
    if not is_known_language(language):
        language = entry_language

    # Contractions carry two targets in two parameters, and both are links.
    if name in _CONTRACTION_OF:
        parts = [
            _clean_target(_raw_param(tpl, key)) for key in ("2", "3")
        ]
        usable = [p for p in parts if p and _target_shape(p) == "lemma"]
        if len(usable) > 1:
            return DefinitionStatement(
                kind=Declaration.CONTRACTION,
                wording="contraction of",
                forms=[Form(lemma=p, language=language) for p in usable],
                relation=Relation.COMPOUND,
            )

    target = _clean_target(_raw_param(tpl, "2"))
    if not target:
        # Older entries omit the language and put the target first.
        first = _clean_target(_raw_param(tpl, "1"))
        if first and not is_known_language(first):
            target, language = first, entry_language

    shape = _target_shape(target)
    wording = _DEFINITION_WORDINGS.get(name)
    if wording is None:
        return None

    # The shape of the target decides, not the family of the template. A
    # phrase, an interwiki link or two alternatives is not something to look
    # up, and yields no declaration at all — and conversely an abbreviation
    # that shortens to a single word (`TV` for `televisione`) is a perfectly
    # good pointer. Judging the family instead would get both kinds of
    # exception wrong.
    if shape != "lemma":
        return None

    # A comma-separated target is one word in several spellings; the walk tries
    # them in order and reads the first that has an entry.
    lemma, *variants = [part.strip() for part in target.split(",") if part.strip()]

    if name in _DERIVED_FROM:
        relation = _DERIVED_FROM[name]
        return DefinitionStatement(
            kind=Declaration.DERIVATION,
            wording=relation.label,
            forms=[Form(lemma=lemma, variants=tuple(variants), language=language)],
            relation=relation,
        )

    return DefinitionStatement(
        kind=Declaration.POINTER,
        wording=wording,
        forms=[Form(lemma=lemma, variants=tuple(variants), language=language)],
        # The gloss sits in the fourth positional slot — `{{apoc of|it|puoi||you
        # can}}` — or under `t=`. It is what lets a reader tell one target from
        # another when a spelling points at several.
        gloss=_clean_target(_raw_param(tpl, "4") or _raw_param(tpl, "t")),
    )


def definition_statements(
    section: str, entry_language: str
) -> list[DefinitionStatement]:
    """Every declaration the definition lines make, in the order they appear.

    They live among the definitions, under a part-of-speech heading, and never
    in an Etymology section: looking for it there would never find them.

    There can be several, and they need not agree: `po'` is the apocope of
    `poco` as a noun, of `puoi` as a verb, and an alternative form of `poi` as
    an adverb — three unrelated words. Which is why they are all returned.
    """
    found: list[DefinitionStatement] = []

    for title, body in extract_sections(section, lambda t: True):
        part_of_speech = title.strip().lower()
        if part_of_speech not in _PARTS_OF_SPEECH:
            continue
        for match in _DEFINITION_LINE.finditer(body):
            for tpl in mwparserfromhell.parse(match.group(1)).filter_templates():
                statement = _statement_from_template(tpl, entry_language)
                if statement is None:
                    continue
                statement.part_of_speech = part_of_speech
                found.append(statement)
                break  # one declaration per definition line

    return found


def definition_statement(
    section: str, entry_language: str
) -> DefinitionStatement | None:
    """The first declaration, for callers that need only one."""
    found = definition_statements(section, entry_language)
    return found[0] if found else None


def lemma_reference(section: str, entry_language: str) -> tuple[Form, str] | None:
    """The lemma this page is a form of, when it is only a form of one.

    A narrow view of `definition_statement` for callers that care about the
    pointer alone. A derivation, an expansion or a contraction is not a
    pointer, and this returns None for all three.
    """
    statement = definition_statement(section, entry_language)
    if statement is None or statement.kind is not Declaration.POINTER:
        return None
    return statement.forms[0], statement.wording


def senses(section: str) -> list[tuple[str, str, str]]:
    """One entry per etymology: (label, part of speech, first definition).

    Used to let a reader choose between homographs by meaning rather than by
    a bare ordinal: nobody knows in advance what "the third etymology" is.
    """
    return [
        (label, *_first_definition(block))
        for label, block in etymology_blocks(section)
    ]


# ---------------------------------------------------------------------------
# Parsing the etymological content
# ---------------------------------------------------------------------------

# The tag name must end here: `<ref>`, `<ref name=x>` or `<ref />`. Without
# this constraint the syntax of {{etymon}} — which writes `<ref:{{R:...}}>` in
# angle brackets — would be mistaken for a tag opening, and the removal would
# devour the text up to the next `</ref>`, derivation templates included. The
# etymology would come out empty with nothing signalling the loss.
_REFERENCES = re.compile(r"<ref(?:\s[^>]*)?/>|<ref(?:\s[^>]*)?>.*?</ref>", re.S | re.I)
_COMMENTS = re.compile(r"<!--.*?-->", re.S)
# Same reasoning: without the boundary, `<i…>` would swallow the `<id:adjective>`
# annotation of the structured format.
_LEFTOVER_TAGS = re.compile(
    r"</?(?:small|sup|sub|span|div|nowiki|i|b)(?:\s[^>]*)?/?>", re.I
)


def _strip_noise(text: str) -> str:
    """Remove bibliographic notes and comments, which are not part of the story."""
    text = _REFERENCES.sub("", text)
    text = _COMMENTS.sub("", text)
    return _LEFTOVER_TAGS.sub("", text)


def _split_body_and_discussion(text: str) -> tuple[str, list[str]]:
    """Separate the main claim from the lines of discussion.

    Well-formed entries state the etymology in prose and reserve bulleted lists
    for alternative proposals. Some contested entries — "focus" is the case
    that guided us — have no prose at all: they are a list of competing
    positions. There we take the first list item as the main position, which is
    Wiktionary's editorial convention.
    """
    body: list[str] = []
    listed: list[str] = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(_LIST_MARKERS):
            listed.append(stripped.lstrip("".join(_LIST_MARKERS)).strip())
        else:
            body.append(stripped)

    if body:
        return " ".join(body), listed
    if listed:
        return listed[0], listed[1:]
    return "", []


def _normalize_name(name) -> str:
    """Comparable template name: lowercase, without the "+" variant."""
    return str(name).strip().lower().rstrip("+")


def _param(tpl: Template, key: str) -> str:
    """Value of a parameter, cleaned of wikitext, or the empty string."""
    if not tpl.has(key):
        return ""

    raw = str(tpl.get(key).value).strip()
    cleaned = _plain_text(raw)

    # At the start of a line the asterisk is the wiki list marker, and cleaning
    # strips it. Here it marks a reconstructed, unattested form: that is
    # linguistic information, not typography, and belongs back on the lemma.
    if raw.startswith("*") and not cleaned.startswith("*"):
        cleaned = "*" + cleaned

    return cleaned


def _first_available(tpl: Template, *keys: str) -> str:
    for key in keys:
        value = _param(tpl, key)
        if value:
            return value
    return ""


def _form_from_relation(tpl: Template) -> Form | None:
    """Extract the ancestor form from a derivation template.

    The parameter convention is positional: 1 entry language, 2 source
    language, 3 lemma, 4 display form, 5 translation. The translation also
    appears as `t=` or `gloss=`.
    """
    language = _param(tpl, "2")
    if not language:
        return None

    lemma = _param(tpl, "3")
    # The hyphen is the convention for "no form cited".
    if lemma == "-":
        lemma = ""

    # Inline annotations belong to the display, not to the lemma. Left in
    # place, `*h₂el-<t:to grow>` becomes a page title that cannot exist, the
    # request comes back 404, and the chain closes on a *false* "no entry" —
    # our own markup mistaken for a fact about the language. The structured
    # format already strips these; the linear templates must do the same, or
    # the same string is read correctly down one path and corrupted down the
    # other.
    lemma, annotations = _split_annotations(lemma)
    if not lemma:
        lemma = annotations.get("alt", "")
    lemma, qualifier = _split_qualifier(lemma)

    # One parameter can hold several spellings of the same form — `[[-ere]],
    # [[-er]]` after the wikilinks are stripped. They are variants of one
    # ancestor, not several ancestors, so the first is followed and the others
    # are carried alongside instead of being joined into an impossible title.
    lemma, *variants = [part.strip() for part in lemma.split(",") if part.strip()] or [
        ""
    ]

    return Form(
        lemma=lemma,
        variants=tuple(variants),
        language=language,
        gloss=(
            _first_available(tpl, "t", "gloss", "5")
            or annotations.get("t")
            or annotations.get("gloss")
            or qualifier
            or None
        ),
        transliteration=(
            _first_available(tpl, "tr") or annotations.get("tr") or None
        ),
    )


# Language-specific templates carry no language parameter — `{{it-deverbal|x}}`,
# not `{{it-deverbal|it|x}}` — so their components start one position earlier.
_NO_LANGUAGE_PARAMETER = {
    "it-deverbal", "it-deverbal fpp", "it-verb-obj", "it-verb-verb",
    "ja-compound", "ja-com", "com-ja", "ja-blend", "sa-af", "sa-com",
}


def _forms_from_word_formation(tpl: Template, entry_language: str) -> list[Form]:
    """Extract the components of a compound or affixal derivation.

    Components sit in the positional parameters from the second onwards and
    belong by default to the language **the template declares**, which is not
    always the language of the entry: `dogaresa` is Venetan and analyses its
    Latin ancestor with `{{af|la|dux|-issa}}`, so `dux` is Latin. Taking the
    section's language instead labelled it Venetan — the very thing C2
    forbids, a form wearing its parent's language — and the walk then read
    Venetan as standing above Latin and called two entries contradictory.

    A component may still come from a third language, given by `langN=` or by
    a `code:` prefix on the value.
    """
    forms: list[Form] = []
    index = 1 if _normalize_name(tpl.name) in _NO_LANGUAGE_PARAMETER else 2
    first = index

    declared = _param(tpl, "1") if first == 2 else ""
    default_language = declared if is_known_language(declared) else entry_language

    while tpl.has(str(index)):
        value = _param(tpl, str(index))
        index += 1
        if not value or value == "-":
            continue

        language = _param(tpl, f"lang{index - first}") or default_language
        if ":" in value:
            candidate, rest = value.split(":", 1)
            if is_known_language(candidate):
                language, value = candidate, rest

        # Components may carry inline annotations — `pós<t:afterwards>` — which
        # belong to the display, not to the lemma. Left in place they become
        # part of the page title, which then cannot exist.
        value, annotations = _split_annotations(value)
        if not value:
            value = annotations.get("alt", "")
        if not value:
            continue

        position = index - first
        gloss = (_first_available(tpl, f"t{position}", f"gloss{position}")
                 or annotations.get("t") or annotations.get("gloss"))
        forms.append(Form(lemma=value, language=language, gloss=gloss or None))

    return forms


def _plain_text(source: str) -> str:
    """Reduce a fragment of wikitext to readable text.

    Mention templates are replaced by the lemma they cite rather than deleted:
    without this, a sentence such as "Some connect this along with faciēs,
    facētus, fax to…" would collapse into "Some connect this along with to",
    which is worse than useless.
    """
    code = mwparserfromhell.parse(source)

    for tpl in list(code.filter_templates(recursive=False)):
        name = _normalize_name(tpl.name)
        replacement = ""
        if name in _MENTION:
            replacement = _param(tpl, "3") or _param(tpl, "2")
        try:
            code.replace(tpl, replacement)
        except ValueError:
            continue  # node already removed because nested in another

    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,;.:!?])", r"\1", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip().strip(",; ")


# --- Adverbs that say how one link relates to the one before it -----------
#
# Three classes, doing three different things. Reading them is not inference:
# the words are in the text, and they state the structure the templates alone
# do not carry.
#
# `originally` is deliberately absent. In Wiktionary's prose it is nearly
# always semantic — "originally meaning to strike", "originally a military
# term" — and would flag a sentence that speaks of no stage at all.

# The form that follows is *not* the immediate parent: stages may be missing.
_DISTANT = re.compile(
    r"\b(?:ultimately|going\s+back\s+to|traceable\s+to|eventually)\b", re.I
)

# The form that follows is *closer* to the entry than the one before it:
# "From Arabic X via Spanish Y" reads entry ← Y ← X, so the textual order is
# reversed at this joint.
_THROUGH = re.compile(r"\b(?:via|through|by\s+way\s+of|mediated\s+by)\b", re.I)

# The source proposes rather than asserts. What follows is a conjecture, and a
# conjecture is not a link: `cavolo` reads "Possibly Neapolitan cavolo **or**
# Sicilian cavulu", and an entry that offers two candidates without choosing
# has not stated a chain. Concatenating one of them picks a side the source
# declined to pick, and silently drops the other.
_CONDITIONING = re.compile(
    r"\b(?:possibly|perhaps|probably|maybe|apparently|presumably|"
    r"alternatively|less\s+likely|more\s+likely|traditionally|"
    r"said\s+to\s+be|thought\s+to\s+be|may\s+be|might\s+be|could\s+be|"
    r"uncertain|unclear|disputed)\b",
    re.I,
)

# A conditioning marker governs forward through commas — "Possibly X or Y" is
# one marker over two candidates — and is released only by the end of the
# sentence.
_SENTENCE_END = re.compile(r"[.;:]")

# Two analyses offered side by side, with nothing choosing between them:
# "From {{af|it|di-|pelo|-are}} **or** from {{inh|it|la|dēpilō}}". The marker
# sits *between* the templates rather than before one, so the conditioning
# above never sees it — and the entry, having declined to choose, must not have
# the choice made for it. Both become conjectures, including the one already
# recorded.
_ALTERNATION = re.compile(r"\bor\b", re.I)

# Two relations joined by a literal `+` are one compound, not two links.
# `Lygodium` is «{{der|mul|grc|λύγος}} + {{der|mul|grc|εἶδος}}» — willow plus
# form — and read as a chain it becomes "from willow, from form", with the
# second element demoted to a reserve that the next entry discards. It is the
# same statement `{{af}}` makes, written with separate templates.
_COMPOSITION = re.compile(r"\+")

# What follows describes the word as it stands today, not where it came from.
# `{{surf}}` says this as a template and is already handled as a remark; the
# same statement written out in prose was being read as a diachronic step, so
# `strumentale` — «inherited from Latin īnstrūmentālis. By surface analysis,
# strumento + -ale» — declared an ancestry the entry does not claim.
#
# Reading a fixed phrase to *withhold* a claim is not the prose reading this
# version leaves out: that would mean extracting ancestors from free text,
# where a misreading invents a link. This can only ever remove one, so a
# misfire costs a note instead of a falsehood.
# `equivalent to` is the commonest of these by a wide margin: `minigolf` is
# «{{ubor|it|en|minigolf}}, equivalent to {{af|it|mini-|golf}}» — taken whole
# from English, and *mini- + golf* is how it parses today, not where it came
# from.
#
# Not `reanalysed as`, which looks like the others and means the opposite: a
# reanalysis is a real diachronic event — morphological boundaries redrawn, as
# in `a napron` → `an apron` — and silencing it would delete a step that
# happened.
_SYNCHRONIC = re.compile(
    r"\b(?:by\s+surface\s+(?:analysis|etymology)|surface\s+analysis|"
    r"synchronically|analy[sz]able\s+as|equivalent\s+to|morphologically)\b",
    re.I,
)


def _current_sentence(lead_in: str) -> str:
    """The part of the lead-in belonging to the template that follows it.

    A marker released by a full stop belongs to the sentence before, and
    letting it reach across would silence a step it never qualified.
    """
    return re.split(r"[.;:]", lead_in)[-1]


# The form that follows is one step beyond the *previous* one. Positive
# evidence that the textual order is the order of the chain, and so it raises
# confidence rather than lowering it.
_ONWARDS = re.compile(
    r"\b(?:itself\s+from|in\s+turn\s+from|this\s+from|which\s+is\s+from|"
    r"and\s+this\s+from)\b",
    re.I,
)


def _connective_before(text: str) -> str:
    """Which class of adverb, if any, introduces the next template.

    Only the tail is examined: an adverb three clauses back governs its own
    template, not this one.
    """
    tail = _plain_text(text)[-80:]
    if _THROUGH.search(tail):
        return "through"
    if _DISTANT.search(tail):
        return "distant"
    if _ONWARDS.search(tail):
        return "onwards"
    return ""


def _demote_last_step(analysis: Analysis, lead_in: str) -> None:
    """Move the step just recorded among the conjectures.

    Used when the text turns out to offer an alternative to it: what looked
    like an assertion was one of two candidates all along, and the entry did
    not choose.
    """
    if not analysis.steps:
        return
    step = analysis.steps.pop()
    analysis.hypotheses.extend(
        Hypothesis(form=form, attribution=_qualifying_phrase(lead_in))
        for form in step.forms
        if form.lemma
    )


def _qualifying_phrase(lead_in: str) -> str | None:
    """The wording that made a candidate a conjecture, when it is worth showing.

    In "Possibly X or Y" the second candidate is introduced by nothing but the
    conjunction, and quoting «or» as though it were the source's reasoning
    tells the reader less than saying nothing.
    """
    phrase = lead_in.strip(" ,;.")
    if len(phrase) < 5 or phrase.lower() in ("or", "and", "either", "but"):
        return None
    return phrase


def _place_step(analysis: Analysis, step: Step, connective: str) -> None:
    """Add a step, honouring an adverb that reverses the textual order.

    `via` marks the step that follows as the nearer one, so it belongs *before*
    the step already recorded. Everywhere else the textual order stands.
    """
    if connective == "through" and analysis.steps:
        analysis.steps.insert(len(analysis.steps) - 1, step)
        analysis.notes.append(
            f"the source gives «{step.forms[0].lemma}» as the intermediate stage"
        )
        return
    analysis.steps.append(step)


# Mentions that may supply a form a derivation deliberately left out. `cog` is
# absent on purpose: a cognate is a sideways relative, never an ancestor.
_PROMOTABLE_MENTION = {"m", "l", "mention", "link"}


def _forms_left_to_the_prose(
    sequence: list[tuple[str, Template]], start: int, language: str
) -> list[Form]:
    """The forms a dash-suppressed derivation names in the prose that follows.

    Wiktionary has a documented idiom for "derived from this language, the form
    given separately": a dash in the lemma slot suppresses the rendering so the
    sentence can name the word with `{{m}}`.

        From the {{der|it|gem-pro|-}} elements {{m|gem-pro|*gunþiz||battle}}
                                           and {{m|gem-pro|*harduz||hard, brave}}

    This is not prose to interpret: the mention repeats the *same language
    code* as the derivation, and that is the whole of the link. Collection
    stops at the first template that does not match — which is what keeps the
    cognates listed after `Aosta` out, and what makes an entry whose mention
    carries a different code (`brezza`, where a Vulgar Latin derivation is
    followed by `{{m|it|…}}`) yield nothing rather than something wrong.
    """
    forms: list[Form] = []

    for _, tpl in sequence[start + 1:]:
        if _normalize_name(tpl.name) not in _PROMOTABLE_MENTION:
            break
        if _param(tpl, "1") != language:
            break
        lemma = _param(tpl, "2")
        if not lemma or lemma == "-":
            break
        forms.append(
            Form(
                lemma=lemma,
                language=language,
                gloss=_first_available(tpl, "t", "gloss", "4") or None,
            )
        )

    return forms


def _readable_source_text(body: str) -> str:
    """The entry's own sentence, with its templates rendered, not deleted.

    This is what gets printed under `NOT_INTERPRETED`, beside a terminal that
    says "the entry states its etymology in prose we could not turn into a
    chain — here is what it says". Deleting the templates leaves only the
    joints: `From {{af|it|di-|pelo|-are}} or from {{inh|it|la|dēpilō}}` becomes
    "From or from", a sentence the source never wrote. Printing that under a
    claim of fidelity is a false statement in the one line whose whole purpose
    is to be faithful.

    Rendering each template as the form it names gives "From di- + pelo + -are
    or from dēpilō", which is both true and useful.
    """
    code = mwparserfromhell.parse(body)

    for tpl in list(code.filter_templates(recursive=False)):
        name = _normalize_name(tpl.name)

        if name in _MENTION:
            rendered = _param(tpl, "3") or _param(tpl, "2")
        elif name in _LINEAR_RELATIONS:
            form = _form_from_relation(tpl)
            rendered = form.lemma if form else ""
        elif name in _WORD_FORMATION_RELATIONS:
            rendered = " + ".join(
                f.lemma for f in _forms_from_word_formation(tpl, "") if f.lemma
            )
        elif name == "root":
            rendered = _split_qualifier(_param(tpl, "3"))[0]
        elif name in _UNCERTAINTY:
            rendered = "of uncertain origin"
        elif name in _ONOMATOPOEIA:
            rendered = "imitative"
        elif name in _DOUBLET or name in _EPONYM:
            rendered = _param(tpl, "2")
        else:
            rendered = ""

        try:
            code.replace(tpl, rendered)
        except ValueError:
            continue

    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([,;.:!?])", r"\1", text)
    text = re.sub(r"(?:,\s*){2,}", ", ", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip().strip(",; ")


def _parse_body(body: str, entry_language: str) -> Analysis:
    """Read the main chain from the etymological claim."""
    analysis = Analysis()
    code = mwparserfromhell.parse(body)

    # The templates in order, each with the text that introduces it. The text
    # carries the adverbs; the order lets a derivation look ahead for the form
    # it left to the prose.
    sequence: list[tuple[str, Template]] = []
    lead_in = ""
    for node in code.nodes:
        if isinstance(node, Template):
            sequence.append((lead_in, node))
            lead_in = ""
        else:
            lead_in += str(node)

    # True while a conditioning marker is in force. It survives commas, so that
    # "Possibly X or Y" covers both candidates, and is released by the end of
    # the sentence.
    conditioned = False

    for position, (lead_in, tpl) in enumerate(sequence):
        readable_lead_in = _plain_text(lead_in)
        if _SENTENCE_END.search(lead_in):
            conditioned = False
        if _CONDITIONING.search(readable_lead_in):
            conditioned = True
        elif (
            not conditioned
            and not _SENTENCE_END.search(lead_in)
            and _ALTERNATION.search(readable_lead_in)
            and analysis.steps
        ):
            # Only when the preceding template was asserted. Under a marker
            # already in force — "Possibly X **or** Y" — the candidates are
            # conjectures both, and the asserted chain before them, which the
            # full stop released, must be left alone.
            # An alternative to what precedes: the step already recorded was
            # never asserted on its own, so it joins the conjectures too.
            conditioned = True
            _demote_last_step(analysis, readable_lead_in)

        name = _normalize_name(tpl.name)
        connective = _connective_before(lead_in)

        if name in _LINEAR_RELATIONS:
            form = _form_from_relation(tpl)
            if form:
                # A derivation with no form of its own may have left it to the
                # prose. Where it did, those mentions are the link.
                forms = [form]
                if not form.lemma:
                    named = _forms_left_to_the_prose(sequence, position, form.language)
                    if named:
                        forms = named

                # A `+` between two relations of the same kind and the same
                # language joins them into one compound. Narrow on purpose:
                # `{{inh|it|la|x}} + {{bor|it|de|y}}` are two different claims,
                # and a `+` after a full stop belongs to another sentence.
                relation = _LINEAR_RELATIONS[name]
                previous = analysis.steps[-1] if analysis.steps else None
                if (
                    not conditioned
                    and previous is not None
                    and previous.relation is relation
                    and previous.forms
                    and previous.forms[0].language == form.language
                    and _COMPOSITION.search(lead_in)
                    and not _SENTENCE_END.search(lead_in)
                ):
                    previous.forms.extend(f for f in forms if f.lemma)
                    continue

                if conditioned:
                    # Proposed, not asserted: it goes where conjectures go.
                    analysis.hypotheses.extend(
                        Hypothesis(
                            form=candidate,
                            attribution=_qualifying_phrase(readable_lead_in),
                        )
                        for candidate in forms
                        if candidate.lemma
                    )
                    continue

                _place_step(
                    analysis,
                    Step(
                        relation=relation,
                        forms=forms,
                        skips_stages=connective == "distant",
                    ),
                    connective,
                )

        elif name in _WORD_FORMATION_RELATIONS:
            forms = _forms_from_word_formation(tpl, entry_language)
            if forms and _SYNCHRONIC.search(_current_sentence(readable_lead_in)):
                # Not a link: it says what the word is made of now, which may
                # be nothing like where it came from. `strumentale` was
                # inherited whole from Latin and *also* looks like strumento +
                # -ale; only the first is history.
                analysis.notes.append(
                    "synchronically analysable as "
                    + ", ".join(f"«{f.lemma}»" for f in forms if f.lemma)
                )
            elif forms and conditioned:
                # An analysis into parts can be conjectural like any other:
                # "apparently from rodo + monte" proposes, it does not assert.
                analysis.hypotheses.extend(
                    Hypothesis(
                        form=candidate,
                        attribution=_qualifying_phrase(readable_lead_in),
                    )
                    for candidate in forms
                    if candidate.lemma
                )
            elif forms:
                _place_step(
                    analysis,
                    Step(relation=_WORD_FORMATION_RELATIONS[name], forms=forms),
                    connective,
                )

        elif name == "root":
            # The ultimate root is categorisation data, not a link: treating it
            # as a step would skip every intermediate stage.
            language = _param(tpl, "2")
            lemma, qualifier = _split_qualifier(_param(tpl, "3"))
            if language and lemma:
                analysis.root = Form(
                    lemma=lemma, language=language, gloss=qualifier or None
                )

        elif name in _UNCERTAINTY:
            analysis.uncertain = True

        elif name in _ONOMATOPOEIA:
            analysis.imitative = True

        elif name in _EPONYM:
            analysis.eponym = _first_available(tpl, "2", "3")
            if analysis.eponym:
                analysis.notes.append(f"named after {analysis.eponym}")
            else:
                analysis.eponym = "an unnamed person or place"

        elif name in _NO_ETYMOLOGY_YET:
            analysis.no_etymology_yet = True

        elif name in _NOT_A_LEMMA:
            analysis.not_a_lemma = True

        elif name in _DOUBLET:
            twin = _param(tpl, "2")
            if twin:
                analysis.notes.append(f"doublet of «{twin}»")

        elif name in _REMARKS:
            target = _first_available(tpl, "3", "2")
            analysis.notes.append(
                f"{_REMARKS[name]} «{target}»" if target else _REMARKS[name]
            )

    if not analysis.uncertain and _UNCERTAINTY_IN_PROSE.search(_plain_text(body)):
        analysis.uncertain = True
        analysis.uncertain_from_prose = True

    return analysis


_TRAILING_QUALIFIER = re.compile(r"^(?P<form>.*\S)\s*\((?P<gloss>[^()]+)\)\s*$")


def _split_qualifier(lemma: str) -> tuple[str, str]:
    """Separate a form from the parenthesised gloss that disambiguates it.

    `{{root|it|ine-pro|*ḱel- (cover)}}` names the root `*ḱel-`; the bracket
    tells it apart from a homonymous root and is editorial, not part of the
    form. Left in, it goes into the page title —
    `Reconstruction:Proto-Indo-European/ḱel- (cover)` — which does not exist,
    and the 404 would read as the language having no entry.

    The same failure as the inline annotations, in the notation that predates
    them. It does no harm today only because roots are never fetched.
    """
    match = _TRAILING_QUALIFIER.match(lemma)
    if match is None:
        return lemma, ""
    return match.group("form"), match.group("gloss").strip()


def _split_annotations(chunk: str) -> tuple[str, dict[str, str]]:
    """Separate a structured term from its `<key:value>` annotations.

    Annotations may contain further ones — `<ety:from<*x<ety:inh<...>>>>` — so
    the scan tracks angle-bracket depth instead of relying on a regular
    expression, which would cut a recursive structure in the wrong place.
    """
    base: list[str] = []
    annotations: dict[str, str] = {}
    current: list[str] = []
    depth = 0

    for character in chunk:
        if character == "<":
            depth += 1
            if depth == 1:
                continue
        elif character == ">":
            depth -= 1
            if depth == 0:
                text = "".join(current)
                current = []
                key, _, value = text.partition(":")
                annotations.setdefault(key.strip(), value.strip())
                continue

        if depth:
            current.append(character)
        else:
            base.append(character)

    return "".join(base).strip(), annotations


def _structured_form(chunk: str, default_language: str) -> Form | None:
    """Interpret a term shaped `[language:]lemma<key:value>…`."""
    base, annotations = _split_annotations(chunk)

    language = default_language
    lemma = base
    if ":" in base:
        candidate, _, rest = base.partition(":")
        # Split on any code-shaped prefix, known or not. Keeping `pgd:𐨭𐨐𐨪`
        # whole leaves the form labelled with the *parent's* language, which is
        # an assertion — and a false one. A code we do not recognise is shown
        # raw, which says exactly as much as we know.
        if _LANGUAGE_CODE.fullmatch(candidate):
            language, lemma = candidate, rest.strip()

    # Some entries leave the lemma empty and put the form in `<alt:…>`.
    if not lemma:
        lemma = annotations.get("alt", "")
    if not lemma:
        return None

    return Form(
        lemma=lemma,
        language=language,
        gloss=annotations.get("t") or annotations.get("gloss") or None,
        transliteration=annotations.get("tr") or None,
    )


def _parse_structured(body: str, entry_language: str) -> list[Step]:
    """Read the steps declared by {{ety}} and {{etymon}}.

    Only the first level is read: the `<ety:…>` nestings describe the
    continuation of the chain, which we rebuild anyway by walking up to the
    ancestor's own entry, where the data is first-hand.
    """
    steps: list[Step] = []

    for tpl in mwparserfromhell.parse(body).filter_templates(recursive=False):
        if _normalize_name(tpl.name) not in _STRUCTURED:
            continue

        base_language = _param(tpl, "1") or entry_language
        relation: Relation | None = None
        forms: list[Form] = []
        index = 2

        while tpl.has(str(index)):
            raw = str(tpl.get(str(index)).value).strip()
            index += 1
            if not raw:
                continue

            if raw.startswith(":"):
                # A new relation opens a new group: whatever was collecting
                # under the previous one is complete and can be emitted.
                if relation is not None and forms:
                    steps.append(Step(relation=relation, forms=forms))
                forms = []
                name = raw[1:].strip().lower().rstrip("+")
                relation = _LINEAR_RELATIONS.get(name) or _WORD_FORMATION_RELATIONS.get(
                    name
                )
                continue

            if relation is None:
                continue
            form = _structured_form(raw, base_language)
            if form:
                forms.append(form)

        if relation is not None and forms:
            steps.append(Step(relation=relation, forms=forms))

    return steps


# Openings that mark a line as something other than a proposed ancestor:
# descendants go the other way in time, comparisons go sideways. Both would
# otherwise be collected as conjectural ancestors and printed as "perhaps X".
_NOT_AN_ANCESTOR = re.compile(
    r"^\W*(?:descendants?\b|compare\b|cf\.?|see\s|akin\s+to\b|related\s+to\b|"
    r"cognates?\b|whence\b|hence\b|compare\s+also\b|doublet\s+of\b|"
    r"synonyms?\b|derived\s+terms?\b)",
    re.I,
)


def _parse_hypotheses(lines: list[str]) -> list[Hypothesis]:
    """Collect derivations proposed but not accepted as certain."""
    hypotheses: list[Hypothesis] = []

    for line in lines:
        if _NOT_AN_ANCESTOR.match(_plain_text(line)):
            continue
        code = mwparserfromhell.parse(line)
        preceding: list = []
        form: Form | None = None

        for node in code.nodes:
            if (
                isinstance(node, Template)
                and _normalize_name(node.name) in _LINEAR_RELATIONS
            ):
                form = _form_from_relation(node)
                break
            preceding.append(node)

        if form is None or not form.lemma:
            continue

        attribution = _plain_text("".join(str(n) for n in preceding))
        if len(attribution) > 160:
            attribution = attribution[:157].rstrip() + "…"

        hypotheses.append(Hypothesis(form=form, attribution=attribution or None))

    return hypotheses


def parse(etymology_text: str, entry_language: str) -> Analysis:
    """Parse a complete "Etymology" section."""
    body, discussion = _split_body_and_discussion(_strip_noise(etymology_text))
    analysis = _parse_body(body, entry_language)

    # The structured format steps in only where prose is silent. Where both are
    # present prose declares more steps, and an already declared uncertainty is
    # a terminal: looking elsewhere for an ancestor would override it.
    #
    # "Declared" is the load-bearing word. Uncertainty counts as the entry's own
    # only when it opens the section: further down, "of unknown origin" almost
    # always qualifies the ancestor just cited. That test lives in
    # `_UNCERTAINTY_IN_PROSE`, which is anchored at the start for this reason.
    if not analysis.steps and not analysis.uncertain:
        analysis.steps = _parse_structured(body, entry_language)

    # Appended, never assigned: the body has already collected the candidates a
    # conditioning marker refused to concatenate, and overwriting them here
    # would throw away exactly what the entry took care to offer.
    analysis.hypotheses += _parse_hypotheses(discussion)

    # "Of uncertain origin. Probably from X, less likely from Y" is a doubt with
    # suggestions, not a chain. The suggestions must not become links — but
    # dropping them would lose what the entry actually offers, so they are kept
    # where conjectures belong: below the terminal, marked as such.
    if analysis.uncertain and analysis.steps:
        analysis.hypotheses = [
            Hypothesis(form=form)
            for step in analysis.steps
            for form in step.forms
            if form.lemma
        ] + analysis.hypotheses
        analysis.steps = []

    analysis.text = _readable_source_text(body) or _readable_source_text(
        " ".join(discussion)
    )
    analysis.prose = _plain_text(body) or _plain_text(" ".join(discussion))
    return analysis
