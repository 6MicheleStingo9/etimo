# Reading an etymology section

Written by the linguist session for whoever reads Wiktionary next — a person or
a parser. `README.md` says how the audit runs; this says what it is looking at.

Everything here is a claim about **what the source does**, not about what is
true of the language. `etimo` never judges Wiktionary: if an entry is wrong,
reporting it wrong is the correct behaviour. The only question is whether the
tree says what the entry says, in the way the entry says it.

---

## An etymology section is not one kind of statement

It is a paragraph of prose in which several different kinds of claim sit side
by side, often in one sentence, distinguished by a single word. Treating them
alike is the origin of nearly every defect this project has found.

| kind | how it appears | what the tree may do |
| --- | --- | --- |
| **descent** | `From {{inh\|it\|la\|focus}}` | draw a link |
| **conjecture** | `Possibly`, `Perhaps`, `Probably`, `apparently` before the relation | record as hypothesis; **never** a link |
| **competing analyses** | `From X or from Y`, `and/or` | both as hypotheses; no link — but see *the shared component* |
| **synchronic analysis** | `{{surf}}`, «Morphologically…», «Analysable as…» | a decomposition of the modern word, not a descent |
| **denial** | «…however this is just a corruption of…» | what is denied is not an ancestor |
| **comparison** | `{{cog}}`, «Compare…» | a cognate is never an ancestor |
| **circumstance** | «introduced by mercenaries», «via the language of trade» | not an etymon; leaves the chain intact |
| **attribution** | «a theory advanced by Jasanoff suggests…» | the qualifier is the **verb**, not the name |
| **declared absence** | `{{rfe}}`, `{{unk}}`, `{{unc}}` | a terminal, and a **fact**: the source says it does not know |
| **origin without an etymon** | «onomatopoeic», «imitative», `{{intnat}}`, «named after…» | a terminal, and a **fact**: the source states an origin that has no ancestor to draw |

The last row is the one most easily missed, because it looks like silence and
is not. «Of onomatopoeic origin» is a positive claim about where a word came
from; it simply names a *manner* rather than a *word*. Reporting it as "nothing
found" loses information the entry actually gave, and — worse — it is
indistinguishable in the output from an entry that says nothing at all. The two
must not share a terminal.

The same holds for `{{intnat}}` (an internationalism: the word arose across
several scientific languages at once, with no single donor) and for eponyms
(`ambaradam`, from the Battle of Amba Aradam). Both name an origin. Neither
yields an ancestor.

---

## The distinctions that carry the most weight

### The qualifier is the verb, not the attribution

«Another theory, advanced by Jasanoff, suggests that…» is a conjecture because
of *suggests*, not because of *Jasanoff*. An entry may name a scholar while
asserting flatly («Meyer-Lübke derives it from…» is an assertion of what
Meyer-Lübke did, and the entry endorses it), and may hedge without naming
anyone. Keying on the presence of a name gets both cases wrong.

### A marker governs the nearest relation, not the sentence

«Possibly from A, from B, from C» hedges **A**. B and C are the ordinary
ancestry of A and are not in doubt — the entry is saying *if* it came from A,
then the rest follows. Spreading the marker over the whole sentence throws away
a chain the source asserted.

The converse trap: in «Probably from A. Compare B», the marker never reaches B
at all, because B is a comparison and was never a candidate ancestor.

### The shared component of competing analyses is not in competition

```
agnellino:      From {{af|it|agnello|-ellino}} or {{af|it|agnello|-ino}}.
acquattamento:  From {{suffix|it|acquattare|mento}} or {{suffix|it|acquattarsi|mento}}.
allotropia:     From {{af|it|allo-|-tropia}} or {{af|it|allotropo|-ia}}.
```

In the first two the analyses **disagree about the suffix and agree about the
base**. `agnellino` comes from `agnello` under either reading; `acquattamento`
from the verb `acquattare` in either its plain or reflexive form. Refusing to
draw anything discards a fact both alternatives assert.

`allotropia` is the case where the caution is right: the two analyses share no
form, so nothing is certain but the result.

**The rule this yields**: when competing analyses are recorded as hypotheses,
any form that appears in *every* one of them is asserted by the entry and may
be drawn. A form appearing in some but not all may not. This distinguishes the
first two cases from the third without a judgement call.

### An inflected form resolves to its lemma, and the resolution can hide a section

`dipinto` and `ansa` were rejected as seed candidates for a reason worth
recording: they are inflected forms, `etimo` resolves them to `dipingere` and
`ansare`, and the conditioned clause on the inflected page is therefore never
walked. Any expectation written against such a page tests a path the tool does
not take.

---

## What was excluded from the population, and why the reason is linguistic

The agreed population is **102 692** entries: the 129 650 Italian lemmas less
four classes. A crude shape-based classifier — spaces, apostrophes, leading
capitals, leading hyphens — counts 101 378 over the corpus catalogue, 1.3%
below it. **That agreement is worth less than it looks**, because the two
methods disagree in both directions and the errors partly cancel: the shape
classifier drops 927 affixes the agreed population keeps, and keeps the
lowercase acronyms (`abc`, `acmonital`, `aennino`) the agreed population drops.
Uppercase acronyms happen to fall under its initial-capital rule, for the wrong
reason. Use it to sort a survey slice, not to state a population size. The exclusions are not tidiness — each names a class whose
"etymology" is a different kind of object.

| excluded | why |
| --- | --- |
| **multiword terms** | mostly: a locution has a phrase history, not an etymon. But see below — the exclusion is right for the majority and wrong as a blanket. |
| **proper nouns** | toponyms and surnames descend by a mechanism the relation templates do not express — place name → family name → given name. `{{surname}}` and `{{place}}` state a category, not an ancestry. |
| **acronyms and abbreviations** | the "source" of `acmonital` is an expansion (*acciaio monetario italiano*), not an etymon. The relation is spelling to phrase, and it runs in the opposite direction from descent. |
| **inflected forms** | they resolve to their lemma; counting them counts the lemma twice. |

### Multiword terms are two classes, and only one of them is rightly excluded

They do carry Etymology sections far more often than the exclusion implies:
**44.1%** of the locutions in the first survey slice had one. But most of those
sections are not etymologies.

```
toccare il fondo         {{lit|to touch the bottom}}. Compare {{cog|fr|toucher le fond}}.
fare un buco nell'acqua  {{lit|to make a hole in the water}}.
a fior di pelle          {{lit|at surface of skin}}. Compare {{cog|fr|à fleur de peau}}.
```

`{{lit}}` is a **literal gloss**: it says what the phrase means word for word,
not where it came from. It lives in the Etymology section because there is
nowhere else to put it. A tool reading that section finds a template it cannot
interpret and is right not to — but it must not record the entry as *silent*,
because the entry spoke and said something else.

The `{{cog|fr|…}}` alongside is a **calque comparison**, not a derivation: the
entry is noting that French has the same figure, without claiming which came
first. Correctly not an ancestor.

But a minority are ordinary etymologies, because the phrase was **borrowed as a
single block**:

```
a posteriori   {{lbor|it|la-med|ā posteriōrī}}
buona fede     From {{inh|it|la|bona fides}}.
ping pong      {{ubor|it|en|ping pong}}
ad personam    {{bor+|it|la|ad persōnam}}
```

These have a genuine etymon — one foreign phrase — and behave exactly like a
one-word lemma. In a cached sample of 55 locutions with a section, **4 (7%)**
were of this kind.

**The test is not whether the term has a space in it.** It is whether the
section carries a relation template. A locution formed in Italian has no
etymon and nothing to draw; a locution borrowed whole has both. Excluding them
by shape excludes the second kind for a property it does not have.

The class is small — on these figures, of the order of 300 entries across the
corpus — and it is the least urgent thing on the list. But it should be
excluded by what its section says, not by its spelling.

---

**This matters for any measurement taken in alphabetical order.** Italian
adverbial locutions are overwhelmingly headed by a preposition, and the
commonest is `a` — `a caldo`, `a cascata`, `a singhiozzo`, `alla moda`, `all'unanimità`.
Affixes sort under `-`. Toponyms and surnames carry an initial capital, which in
most collations sorts them apart as well.

So a walk through the corpus in alphabetical order does **not** meet these
classes at a steady rate. Measured on the first 6 805 entries of the corpus
survey, which ran from `'` to `ammannare`:

| | in that slice | in the whole corpus | |
| --- | ---: | ---: | ---: |
| lemmas | 68.6% | 79.7% | |
| locutions | 15.5% | 8.4% | 1.8× |
| affixes | 6.0% | 0.7% | **8.6×** |
| proper nouns | 9.8% | 11.2% | 0.9× |

The affixes are the sharpest distortion and the least expected: `-` sorts
before every letter, so a single stretch at the very start of the walk holds
two fifths of every affix in the corpus. The proper nouns, which looked like
the obvious culprit, are in fact slightly *under*-represented — the A- toponyms
are numerous but no more so than elsewhere.

Locutions and proper nouns yielded "no chain" 93% and 73% of the time, for
entirely correct reasons. So, read as a corpus figure, that slice reported
45.7% "no chain". The true lemma figure in the same slice is **31.6%**, of
which 28.6% is an absent section and only **3.1%** — about 3 100 entries
projected over the corpus — is a gap in our reading.

**A survey outcome must always be reported next to the composition of what it
surveyed.** Without the denominator it is a statement about a letter of the
alphabet wearing the costume of a statement about the corpus.

---

## Why the seed holds 21 entries and not 54

The seed is the only artefact in this project not derived from the parser's own
tables. The invariants, the survey and the ledger all read Wiktionary with the
same lists the parser uses, so they can find errors *within* those lists and
never errors *of* them. The seed is written by reading entries as prose. That
is its whole value, and it dictates what belongs in it.

A case earns its place when it is the **smallest thing that distinguishes two
behaviours the tool could plausibly have** — not an interesting word, not a
word that once broke. Thirty-three cases were removed because they were
**overdetermined**: two or more mechanisms in the code each produced the
expected output on their own, so either could be deleted and the case would
stay green. A case that cannot fail alone is decoration.

`cavolo` is the example, and it is kept with the flaw written on it: its two
candidates are *also* chronologically impossible above Late Latin, so the
chronology check would exclude them even with the conditioning rule removed
entirely.

**Overdetermination is not visible by breaking everything.** Break everything
and every case turns red, which looks like a seed full of good guards. It is
visible only by breaking **one mechanism at a time and watching who stays
silent**. The useful signal is not which cases light up; it is which do not
light up when they should.

The honest count, carried in the file itself: **21 entries, two real guards.**
`dipelare` for alternation and `rodomonte` for conditioning over a formation
template. The rest verify results rather than mechanisms — which is not a
defect but the ceiling of what is reachable when the code has more defences
than the source has entries that isolate them.

Each case states its own reason in its `why` field, including the four that
carry `PRESIDIUM` or `OVERDETERMINED` and the list of entries checked and
rejected while hunting for a clean guard on conditioning over a linear
relation. That guard does not exist in this seed, and the reason is in the
data: an isolating case would need a modaliser directly before a
`{{der}}`/`{{inh}}`/`{{bor}}` that yields a form, with no alternation, a
chronologically ordinary ancestor, and a lemma rather than an inflected form.
Seven candidates were read and each failed one of the four.
