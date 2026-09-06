# What the 128 silent entries actually say

Answer to issue #5. Written by the linguist session.

## What was classified, and what that limits

The corpus survey's first slice — 6 805 entries — held **128 lemmas that have
an Etymology section and yield no chain**. Each was fetched and its Italian
Etymology section read and classified by shape.

**121 of 128 were resolved.** Seven still fail on the network (`acidulare`,
`acidulato`, `acusma`, `aerobox`, `aggraziato`, `alcmanio`, `allotropia`) and
are counted separately, not silently folded into a class.

*Provenance.* The counts below are the completed retry pass's own summary, and
they sum to 128. The raw classification file it wrote was then damaged: a
second retry pass of mine was still running against the same file, hit
Wiktionary's rate limiter, and its write clobbered several entries the first
pass had resolved — a plain lost update between two of my own background jobs.
The damaged file shows 8 unresolved instead of 7. It is not the source of these
figures, and re-deriving it costs one clean pass once the limiter releases.

**Two things this does not establish.** The slice ran alphabetically from `'`
to `ammannare`, so it is rich in `a-` parasynthetic verbs and their derivatives
— exactly the class that attracts the largest finding below. Every projection
here should be treated as an upper bound until the hash-ordered survey produces
a representative slice. And the classification is by the *shape* of the
section, not by whether the reading it implies is correct.

## The count

| class | n | % | ours or the source's? |
| --- | ---: | ---: | --- |
| **relation written in prose with `{{m}}`** | **52** | **40.6%** | **ours** |
| declared absent — `{{rfe}}`, `{{unk}}`, `{{unc}}` | 20 | 15.6% | correct: a fact |
| no Etymology section (variants, participles) | 14 | 10.9% | see below |
| competing analyses recognised | 10 | 7.8% | correct — mostly |
| relation present, form withheld | 10 | 7.8% | **partly ours** |
| unresolved (network) | 7 | 5.5% | — |
| mention without a governing verb | 5 | 3.9% | **ours** |
| cognate only | 4 | 3.1% | correct |
| bare prose | 3 | 2.3% | mixed |
| grammatical template / internationalism / onomatopoeia | 3 | 2.3% | correct: facts |

**Roughly 30% is the tool behaving correctly** on entries that state something
other than a descent. That part must not be "fixed": an entry saying
`{{rfe}}` or «Of onomatopoeic origin» has spoken, and reporting it as silent
is the defect, not the reading.

---

## 1. The relation is in the prose and the form is in a `{{m}}` — 52 entries

```
absidiola      From {{m|it|abside}}.
affondatoio    From {{m|it|affondare}}.
afflittivo     From {{m|it|affliggere}}.
accordicchio   From {{m|it|accordo}}.
accolitato     From {{m|it|accolito}}.
adultizzazione From {{m|it|adulto}}.
acquaragia     From {{m|it|acqua}} + {{m|it|ragia}}.
accagionare    Probably derived from {{m|it|cagione}}.
acquisire      Reformed from {{m|it|acquisito}}; cf. {{m|it|acquistare}}.
accapigliarsi  From {{m|it|capegli}}, older form of {{m|it|capelli}}.
```

The prose carries the relation; the `{{m}}` carries the form. These are
unambiguous Italian derivations and none of them reaches the tree.

**Why editors write it this way, and why it will not go away.** It is a gap in
Wiktionary's own template vocabulary, not a house style. `{{inh}}`, `{{bor}}`
and `{{der}}` are cross-language — they presuppose a different source language.
`{{af}}` and `{{suf}}` require naming the affix. But *«X comes from Y, both
Italian, and I do not want to commit to which affix»* has **no template**. So
it lives in prose, and it will keep living there.

Our reading gap mirrors a gap in the source.

**What distinguishes this from a mention.** `{{m}}` alone means nothing — it is
the neutral way to name a form. What makes these relations is the governing
verb phrase immediately before: `From`, `Derived from`, `Reformed from`,
`Deverbal of`, `Unsuffixed past participle of`, `Feminine of`. A `{{m}}` with
no such phrase before it (`Compare {{m|it|ino}}`, `See {{m|it|abbigliare}}`) is
not a relation and must stay out.

The recommendation is therefore **not** «read `{{m}}` as a relation». It is:
**read the governing phrase, and let it license the `{{m}}` that follows it** —
the same principle already applied to the alternation pattern, where what
matters is what opens the clause.

Sub-classes worth separating, because they are not all descent:

| | example | |
| --- | --- | --- |
| plain derivation | `From {{m|it|abside}}` | a link |
| compound written by hand | `{{m|it|acqua}} + {{m|it|ragia}}` | a formation, like `{{af}}` |
| conjectured | `Probably derived from {{m|it|cagione}}` | a hypothesis, not a link |
| grammatical form | `Feminine of {{m|it|alunno}}` | **not a descent** — a form of the same lexeme |
| acronym expansion | `acmonital`, `aennino` | excluded population anyway |

The fourth row matters: `alunna` is not *descended from* `alunno`, it is the
feminine of it — *mozione*, fully regular gender inflection, the same lexeme.
Drawing that as an ancestor would be a new error of the exact kind this project
exists to avoid.

**The test is whether the governing phrase names a different lexeme or another
form of the same one.**

```
DIFFERENT LEXEME → derivation, draw it
   From · Derived from · Reformed from
   Deverbal of                  acciuffare ← ciuffo,  accosto ← accostare
   Diminutive/Augmentative of   Italian alterati are lemmas in their own right
   Clipping of                  when lexicalised: porno ← pornografia

SAME LEXEME → not a descent
   Feminine of · Masculine of   mozione
   Plural of · Singular of      inflection
   Past participle of           when it is the verb form, not a deverbal noun
   Alternative form/spelling of · Apocopic form of · Syncopated form of
```

`accosto` sits on the near side of that line and an earlier draft of this
document put it on the far side. It carries `{{it-deverbal|accostare}}` and is
a deverbal **noun** — a distinct lexeme. «Unsuffixed past participle of»
describes the *mechanism* of the derivation (the form taken is the participle's,
with no suffix added), not that the word is an inflected form.

The last line connects to the fourteen variants in §3: same lexeme, so **no
link from the variant to its main form** — but the pointer should be followed
to reach that form's chain. Two behaviours, both correct, neither a link.

## 2. The source names a language and withholds the form — 10 entries

Three spellings of one idiom, and we read one:

```
agrimonia     From {{uder|it|la|-}}     ← the known one
acquirente    From {{der|it|la|}}       ← third parameter empty
albergheria   From {{uder|it|la}}       ← third parameter absent
```

All three say the same thing: *the word comes from Latin, and I am not giving
you the Latin word.* That is a positive statement about a language and a
declared limit about a form — which is exactly what the `◌` terminal was
introduced for. It should fire on all three.

The rest of this class are conditioned prose (`affannare`, `aggio` — «Probably
from…») and eponyms (`amarcord`, `ambaradam`), where the current behaviour is
correct.

## 3. The variant spellings — 14 entries

```
abadessa · abbadessa · abadia · abazia · alcol · alcole · alcool · alcoole
acquisito · affrancato · allacciato · abborracciona · ahia · amatita
```

These genuinely have **no Etymology section**. They are alternative spellings
and participial forms whose etymology lives on the main lemma, reached by
`{{alt form of}}` or `{{alt}}` in the definition line.

The entry is not silent: it says *this is a spelling of X*, and X has a chain.
Whether following that pointer is right is a design question, not a linguistic
one — but the linguistic fact is that **a variant is not an unknown**. The
entry told us where to look.

`ahia` is different and belongs with the onomatopoeias: it is an interjection
whose sibling `ahi` says «Of onomatopoeic origin».

## 4. Where the shared component of competing analyses is lost

Not a class of its own in the count — these show as "recognised" — but visible
inside it:

```
agnellino       From {{af|it|agnello|-ellino}} or {{af|it|agnello|-ino}}.
allotropia      From {{af|it|allo-|-tropia}} or {{af|it|allotropo|-ia}}.
acquattamento   From {{suffix|it|acquattare|mento}} or {{suffix|it|acquattarsi|mento}}.
```

In `agnellino` the analyses **disagree about the suffix and agree about the
base**: it comes from `agnello` under either reading. Recording both as
hypotheses and drawing nothing discards a fact the entry asserts twice. In
`allotropia` the caution is right — the two analyses share no form at all.

**The rule, which needs no judgement call**: a form appearing in *every*
competing analysis is asserted by the entry and may be drawn. A form appearing
in some but not all may not.

**But it needs one qualification, and `acquattamento` is why.** Its two
analyses differ in the base (`acquattare` / `acquattarsi`, the plain and
reflexive forms of one verb) and agree in the suffix. Intersecting the strings
therefore yields `mento` — the *affix*. That is true and useless: an affix is a
component of a formation, not an ancestor, and drawing it would assert nothing
about descent.

So: **the intersection must contain at least one base — a form that is not an
affix — before it is worth drawing.** Under that qualification `agnellino`
draws `agnello`, and both `allotropia` and `acquattamento` correctly stay
silent. That the two bases of `acquattamento` are the same verb is true and
outside what a parser can know.

---

## Ranked

1. **The governing phrase before a `{{m}}`** — 40.6% of this slice, and the
   only class here big enough to matter on its own. Needs the sub-classes kept
   apart, especially grammatical forms, which must not become ancestors.
2. **The two unread spellings of the withheld form** — small, exact, and the
   terminal for it already exists.
3. **The shared component of competing analyses** — small, but it turns a
   silence into an assertion the entry actually makes.
4. **The variants** — a design question about pointers, not a reading defect.

Nothing here is a case of `etimo` drawing something false. Every one of them is
a case of it drawing **nothing** where the entry said something — which is why
no structural invariant has ever seen them, and why twenty days of auditing did
not touch them. An absent tree is not a corrupt tree.
