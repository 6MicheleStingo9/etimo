# etimo

A command-line tool that traces the recorded history of an Italian word through
Wiktionary, ancestor by ancestor, until the chain reaches a terminal.

```text
$ etimo fuoco
fuoco (it)
└─ inherited from Latin
   └─ focus (la) «hearth»
      └─ ⊗ uncertain origin
         perhaps *bʰeh₂- (ine-pro) «to shine» — «Some connect this along with faciēs, facētus, fax to»
         perhaps *dʰegʷʰ- (ine-pro) «to burn» — «Matasović, and Hamp before him, opt to derive from»

1 step · terminal: uncertain origin
```

The output is a tree. Each node is a form; each node is the ancestor of the node
above it; each branch ends in a terminal stating why the walk stopped. Above,
the terminal is `uncertain origin`: Wiktionary declares the origin of Latin
*focus* unknown. The two indented lines are proposals recorded in the entry.
They are printed below the terminal, dimmed and attributed, and are not part of
the chain.

The distinction between a terminal that is a finding about the language and one
that is a limit of the source or of the program is the tool's governing
constraint. It is specified under [Terminals](#terminals).

Examples in this document are verbatim output, with two omissions: the summary
line ends with a request count and a timing, which vary between runs and are cut
here, and blocks holding several invocations drop the summary line altogether.
Where an option such as `--depth` appears, it is there to keep the example
short, and the tree continues beyond what is shown.

---

## Contents

- [Synopsis](#synopsis)
- [Installation](#installation)
- [Description](#description)
- [Relations](#relations)
- [Terminals](#terminals)
- [Declarations in definition lines](#declarations-in-definition-lines)
- [Ambiguity and pointers](#ambiguity-and-pointers)
- [Output formats](#output-formats)
- [Source data](#source-data)
- [Constraints on what is claimed](#constraints-on-what-is-claimed)
- [Cache](#cache)
- [Known limitations](#known-limitations)
- [Environment](#environment)
- [Exit status](#exit-status)
- [Development](#development)
- [Licence](#licence)

---

## Synopsis

```text
etimo WORD [options]

  -l, --language CODE     starting language, in Wiktionary codes (default: it)
  -s, --sense N           which of several words the spelling stands for
      --senses            list those words, and exit
  -d, --depth N           how many steps at most (default: 12, maximum 100)
  -c, --chain             main line only, one link per line
  -j, --json              structured output, for feeding into something else
      --no-compounds      do not break compounds into their pieces
      --as LEMMA          when the form points at several words, follow this one
      --as-written        do not resolve an inflected form to its lemma
      --no-cache          always ask the network
      --cache-ttl N       after how many days to re-fetch an entry (default: 30)
      --clear-cache       delete the stored pages and exit
      --prune-cache       drop expired pages and reclaim the space
      --cache-stats       report how much is stored locally and exit
      --no-color          disable colours
```

```bash
etimo fuoco                 # full tree
etimo caffè --chain         # main line only
etimo riso --senses         # enumerate the words this spelling stands for
etimo focus --language la   # start from a Latin word
etimo ciao --json           # structured output
```

---

## Installation

Requires Python 3.10 or later.

```bash
pipx install .          # or, for development:
uv pip install -e ".[dev]"
```

One runtime dependency: `mwparserfromhell`, the library Wikimedia uses to parse
its own pages. Networking, interface and formatting use the standard library
only.

---

## Description

`etimo` resolves a form to a Wiktionary entry, reads the etymology declared
there, and repeats the operation on each ancestor it finds. The walk terminates
when an entry declares a linguistic endpoint, when no further data is available,
or when a limit set by `--depth` is reached.

A chain may be long. `padre` resolves in five steps:

```text
$ etimo padre
padre (it)
└─ derived from Old Italian
   └─ patre (roa-oit)
      · the page exists but does not cover Old Italian
      └─ inherited from Latin
         └─ pater (la)
            · step reported by the entry «padre»
            └─ inherited from Proto-Italic
               └─ *patēr (itc-pro)
                  └─ inherited from Proto-Indo-European
                     └─ *ph₂tḗr (ine-pro)
                        └─ formed with affixes from
                           ├─ *peh₂- (ine-pro) «to protect, shepherd»
                           │  └─ √ reconstructed form
                           └─ *-tḗr (ine-pro)
                              └─ √ reconstructed form

5 steps · 1 link may skip stages · 2 terminals: 2× reconstructed form
```

Forms prefixed with an asterisk are **reconstructions**: they are not attested
in any text and are established by comparing attested descendants. A branch
ending on one terminates as `reconstructed form`, not as missing data — the
comparative method reaches no further back, which is a fact about the method and
not a gap in the source.

A form with several components yields several branches. Neither branch is the
principal one:

```text
$ etimo capolavoro --depth 3
capolavoro (it)
└─ formed with affixes from
   ├─ capo (it)
   │  · doublet of «chef»
   │  └─ inherited from Vulgar Latin
   │     └─ capus (la-vul)
   │        · the entry does not separate Vulgar Latin: read under Latin; the entry records 2 distinct etymologies; following «Etymology 1»
   │        └─ inherited from Latin
   │           └─ caput (la)
   │              · step reported by the entry «capo»
   │              └─ ↓ depth limit reached
   └─ lavoro (it)
      └─ ? etymology not interpreted
         the entry says: «Deverbative from lavorare; perhaps corresponding to labor.»
         perhaps labor (la) — «perhaps corresponding to»

3 steps · 2 terminals: 1× depth limit reached, 1× etymology not interpreted
```

### Notation

| element | meaning |
| --- | --- |
| `lemma (code)` | a form and its Wiktionary language code |
| `«text»` | quoted from the entry: glosses, cited phrasings, attributions |
| unquoted text | stated by `etimo` about the entry |
| `· text` | a note attached to the node above it |
| `perhaps X — «…»` | a proposal recorded by the entry, with its attribution |

Citations and commentary are also distinguished by colour where the terminal
supports it. The guillemets carry the distinction when it does not.

---

## Relations

Three relations may appear between a node and its ancestor. They are not
interchangeable.

| relation | claim |
| --- | --- |
| `inherited from` | continuous transmission between speakers of successive stages of one language |
| `borrowed from` | the form was taken from another language at some point |
| `derived from` | the form goes back to the ancestor **ultimately**; intermediate stages are not specified |

```text
$ etimo caffè --depth 2
caffè (it)
└─ borrowed from Ottoman Turkish
   └─ قهوه (ota) [kahve]
      └─ borrowed from Arabic
         └─ قَهْوَة (ar)
            └─ ↓ depth limit reached

2 steps · terminal: depth limit reached
```

`inherited` and `borrowed` describe passages the source presents as immediate.
`derived` does not: it asserts descent without asserting adjacency.

```text
$ etimo riso --sense 3
This entry records 4 distinct etymologies. For the others: --sense 2 … --sense 4
riso (it)
· the entry records 4 distinct etymologies; following «Etymology 3»
└─ inherited from Late Latin
   └─ oryza (la-lat)
      · the entry does not separate Late Latin: read under Latin
      └─ derived from Ancient Greek
         └─ ὄρῡζα (grc)
            · derived from Iranian, whose form the source does not give
            └─ ◌ source names the language, not the form
               perhaps *wrinǰiš (ira-pro)

2 steps · 1 link may skip stages · terminal: source names the language, not the form · etymology 3 of 4
```

Between Late Latin and Ancient Greek lie centuries the entry does not itemise.
The summary line counts such links separately, so that a tree is not read as
more complete than the source makes it. In JSON, each link carries
`contiguous: true|false`.

This example also shows two limits reported rather than concealed. The entry
names Iranian as the next stage without giving a form, so the branch terminates
on `source names the language, not the form`; the reconstruction it mentions
elsewhere is recorded as a proposal rather than drawn as a link.

Adverbs in the surrounding prose are read as well:

| phrasing | effect |
| --- | --- |
| *ultimately from X* | the link is marked as skipping stages |
| *from X via Y* | Y is the nearer ancestor; the chain is ordered accordingly |
| *itself from*, *in turn from* | confirms that textual order is chain order |

### Chronological validation

An entry may name as ancestor a language that began after its supposed
descendant had ceased — e.g. modern German as the source of a Lombardic word, four
centuries after Lombardic ended. The condition is checked against approximate
attestation spans and reported in a note; the chain is left as the entry gave
it, since rearranging it would substitute the tool's claim for the source's.

The check fires only when the claimed ancestor *begins* after the descendant has
*ended*. Languages overlapping in time never trigger it, whatever their kinship is.

---

## Terminals

Every branch ends in a terminal. Terminals fall into two classes, and the class
is reported in the output and in the JSON field `linguistic`.

**Findings** — the language has nothing further to yield:

| | | |
| :-: | --- | --- |
| `√` | reconstructed form | a reconstructed form was reached; there is nothing before it to reconstruct |
| `⊗` | uncertain origin | the source states outright that the origin is unknown |
| `≈` | imitative origin | the form imitates a sound and was not transmitted |
| `≡` | named after | the form comes from a person or a place |
| `·` | data exhausted | the entry records nothing further |
| `=` | already shown above | the branch rejoins one drawn elsewhere in the tree |

**Limits** — of the source or of this program:

| | | |
| :-: | --- | --- |
| `◌` | source names the language, not the form | the entry states where, not what |
| `?` | no entry · language not covered · no etymology recorded | the source does not hold it |
| `?` | etymology not interpreted | the source states something the parser could not read; the text is printed |
| `↓` | depth limit reached | the walk was cut short by `--depth` |
| `↺` | circular reference | the source points back into the current branch |
| `!` | data not retrievable | the network request failed |

The two classes are printed in different colours where colour is available. A
limit is never rendered as a finding.

`etymology not interpreted` prints the source text rather than discarding it:

```text
$ etimo allogliato
The entry «allogliato» states its etymology in prose that this tool
cannot turn into a chain. Its text is printed as the source gives it.
allogliato (it)
└─ ? etymology not interpreted
   the entry says: «From loglio.»

0 steps · terminal: etymology not interpreted
```

The information is available to the reader even though the parser could not
construct the link.

### Competing proposals

Where an entry offers proposals instead of an origin, every proposal is
recorded, none is walked, and the terminal remains `uncertain origin`:

```text
$ etimo bravo
bravo (it)
└─ ⊗ uncertain origin
   perhaps brahaigne (fro) «barren»
   perhaps *bravus (la-vul) — «Probably from»
   perhaps prāvus (la) — «from a fusion of»
   perhaps brau (oc-pro) «show-off» — «Less likely from»
   perhaps *bragos (cel-gau)
   perhaps *hrawaz (gem-pro) «raw, uncooked» — «'to strut'). Or perhaps borrowed from a descendant of»

0 steps · terminal: uncertain origin
```

Six proposals pointing to Latin, Occitan, Gaulish and Germanic. Selecting the
first would yield a tidier tree and a false one. Each proposal carries the
phrasing under which the entry offered it, so a proposal the source called
*«less likely»* is not read as one it endorsed.

---

## Declarations in definition lines

A minority of Italian entries carry an Etymology section. The remainder declare
in the definition line what the form is, in templates. Three declaration types
are recognised, each handled differently:

| declaration | handling | example |
| --- | --- | --- |
| pointer | resolved before the walk; not a link | `far` → `fare` |
| derivation | a link, marked as read from the definition | `tubicino` → `tubo` |
| contraction | several components, as a compound | `dal` → `da` + `il` |

```text
$ etimo far --depth 1
far (it) — apocopic form of «fare»
the history below is the lemma's

fare (it)
└─ inherited from Late Latin
   └─ facio (la-lat)
      └─ ↓ depth limit reached

$ etimo tubicino --depth 1
tubicino (it)
└─ diminutive of
   · as stated in the definition
   └─ tubo (it)
      └─ ↓ depth limit reached

$ etimo dal --depth 1
dal (it)
└─ compound of
   ├─ da (it)
   │  └─ ↓ depth limit reached
   └─ il (it)
      └─ ↓ depth limit reached
```

Classification is by **target shape**, not by template family. A single-word
target is resolvable; a phrase, a link to another Wikimedia project, or
comma-separated alternatives are not, and yield no declaration at all rather
than a request for a page that cannot exist.

**Acronyms are out of scope.** An entry unfolding into a phrase — `CEI` into
«Conferenza Episcopale Italiana» — states how the letters are read, not where
a word came from: an acronym does not descend from its expansion, it is a way
of writing it. Such entries report no recorded etymology.

The same rule keeps the abbreviations that *are* etymological. `{{abbreviation
of}}` naming a single word is a pointer like any other, since the word it names
has a history to reach. Only the target's shape decides, so removing acronyms
did not remove those with them.

The note `as stated in the definition` marks the sole case where a synchronic
claim is read as a link. `navicella` is analysable as a diminutive of `nave` yet
entered Italian already formed; entries carrying an etymology of their own are
never subject to this rule.

A synchronic analysis stated in the etymology itself is recorded as a note and
never walked. `{{surf}}`, and the phrasings *by surface analysis*, *equivalent
to*, *morphologically* and *synchronically*, all mark a description of the form
as it now stands rather than an account of where it came from:

```text
$ etimo minigolf --depth 1
minigolf (it)
· synchronically analysable as «mini-», «golf»
└─ borrowed unadapted from English
   └─ minigolf (en)
      └─ ↓ depth limit reached

1 step · terminal: depth limit reached
```

`synonym of` is never followed: a synonym is a distinct word.

---

## Ambiguity and pointers

### Several etymologies under one spelling

Where a spelling covers unrelated words, the sense is not chosen silently. On a
terminal the tool asks; `--senses` lists the alternatives and exits:

```text
$ etimo riso --senses
«riso» is four different words here. Which one?

  1  noun        laughter, laugh  < rīsus (la)
  2  participle  past participle of «ridere»
  3  noun        rice  < oryza (la-lat)
  4  verb        misspelling of «risò»
```

The indices are those accepted by `--sense`. Sections without an etymology of
their own — 2 and 4 above — are listed here but omitted from the interactive
prompt, since selecting them would yield nothing. The prompt is written to the
terminal and read from the keyboard, so redirection captures the tree alone.

### Inflected forms

An inflected form carries no etymology; it declares the lemma it belongs to.
That pointer is resolved before the walk and reported outside the tree, since an
inflected form does not descend from its lemma:

```text
$ etimo amata
amata (it) — feminine singular of «amato», past participle of «amare»
the history below is the lemma's

amare (it)
· the entry records 2 distinct etymologies; following «Etymology 1»
└─ inherited from Latin
   └─ amo (la)
      · the entry records 2 distinct etymologies; following «Etymology 1»
      perhaps *amāō (itc-pro) — «Perhaps»
      perhaps *h₃emh₃- (ine-pro) «to take hold of»
      └─ formed with affixes from
         └─ *amāō (itc-pro)
            └─ derived from Proto-Indo-European
               └─ *h₃emh₃- (ine-pro)
                  · the entry «*amāō» also gives «*-āō», not reached here
                  └─ √ reconstructed form

3 steps · 1 link may skip stages · terminal: reconstructed form · etymology 1 of 2
```

Pointers may chain and are followed up to four hops, stopping at the first entry
with an etymology of its own. An entry carrying an etymology is never
redirected: direct evidence takes precedence over a cross-reference.
`--as-written` suppresses resolution.

The note on the last node illustrates a related rule. Where an entry passed
earlier declares forms the walk does not reach — because a later entry gave a
different account, or because the chain ended first — those forms are named
rather than discarded, with the entry that declared them.

### Several pointer targets

One spelling may be a form of unrelated lemmas. Targets are selected by name,
since they have one. Where no terminal is attached, the first is followed and
the choice is reported:

```text
$ etimo "po'" --depth 1
«po'» is a form of three different words. Which one?

  poco               noun    no gloss given
  poi                adverb  then, later
  puoi               verb    you can

No one to ask, so following «poco». Choose with --as poco.
po' (it) — apocopic form of «poco»
the history below is the lemma's

poco (it)
└─ inherited from Latin
   └─ paucus (la)
      └─ ↓ depth limit reached

1 step · terminal: depth limit reached
```

`etimo "po'" --as puoi` selects directly. Targets are deduplicated on
destination: a lemma reached from two parts of speech is one choice. Every
alternative appears in the JSON under `points_at`, each marked `chosen` or not,
so a program can always tell that a choice was made on its behalf.

---

## Output formats

### Chain

`--chain` drops the branches and prints the main line:

```text
$ etimo caffè --chain
caffè (it)
  ← قهوه (ota) [kahve]  borrowed from Ottoman Turkish
  ← قَهْوَة (ar)  borrowed from Arabic
  ← ? etymology not interpreted

2 steps · terminal: etymology not interpreted
```

### JSON

`--json` emits the same content as data. Terminals carry their class:

```json
"terminal": { "type": "uncertain_origin", "label": "uncertain origin",
              "linguistic": true }
```

Ambiguity is declared rather than resolved silently:

```json
"ambiguous": true,
"senses": [
  { "index": 1, "part_of_speech": "noun", "definition": "laughter, laugh",
    "chosen": true,  "ancestor": { "lemma": "rīsus", "language": "la" } },
  { "index": 3, "part_of_speech": "noun", "definition": "rice",
    "chosen": false, "ancestor": { "lemma": "oryza", "language": "la-lat" } }
]
```

---

## Source data

All data comes from **en.wiktionary.org**. The tool fetches page source, parses
it, and follows what it finds. It holds no etymological knowledge of its own.

### Choice of edition

The English Wiktionary encodes etymologies in **templates** rather than prose:

```text
{{inh|it|la|focus}}     inherited · Italian · from Latin · the word focus
{{bor|it|ota|قهوه}}     borrowed · Italian · from Ottoman Turkish · qahve
{{unc|la}}              origin uncertain
```

The third is the decisive one: **uncertainty is encoded as data**, which is what
permits "the source declares the origin unknown" to be distinguished from "the
parser found nothing". Editions that state etymologies in sentences, including
the Italian Wiktionary, do not support that distinction reliably.

### Two encodings

Wiktionary is mid-migration between the prose-with-templates style and a fully
structured one. Both are read. Prose takes precedence where both are present,
as it generally declares more steps; the structured format is used where prose
is absent. Without it, approximately one Latin entry in five would break the
chain.

### Coverage

Measured on 2 000 randomly selected Italian entries, in August 2026:

| | |
| --- | ---: |
| entries with an etymology section that yield a chain | **90%** |
| entries that yield a chain **or** readable text | **98%** |
| entries with no etymology section on Wiktionary at all | 36% |

The last figure is a property of the source, not of the tool.

---

## Constraints on what is claimed

One rule governs the output:

> **A finding about the language is stated only on positive evidence** — the
> source said something and it was understood. Failure to find something the
> parser knows how to read is never, by itself, a fact about the language.

Consequences, each deliberate:

- **An unfetched page is not an endpoint.** A reconstructed form without an
  entry terminates as `no Wiktionary entry`, not as `reconstructed form`.
- **A declared uncertainty outranks the proposals following it.** *«Of uncertain
  origin, probably from X»* terminates as uncertain, with X recorded as a
  proposal. Walking X would substitute a conjecture for the source's verdict.
- **A form cited for comparison is not an ancestor.** *«Compare German Bank»* is
  a remark.
- **Convergent branches are not an error.** Where a compound's components share
  an ancestor, the second reads `already shown above`.
- **Unparsed prose is printed, not discarded.**
- **Forms declared but not reached are named.** Where two entries give different
  accounts of the same stretch, the walk follows the page it is reading and
  records what the other entry stated, rather than choosing silently between
  them.

Output asserting something the source does not support is a defect, not a
limitation.

---

## Cache

Fetched pages are stored in `~/.cache/etimo/pages.sqlite`, or under
`XDG_CACHE_HOME` where set, and expire after thirty days.

The cache is effective because etymological chains converge: thousands of words
resolve to a few hundred ancestors, so upper entries are requested by every word
in the family. **Absent pages are recorded as well** — many forms cited in
etymologies have no page, and re-requesting them on every run would be the
largest avoidable source of traffic.

Expiry exists because Wiktionary is corrected over time; a permanent local copy
would serve superseded answers indefinitely.

| option | effect |
| --- | --- |
| `--no-cache` | bypass the cache entirely |
| `--cache-ttl N` | set the expiry threshold in days |
| `--cache-stats` | report stored size and entry count |
| `--prune-cache` | delete expired entries and reclaim space |
| `--clear-cache` | delete all stored pages |

A cache that cannot be read or written is reported and bypassed. It is an
optimisation, not a dependency.

---

## Known limitations

- **First lookup latency.** An unvisited chain costs three to eight requests,
  spaced half a second apart to stay within reasonable use of a free public
  service. Subsequent lookups are served locally.
- **Glosses are in English**, as written by the source. They are not translated,
  as doing so would introduce unverifiable content.
- **Intermediate ambiguity is resolved silently.** Where a form partway up the
  chain covers several unrelated words, the first is followed and a note
  records it. The choice is offered only for the requested word.
- **Non-arboreal etymologies are simplified.** Blending, contamination and
  merged histories are represented as trees and lose detail.
- **Step order is inferred** from the order of mention in the source. This is
  correct for *«from X, from Y»* and may be wrong for less regular phrasings.
- **A proposal attributed to a named scholar is read as asserted.** *«Another
  theory, advanced by X, suggests…»* enters the chain rather than the list of
  proposals. The qualifying markers cover *possibly*, *perhaps*, *probably* and
  their kin, and not the forms an entry uses to attribute a hypothesis to
  someone.
- **Coverage is Wiktionary's**, and is uneven on technical, regional and recent
  vocabulary.

Each of these is reported in the output where it applies.

---

## Environment

| variable | purpose |
| --- | --- |
| `ETIMO_USER_AGENT` | identifies the client to Wikimedia; required by their terms of use for anything beyond casual use |
| `XDG_CACHE_HOME` | overrides the cache location |
| `NO_COLOR` | disables colour, as does a non-terminal stdout |

```bash
export ETIMO_USER_AGENT="etimo/0.1.0 (name.surname@example.com)"
```

---

## Exit status

| code | condition |
| ---: | --- |
| `0` | success |
| `1` | error |
| `2` | invalid command line |
| `3` | word not found |
| `4` | source unreachable |

---

## Development

```bash
uv pip install -e ".[dev]"
pytest                 # 336 tests, no network, about a second
ruff check src tests
mypy src/etimo
```

No test touches the network. Parser and walker run against fixed wikitext
through `DictSource`, the HTTP layer against a stubbed `urlopen`. A failing test
therefore always indicates a change in the code, never in Wiktionary.

The architecture is a pipeline with one-way dependencies: `wikitext` parses text
and knows nothing of the network; `walker` traverses and knows nothing of the
output format; `render` returns strings and never prints; `cli` is the only
module that touches the terminal. The page source is a `Protocol` with three
implementations — network, cache, dictionary — which is what makes the above
testable without mocks.

One test is a strict `xfail`, marking a known defect rather than a failure: it
is listed under [Known limitations](#known-limitations) and carries the
reasoning for leaving it open.

The examples in this file are checked against live output by
`tools/check_readme_examples.py`, which is not part of the suite: the suite is
offline so that a red test always means the code changed, whereas this asks
whether the documentation still matches the tool, and only the live source can
answer that.

`ANALYSIS.md` records an audit of the tool: what was measured, what was found
and what was corrected.

---

## Licence

MIT — see [LICENSE](LICENSE).

Data originates from Wiktionary and is distributed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Anything
published using this tool carries that licence on its *content*.
