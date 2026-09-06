# Picking this up again

Written for whoever opens this branch after weeks away — which, from September
2026, is how the project is worked: Michele activates the two sessions
sporadically, and they run until their quota is spent. **The conversation does
not survive; this file does.**

Read this first, then `tools/validation/README.md` for how the audit works,
`tools/validation/READING.md` for what a Wiktionary etymology section actually
says and how the seed was chosen, and `ANALYSIS.md` for what was measured when.

---

## Who decides what

| | |
| --- | --- |
| **developer session** | code, workflows, the ledger, the harness, performance — anything mechanical |
| **linguist session** | what Wiktionary says and means, which entries are worth looking at, the seed's contents, the marker vocabulary, how much corpus to validate |

The division is not bureaucratic: it works because the blind spots differ.
Nearly every defect found so far surfaced because one session tripped over the
other's error. When one of them opined on the other's ground, it added nothing
the other had not already seen better.

Reaching the peer: `ListAgents`, then `SendMessage`. **The name tells you
nothing about what a session works on.** In a multi-root workspace the name is
derived from the *first* folder in the list — here `area` — so sessions called
`area-*` may be on any project, and the peer has answered to «Etimo -
Linguist», «area-3d», «area-5a», «area-91» on different days.

So: open with one line identifying yourself and asking whether it is the right
session, and give a recognition token before the substance. `brindare` as a
negative case, `cavolo` and `pizza` annotated as overdetermined, the seven
candidates rejected while looking for a conditioning guard — no other session
holds those. Four wrong addresses were tried on 6 September before finding the
peer; each answered honestly and quickly, which is the reason to ask first and
explain second.

---

## First thing to do: read what ran unattended

Two workflows run on their own and commit to this branch.

```bash
gh run list --limit 10                       # did anything go red?
python tools/validate_wiktionary.py --summary-only 2>/dev/null || \
  python - <<'PY'
import json
from collections import Counter
led = json.load(open("tools/validation/coverage-ledger.json"))
items = led["items"]
done = [i for i in items if i.get("last_result")]
print(f"audited {len(done)} of {len(items)}")
print("failure classes:", Counter(
    i.get("last_failure_class") for i in items if i.get("last_failure_class")))
print("diagnostics:", Counter(
    i.get("diagnostic_class") for i in items if i.get("diagnostic_class")))
PY

python tools/survey_corpus.py --summary          # how far the survey has got
```

**A red run is the only thing that demands attention.** The audit exits
non-zero only for defects attributable to this code: a broken structural
invariant, an exception, or an expectation failing while the page hash is
unchanged. Entries Wiktionary has no etymology for, entries changed upstream
and network errors are recorded and stay green on purpose — a light that fires
on a third of the corpus stops being read.

If a run is red, the log names the word and the class. `PARSER_REGRESSION` means
the source said the same thing yesterday and we read it differently: that is
ours. `SOURCE_DRIFT` means the page moved.

---

## What runs

| | when | what it does |
| --- | --- | --- |
| **Wiktionary daily audit** | 03:00 UTC | 300 entries: 215 interpretive-load, 30 template-only as a sentinel, 55 barren. Plus all 21 hand-written expectation cases, every night. |
| **Corpus survey** | 05:00 UTC, 2h slices | one pass over all 127101 lemmas, recording where the tool reaches and whether every form drawn was one the source wrote |

Both live on `main` — GitHub reads `on: schedule` only from the default branch
— and both check out this branch, run its code, and push their results back
here. `main` takes no automated commits.

---

## Open, in the order I would take them

**1. The xfail on `dō`.** A theory attributed to a named scholar is read as
asserted: «Another theory, advanced by Jasanoff, suggests that…» enters the
chain instead of the proposals. The test carries the criterion the peer
established — *the qualifier is the verb, not the attribution* — and two traps
found in real entries. It touches `_CONDITIONING`, which decides what counts as
asserted, so it is not a thing to widen casually. Roughly 10–15 entries.

**2. The re-check distribution is uneven.** Some entries were re-checked 18
times in a simulated 30 days while others once. Left alone deliberately: the
right remedy depends on what *fresh* should mean, and the classes may have made
it moot. Measure before touching it.

**3. Two measurements never finished.** Fifteen agents died to a session limit
mid-analysis. Unmeasured: the operational health of the runs across time,
whether the cache key defeats itself (it uses `github.run_id`, unique per run,
so it may always be missing and falling back), and the growth of the ledger.

**4. The ledger carries 53 MB of nothing.** 125087 of its 127199 entries have
never been audited: rows saying "this word exists and we have not looked at
it", which the corpus already says. GitHub warns on every push (66 MB against a
50 MB recommendation) and a fully audited ledger would reach 67 MB — under the
100 MB hard limit, so nothing breaks, but 53 MB of empty rows are committed
every night.

The fix is to persist only entries that have a state and derive the rest from
the corpus at load time: 1.1 MB today, growing with coverage rather than
starting at the maximum. It was left undone deliberately — it changes the
format of the one file that must survive between sessions, and doing that at
the end of a long session is how a persistent store gets corrupted. Do it
first thing in a session, with the ledger backed up, or not at all.

**5. The first 6805 survey rows are alphabetical.** They were walked before
the order was scattered, so they are «a» words and not a sample. `--summary`
now reports composition and a lemma-only breakdown, which makes them readable;
re-running them would cost little, since their pages are cached.

**6. The survey's anchoring figure starts from zero.** The first 6805 entries
were surveyed before anchoring existed and do not carry it. Either let the
figure build from the entries surveyed since, or re-run those 6805 — cheap,
since their pages are cached.

**6. The survey's running percentages are not corpus figures, and must not be
read as any.** It walks in alphabetical order, and Italian sorts by grammatical
class: adverbial locutions are headed by a preposition and the commonest is
`a`, affixes sort under `-`, proper nouns under an initial capital. The first
6805 entries ran from `'` to `ammannare` and were 15.5% locutions and 9.8%
proper nouns — three and five times their share of the corpus — both classes
excluded from the agreed population, and both correctly yielding no chain
almost always. That slice reports 45.7% "no chain"; on its lemmas alone the
figure is 31.6%, of which only **3.1%** is a gap in our reading rather than an
absent section.

The remedy is not to resample. It is that **the survey must report the
composition of what it surveyed alongside its outcomes** — an outcome without
its denominator is a statement about a letter of the alphabet dressed as a
statement about the corpus. See `tools/validation/READING.md`, "What was
excluded from the population".

---

## What this project has learned about checking things

Written here because it cost a great deal and reads as pedantry until it
happens to you.

**A check that verifies an absence fails in one direction only.** Nineteen
corrections were made to the measuring instruments; nine of them accused
something that was working, and not one ever excused a defect. Every gap in
such an instrument becomes an accusation and no gap becomes an acquittal.
**When a measurement says the code is wrong, check the measurement first.**

The nineteenth is the clearest of them and took fifteen minutes to notice: an
extractor returned an empty list both when a page's Italian section had no
Etymology heading **and when the network request failed**, and printed the same
label for both. Three entries that do have etymologies were recorded as having
none. A failure of the instrument had disguised itself as a fact about the
source — which is the same direction as all the others. **A tool must be able
to say "I could not look" in words it cannot confuse with "there is nothing
there."**

**A check built on the parser's tables cannot find an error in those tables.**
It reads the source with the same incomplete list and agrees with itself. This
is why the 21 hand-written cases exist — they are the only artefact not derived
from those tables — and why the survey's anchoring check asks a flat textual
question instead of a structural one.

**Verify that a new check can fail.** Half of the ones written here could not,
at first draft: an expectation naming a relation that does not exist, a
`must_include` satisfied by a tree that made the exact error it was written to
catch, a guard whose condition could never be false. Break the code on purpose
and confirm the check goes red.

**Beware the sample you built yourself.** A synthetic corpus generated
categories with `(i * 7 + 3) % 4` and populations with `i % 20`; they share a
factor, so every interesting entry landed in one category and two rounds went
to fixing a defect that was not there. An unintended structure in how a sample
is built becomes an apparent structure in the result — and a modulus is worse
than a ranking, because a ranking is visibly an order.

**And beware the one nobody built.** This has now happened three times: a
sample taken from the head of a relevance ranking, the synthetic corpus above,
and the corpus survey's alphabetical walk. The third is the worst, because no
one chose it — reading a corpus in the order it is stored is the default, and
in Italian that order is correlated with grammatical class. Nothing had to be
constructed badly for the result to mislead.

**An order you did not choose is still a sampling.** The survey walked the
corpus alphabetically — nobody decided that, it came free with the file — and
Italian's alphabet is correlated with grammatical class: `a` is where the
adverbial locutions live (`a caldo`, `alla moda`, governed by a preposition),
capitals are where the toponyms live, `-` is where the affixes live. The first
6805 entries were 6295 «a» words and reported 45.7% of the corpus as
unreadable, where the figure for lemmas is 31.2%. The walk is now scattered by
a hash of the title, so any prefix of it is a fair sample; and every figure is
reported beside the composition it was measured on. **A figure without its
denominator is a statement about a slice dressed as a statement about the
corpus.**

**A class at 0.3% cannot be sampled.** Sixty random entries held one. Rare
classes are chased by name, not estimated.

---

## What the audit is for, and what it is not

Michele's words, September 2026: to reinforce `etimo` by checking **correct
coverage** and **variance against the source**.

`etimo` does not judge Wiktionary. If an entry is wrong, `etimo` reports it
wrong and has done its job. So "correct" has one meaning here and it is
verifiable: **the tree says what the entry says, in the way the entry says
it** — a conjecture stays a conjecture, a synchronic remark does not become a
descent, a comparison does not become an ancestor, and nothing named is lost.

`Trebisacce` was not a disagreement with the source. It was an infidelity to
it: the entry said «Morphologically from tre + bisacce, however this is just a
corruption of τραπεζὰκιον», and the tool drew as ancestors the two words the
sentence went on to deny. Every structural check passed.

That is the distinction any new check has to respect. It may assert that we
read the source faithfully. It may not assert that the source is right.
