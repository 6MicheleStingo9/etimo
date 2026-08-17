"""Wiktionary language codes and their names.

Wiktionary uses its own codes (`la`, `grc`, `ine-pro`, `la-vul`), which do not
always match ISO 639. The canonical English name serves three purposes at once:
it is shown to the user, it is the section heading (`==Ancient Greek==`), and
it is a path segment in the URL of reconstructed forms
(`Reconstruction:Proto-Indo-European/...`). One name, one table, no risk of the
three drifting apart.

Coverage is limited to languages that actually turn up in the etymologies we
walk. For unknown codes we return the raw code: saying "ine-pro" is less
harmful than inventing a plausible but false name.
"""

from __future__ import annotations

import unicodedata

# Abjad scripts: vowel marks are written in citations but not in page titles.
_UNVOCALIZED_SCRIPTS = frozenset(
    {
        "ar", "ota", "fa", "fa-cls", "ur", "ps", "sd", "kmr",
        "he", "hbo", "arc", "syc", "phn",
    }
)

# Languages whose entries are cited with vowel-length marks but titled without
# them: `labōs` belongs to the page `labos`, `ὄρῡζα` to `ὄρυζα`. This holds for
# attested Latin in all its phases and for Ancient Greek, but not for
# reconstructed forms, where the macron is part of the title
# (`Reconstruction:Proto-Italic/patēr`).
_TITLES_WITHOUT_VOWEL_LENGTH = frozenset(
    {"la", "la-lat", "la-med", "la-vul", "la-ecc", "la-new", "itc-ola", "grc"}
)

# Macron and breve. Only these are stripped: in Ancient Greek the accents and
# breathings are part of the title, and removing diacritics indiscriminately
# would reduce `ὄρυζα` to `ορυζα`, which is no entry at all.
_VOWEL_LENGTH_MARKS = frozenset({"̄", "̆"})

_LANGUAGES: dict[str, str] = {
    # --- Italian and its direct ancestors ---
    "it": "Italian",
    "roa-oit": "Old Italian",
    "la": "Latin",
    "la-lat": "Late Latin",
    "la-med": "Medieval Latin",
    "la-vul": "Vulgar Latin",
    "la-ecc": "Ecclesiastical Latin",
    "la-eme": "Early Medieval Latin",
    "la-cla": "Classical Latin",
    "la-new": "New Latin",
    "itc-ola": "Old Latin",
    "itc-pro": "Proto-Italic",
    "ine-pro": "Proto-Indo-European",
    # --- Languages and dialects of Italy ---
    "vec": "Venetan",
    "nap": "Neapolitan",
    "scn": "Sicilian",
    "lmo": "Lombard",
    "pms": "Piedmontese",
    "lij": "Ligurian",
    "egl": "Emilian",
    "rgn": "Romagnol",
    "sc": "Sardinian",
    "fur": "Friulian",
    "co": "Corsican",
    "roa-tar": "Tarantino",
    # --- Classical and Mediterranean ---
    "grc": "Ancient Greek",
    "grk-pro": "Proto-Hellenic",
    "el": "Greek",
    "gkm": "Byzantine Greek",
    "he": "Hebrew",
    "hbo": "Biblical Hebrew",
    "arc": "Aramaic",
    "syc": "Classical Syriac",
    "ar": "Arabic",
    "xcl": "Old Armenian",
    "hy": "Armenian",
    "cop": "Coptic",
    "egy": "Egyptian",
    "akk": "Akkadian",
    "sux": "Sumerian",
    "phn": "Phoenician",
    "xpu": "Punic",
    "ett": "Etruscan",
    "xrr": "Raetic",
    "xlg": "Ligurian (ancient)",
    "osc": "Oscan",
    "xum": "Umbrian",
    "sem-pro": "Proto-Semitic",
    "afa-pro": "Proto-Afro-Asiatic",
    # --- Germanic ---
    "gem-pro": "Proto-Germanic",
    "gmw-pro": "Proto-West Germanic",
    "got": "Gothic",
    "lng": "Lombardic",
    "frk": "Frankish",
    "goh": "Old High German",
    "gmh": "Middle High German",
    "de": "German",
    "nl": "Dutch",
    "dum": "Middle Dutch",
    "odt": "Old Dutch",
    "gml": "Middle Low German",
    "osx": "Old Saxon",
    "ang": "Old English",
    "enm": "Middle English",
    "en": "English",
    "non": "Old Norse",
    "is": "Icelandic",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    # --- Romance and Celtic ---
    "fr": "French",
    "fro": "Old French",
    "frm": "Middle French",
    "nrf": "Norman",
    "pro": "Old Occitan",
    "oc": "Occitan",
    "ca": "Catalan",
    "es": "Spanish",
    "osp": "Old Spanish",
    "pt": "Portuguese",
    "roa-opt": "Old Portuguese",
    "ro": "Romanian",
    "cel-pro": "Proto-Celtic",
    "ga": "Irish",
    "sga": "Old Irish",
    "cy": "Welsh",
    "gaul": "Gaulish",
    "cel-gau": "Gaulish",
    "xtg": "Transalpine Gaulish",
    "xcg": "Cisalpine Gaulish",
    "xlp": "Lepontic",
    "br": "Breton",
    # --- Slavic, Baltic, Uralic ---
    "sla-pro": "Proto-Slavic",
    "cu": "Old Church Slavonic",
    "ru": "Russian",
    "pl": "Polish",
    "cs": "Czech",
    "sh": "Serbo-Croatian",
    "bg": "Bulgarian",
    "sl": "Slovene",
    "bsl-pro": "Proto-Balto-Slavic",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "hu": "Hungarian",
    "fi": "Finnish",
    "et": "Estonian",
    "urj-pro": "Proto-Uralic",
    # --- Indo-Iranian and Eastern ---
    "sa": "Sanskrit",
    "inc-pro": "Proto-Indo-Aryan",
    "iir-pro": "Proto-Indo-Iranian",
    "ira-pro": "Proto-Iranian",
    "pal": "Middle Persian",
    "peo": "Old Persian",
    "fa": "Persian",
    "fa-cls": "Classical Persian",
    "hi": "Hindi",
    "ur": "Urdu",
    "bn": "Bengali",
    "ta": "Tamil",
    "sd": "Sindhi",
    "ae": "Avestan",
    # --- Turkic and other sources of loanwords ---
    "ota": "Ottoman Turkish",
    "gsw": "Swiss German",
    "bar": "Bavarian",
    "nci": "Classical Nahuatl",
    "xaa": "Andalusian Arabic",
    "sqr": "Siculo-Arabic",
    "grc-koi": "Koine Greek",
    "roa-oca": "Old Catalan",
    "oc-pro": "Proto-Occitan",
    "roa-git": "Judeo-Italian",
    "xno": "Anglo-Norman",
    "tr": "Turkish",
    "trk-pro": "Proto-Turkic",
    "mn": "Mongolian",
    "zh": "Chinese",
    "ltc": "Middle Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "sw": "Swahili",
    "eu": "Basque",
    "mt": "Maltese",
    "sq": "Albanian",
    "kmr": "Northern Kurdish",
    # --- Dravidian and Austroasiatic ---
    "dra": "Dravidian",
    "dra-pro": "Proto-Dravidian",
    "aav": "Austroasiatic",
    "aav-pro": "Proto-Austroasiatic",
    "map-pro": "Proto-Austronesian",
    "tai-pro": "Proto-Tai",
    # --- Amerindian ---
    "nah": "Nahuatl",
    "qu": "Quechua",
    "tpw": "Old Tupi",
    "car": "Galibi Carib",
    # --- Language families ---
    # These appear when the source gives the origin by group rather than by
    # language: "a borrowing from an Eastern Iranian language".
    "ine": "Indo-European",
    "ira": "Iranian",
    "iir": "Indo-Iranian",
    "gem": "Germanic",
    "sla": "Slavic",
    "cel": "Celtic",
    "sem": "Semitic",
    "roa": "Romance",
    "itc": "Italic",
    "trk": "Turkic",
    "qfa-sub": "Substrate",
    # --- Conventional ---
    "mul": "Translingual",
    "und": "Undetermined",
}

# Suffix Wiktionary uses to mark reconstructed, unattested languages.
_PROTO_SUFFIX = "-pro"

# Historical phases Wiktionary often does not give a section of their own:
# Late, Vulgar, Medieval and Old Latin forms usually sit inside `==Latin==`.
# Falling back to that section recovers chains that would otherwise break for
# an editorial reason rather than a linguistic one.
_SECTION_FALLBACK: dict[str, str] = {
    "la-lat": "la",
    "la-med": "la",
    "la-vul": "la",
    "la-ecc": "la",
    "la-eme": "la",
    "la-cla": "la",
    "la-new": "la",
    "itc-ola": "la",
    "grc-koi": "grc",
    "gkm": "el",
}


def primary_code(code: str) -> str:
    """The first code, when the source names several at once.

    Entries sometimes hedge between two stages — `{{der|it|roa-oca,oc-pro|…}}` —
    and the whole string would match no section and no page title. The first is
    the one the entry puts forward.
    """
    return code.split(",")[0].strip() if "," in code else code.strip()


# Roughly when each language was in use, as (first attested, last attested).
# Centuries are approximate on purpose and deliberately generous at both ends:
# the check below must fire only where the contradiction is beyond argument, so
# every uncertainty is resolved in favour of silence. 2100 stands for "still
# spoken".
#
# This replaced a scheme of ranks within families, which had a flaw worth
# recording. Grouping Italian, French and Spanish under one "Italic" family
# made them comparable, but they are not stages of one another — they are
# sisters, alive at the same time. Comparing their ranks declared the massive
# and well documented sixteenth-century borrowing of Italian words into French
# (`banque`, `soldat`, `bilan`) an impossibility. Dates carry no such
# assumption: two languages that overlap in time simply never trigger the test,
# whatever their kinship.
_ATTESTED: dict[str, tuple[int, int]] = {
    # Italic and Romance
    "itc-pro": (-2000, -700), "itc-ola": (-700, -100),
    "la": (-600, 900), "la-lat": (200, 700), "la-vul": (100, 900),
    "la-ecc": (200, 2100), "la-med": (600, 1500), "la-eme": (500, 1000),
    "la-new": (1500, 2100),
    "roa-oit": (900, 1500), "it": (1200, 2100),
    "fro": (800, 1400), "frm": (1300, 1650), "fr": (1500, 2100),
    "pro": (800, 1500), "oc": (1500, 2100),
    "osp": (900, 1500), "es": (1200, 2100),
    "roa-opt": (900, 1500), "pt": (1200, 2100),
    "ca": (1000, 2100), "ro": (1500, 2100),
    "vec": (1200, 2100), "nap": (1200, 2100), "scn": (1200, 2100),
    "osc": (-500, 100), "xum": (-500, 100), "ett": (-700, 100),
    # Germanic
    "gem-pro": (-500, 200), "gmw-pro": (0, 400), "got": (300, 700),
    "lng": (500, 1000), "frk": (400, 900),
    "goh": (700, 1050), "gmh": (1050, 1350), "de": (1350, 2100),
    "osx": (800, 1200), "gml": (1200, 1600),
    "odt": (500, 1150), "dum": (1150, 1500), "nl": (1500, 2100),
    "ang": (450, 1150), "enm": (1150, 1500), "en": (1500, 2100),
    "non": (700, 1350), "is": (1350, 2100), "sv": (1350, 2100),
    "da": (1350, 2100), "no": (1350, 2100),
    # Hellenic
    "grk-pro": (-2500, -1600), "grc": (-800, 400),
    "gkm": (400, 1450), "el": (1450, 2100),
    # Slavic and Baltic
    "sla-pro": (-500, 500), "cu": (850, 1700),
    "ru": (1000, 2100), "pl": (1000, 2100), "cs": (1000, 2100),
    "sh": (1000, 2100), "bg": (1000, 2100), "sl": (1000, 2100),
    "lt": (1500, 2100), "lv": (1500, 2100),
    # Indo-Iranian
    "iir-pro": (-2500, -2000), "inc-pro": (-2000, -1500),
    "ira-pro": (-2000, -1500),
    "sa": (-1500, 600), "ae": (-1200, -400), "peo": (-600, -300),
    "pal": (200, 900), "fa-cls": (900, 1600), "fa": (1600, 2100),
    "hi": (1300, 2100), "ur": (1300, 2100), "bn": (1300, 2100),
    # Semitic and neighbours
    "sem-pro": (-4000, -3000), "akk": (-2500, -100),
    "hbo": (-1200, -200), "arc": (-900, 700), "syc": (100, 1300),
    "he": (-1200, 2100), "ar": (400, 2100), "mt": (1500, 2100),
    "phn": (-1200, -300), "egy": (-3000, 400), "cop": (200, 1500),
    "sux": (-3000, -1800),
    # Celtic
    "cel-pro": (-1300, -800), "gaul": (-500, 500), "sga": (600, 900),
    "ga": (1200, 2100), "cy": (1000, 2100), "br": (1200, 2100),
    # Turkic, Armenian, other
    "ota": (1300, 1930), "tr": (1930, 2100), "trk-pro": (-500, 500),
    "xcl": (400, 1100), "hy": (1100, 2100),
    "ine-pro": (-4500, -2500),
}


def impossible_order(ancestor: str, descendant: str) -> bool:
    """True when a claimed ancestor is demonstrably later than its descendant.

    Not "unlikely": impossible. Modern German cannot have given a word to
    Lombardic, which died out four centuries before German existed, and no
    amount of editorial disagreement makes it so.

    The test is deliberately blunt — the claimed ancestor must begin *after*
    the descendant had already ceased — so it stays silent wherever the two
    overlap even slightly. Languages we have no dates for are never checked.
    """
    older = _ATTESTED.get(ancestor)
    younger = _ATTESTED.get(descendant)
    if older is None or younger is None:
        return False
    return older[0] > younger[1]


def language_name(code: str) -> str:
    """Display name of the language, or the code itself when unknown."""
    if not code:
        return "unspecified language"
    code = primary_code(code)
    if code in _LANGUAGES:
        return _LANGUAGES[code]
    # Many variants are shaped "base-variant": fall back to the base language,
    # keeping the code visible so an approximation is not passed off as exact.
    base = code.split("-")[0]
    if base in _LANGUAGES:
        return f"{_LANGUAGES[base]} ({code})"
    return code


def wiktionary_name(code: str) -> str:
    """Canonical name used as a section heading and as a URL segment.

    Unlike `language_name` this never decorates the result: the value goes into
    a lookup, where an added code would simply not match.

    It also never *guesses*. Falling back on the base of an unknown code would
    turn `cel-gau` into "Celtic" and send us looking for a section that does not
    exist while the real one is called "Gaulish" — worse than failing outright,
    because the failure would then be blamed on the language.
    """
    code = primary_code(code)
    if code in _LANGUAGES:
        return _LANGUAGES[code]
    return code


def is_known_language(code: str) -> bool:
    """True when we know where to look for this language's section."""
    return primary_code(code) in _LANGUAGES


def is_reconstructed(code: str) -> bool:
    """True when the language is reconstructed, hence not directly attested."""
    return primary_code(code).endswith(_PROTO_SUFFIX)


def can_locate_reconstruction(code: str) -> bool:
    """True when we can build the `Reconstruction:` title for this language.

    The namespace path uses the canonical name, so an unregistered proto-code
    would yield `Reconstruction:bnt-pro/…` — a title that cannot exist. Asking
    for it and reading the 404 as "here reconstruction stops" would state as a
    fact about the language what is a gap in our table.
    """
    return is_known_language(code)


def fallback_language(code: str) -> str | None:
    """Language to look under when the entry has no section of its own."""
    return _SECTION_FALLBACK.get(primary_code(code))


def normalize_lemma(lemma: str, code: str) -> str:
    """Bring a lemma to the form Wiktionary uses as a page title.

    Citations carry marks that titles do not: vocalisation in abjad scripts
    (`قَهْوَة` belongs to `قهوة`) and vowel-length marks in Latin and Greek
    (`labōs` to `labos`, `ὄρῡζα` to `ὄρυζα`). Looking up the cited form would
    yield a false "entry missing", declaring a chain exhausted while it in fact
    continues.

    The two cases are handled differently, and both need care. In Latin and
    Greek the characters are precomposed and must be decomposed, but only the
    length mark is dropped: deleting every diacritic would reduce `ὄρυζα` to
    `ορυζα`. In Arabic, decomposition would itself be destructive, splitting
    `أ` into `ا` plus hamza and so changing the word rather than cleaning it.
    """
    cleaned = lemma.strip()
    code = primary_code(code)

    if code in _UNVOCALIZED_SCRIPTS:
        return "".join(c for c in cleaned if not unicodedata.combining(c))

    if code in _TITLES_WITHOUT_VOWEL_LENGTH:
        decomposed = unicodedata.normalize("NFD", cleaned)
        stripped = "".join(c for c in decomposed if c not in _VOWEL_LENGTH_MARKS)
        return unicodedata.normalize("NFC", stripped)

    return cleaned


def page_title(lemma: str, code: str) -> str:
    """Title of the Wiktionary page hosting this form.

    Reconstructed forms do not live in the main namespace but under
    `Reconstruction:<Canonical name>/<lemma without asterisk>`.
    """
    code = primary_code(code)
    cleaned = normalize_lemma(lemma.lstrip("*"), code)
    if is_reconstructed(code) or lemma.startswith("*"):
        return f"Reconstruction:{wiktionary_name(code)}/{cleaned}"
    return cleaned
