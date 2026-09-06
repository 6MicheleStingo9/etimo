# Picking this up again

Written for whoever opens this branch after weeks away — which, from September
2026, is how the project is worked: Michele activates the two sessions
sporadically, and they run until their quota is spent. **The conversation does
not survive; this file does.**

Read this first, then `tools/validation/README.md` for how the audit works and
`ANALYSIS.md` for what was measured when.

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

Reaching the peer: `ListAgents`, then `SendMessage`. **The name changes between
activations** — it has been «Etimo - Linguist», «area-3d», «area-5a». Identify
yourself and state the subject; a wrong session will say so.

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

**4. The survey's anchoring figure starts from zero.** The first 6805 entries
were surveyed before anchoring existed and do not carry it. Either let the
figure build from the entries surveyed since, or re-run those 6805 — cheap,
since their pages are cached.

---

## What this project has learned about checking things

Written here because it cost a great deal and reads as pedantry until it
happens to you.

**A check that verifies an absence fails in one direction only.** Eighteen
corrections were made to the measuring instruments; eight of them accused
working code, and not one ever excused a defect. Every gap in such an
instrument becomes an accusation and no gap becomes an acquittal. **When a
measurement says the code is wrong, check the measurement first.**

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
