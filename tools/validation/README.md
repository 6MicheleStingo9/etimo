# Continuous validation against Wiktionary

This folder holds the harness that audits `etimo` against live Wiktionary
entries, and the ledger recording what has been audited and when.

The audit answers one question daily: **does the tool still read the source
correctly today?** Wiktionary changes under us, and the offline test suite
cannot see that by design — it runs against frozen fixtures precisely so that
a red test always means the code moved. This is the other half of that
arrangement.

---

## What it can and cannot find

**The corpus-wide checks verify that a tree is not corrupt**: no markup left in
a lemma, no language inherited from a parent, no cycle disguised as a branch,
no linguistic terminal resting on an empty form. They run on every lemma
without anything written by hand, and they catch regressions in the reading
machinery.

**They cannot find a tree that is well-formed and wrong.** Four real defects
found before this system existed all passed every structural invariant:

| entry | the tree said | the source said |
| --- | --- | --- |
| `strumentale` | descends from `strumento` + `-ale` | *by surface analysis*, a synchronic remark |
| `Trebisacce` | descends from `tre` + `bisacce` | «however this is just a corruption of τραπεζὰκιον» |
| `capolavoro` | stopped at an acronym | an alternative spelling of `caput` |
| `minigolf` | descends from `mini-` + `golf` | *equivalent to*, borrowed whole from English |

Every one was structurally perfect. Each came from a phrasing the parser did
not yet recognise — and **a check built on the parser's own tables cannot find
an error in the parser's tables**, however carefully written. It would read
the source with the same incomplete list and agree with itself.

This is why the hand-written expectations exist. Their value is not that they
hold a truth the code lacks; it is that **they are the only artefact not
derived from the parser's tables**. They are deliberately few, and each one
exercises a decision the parser has to make rather than a word it has to look
up: `cane → canis` would pass with half the parser broken.

---

## Corpus

The universe is `Category:Italian lemmas` on **en.wiktionary.org** — the same
edition the tool reads. Drawing the corpus from the Italian Wiktionary while
validating against the English one would make the coverage figure measure the
overlap between two projects rather than the quality of this one.

Membership is asked, never inferred. Wiktionary already separates lemmas from
inflected forms, so the category answers directly:

```text
129 665   Category:Italian lemmas
468 090   Category:Italian non-lemma forms
```

Acronyms are subtracted by category — `Italian acronyms`, `Italian
initialisms`, `Italian abbreviations` — because they are out of scope: an
acronym does not descend from its expansion.

**The snapshot is immutable.** Rebuilding it would leave the ledger chasing a
universe moving beneath it, and coverage measured against a shifting
denominator says nothing. `build_corpus.py` refuses to overwrite an existing
snapshot without `--force`, and `dataset_hash` is a digest of the lemmas
themselves, so two runs seeing the same category agree and a run seeing a
changed one says so.

---

## Structural invariants

Run on every lemma, with nothing written by hand:

| | check |
| --- | --- |
| I1 | no markup surviving in a lemma — `<…>`, `[[…]]`, `::` |
| I2 | no unsplit language prefix, e.g. `pgd:𐨭𐨐𐨪` |
| I3 | no link contradicting `impossible_order` |
| I4 | no form repeated along one branch |
| I5 | no linguistic terminal on an empty form |
| I6 | hypotheses well-formed and non-empty |

---

## Expectations

Each case in the seed states what its tree must and must not contain:

```json
{
  "word": "dipelare",
  "language": "it",
  "category": "uncertain-origin",
  "expected": {
    "must_include_hypotheses": ["dēpilō::la"],
    "must_not_include_forms":  ["dēpilō::la"]
  }
}
```

Both halves are needed, and the pair is the point: the first says the
conjecture was recorded, the second that it was not drawn as an ancestor. With
only the first, the expectation is satisfied by a tree that made exactly the
mistake the case exists to catch.

| field | meaning |
| --- | --- |
| `must_include_relations` | relation names present in the tree |
| `must_include_terminals` | terminal names present in the tree |
| `must_include_forms` | `lemma` or `lemma::language`, drawn in the tree |
| `must_include_hypotheses` | recorded as a conjecture, not as a link |
| `must_include_chains` | a lineage appearing as a contiguous sub-path |
| `must_not_include_forms` | absent from the tree |
| `must_not_include_relations` | absent from the tree |
| `must_not_include_terminals` | absent from the tree |
| `must_not_include` | any of the three, matched loosely |

Names are matched by **equality**, never by substring, and both spellings of
each name work: `uncertain_origin` and `uncertain origin` mean the same thing,
while `borrowed` means `borrowed` and is not satisfied by `unadapted
borrowing`.

**Negative cases matter as much as positive ones.** `brindare` says «probably
introduced by mercenaries» and its chain must survive intact: a parser that
demotes too eagerly passes every test that only asks for things to be present.

---

## Failure classes

| class | meaning |
| --- | --- |
| `FIDELITY_INVARIANT_VIOLATION` | a structural invariant broke: a code defect |
| `EXPECTED_FACT_MISSING` | the tree is sound but does not match an expectation |
| `SOURCE_LIMIT` | the **starting** entry yielded nothing — no page, no section, no etymology |
| `TRANSIENT_NETWORK_ERROR` | connectivity or rate limiting; does not penalise priority |
| `EXECUTION_EXCEPTION` | an unexpected runtime error |
| `PARSER_REGRESSION` | a diagnostic: the page hash is unchanged and the case now fails |
| `SOURCE_DRIFT` | a diagnostic: the page hash changed since the last audit |

`SOURCE_LIMIT` applies only when the starting entry gave nothing at all. A
limit reached higher up the tree means the walk did read something and got
somewhere, so a failing expectation is the informative answer — classifying on
any source limit anywhere buried the real reason under a statement that was
true and useless.

---

## Where failures show up

Four places, in descending order of how likely anyone is to look:

| | |
| --- | --- |
| **the run turns red** | only for defects attributable to this code |
| **Step Summary** | a table of the batch's failures, on the run's page |
| **artifact** | the full report as JSON, kept 30 days |
| **the ledger** | committed to the validation branch, so the history persists |

The first line is what matters. GitHub notifies failed runs and nothing else,
so a batch that always exits zero is an audit nobody reads — which is what
this was until the question «and where will I see the failures?» was asked.

**What turns the run red** is narrow on purpose: a broken structural
invariant, an unexpected exception, or an expectation that fails while the
page's hash is unchanged — meaning the source said the same thing yesterday
and we read it differently.

**What does not**: an entry Wiktionary has no etymology for (a third of them),
an entry that changed upstream, a network error. Those are true, recorded, and
visible in the summary — but they are not alarms, and a red light that fires
on them would teach whoever watches it to stop looking. A red that is always
on is worth less than no red at all.

---

## What gets audited, and how often

The corpus is not flat. Measured on 600 random lemmas:

| | share | entries | what a misreading produces |
| --- | ---: | ---: | --- |
| no Etymology section | 38.7% | ~49 100 | nothing to read |
| templates only | 56.3% | ~71 600 | structural corruption, never a wrong reading |
| **interpretive load** | **5.0%** | **~6 400** | **the parser judges, and can judge wrong** |

Every defect this project has ever found came from that 5%: entries whose
prose asks whether a form is an ancestor, a conjecture, a synchronic remark or
a comparison. The other 120 000 are not easy — they are entries where no
alternative reading exists.

Six classes mark that load, and they are not equal:

| | class | a misreading here |
| --- | --- | --- |
| grave | `conditioning` `alternation` `synchrony` | **invents an ancestor** the source never claimed |
| venial | `non_ancestor` `mediation` `attribution` | **loses a link** the source stated |

The queue orders by that, and an entry carrying more than one class comes
first: the parser takes more than one decision there.

**How the classification is made.** Six `insource:` searches at corpus-build
time — 86 requests instead of 127 101 page downloads. It over-estimates,
because a search matches anywhere on a page and a page holds every language
that spells the word that way: measured against the Italian section on 50
entries, **56% precision and 100% recall**. Over-estimating is the survivable
half — it costs requests, where under-estimating would cost unseen defects —
so the estimate only sets precedence, and the harness replaces it with the
truth when it audits the entry.

**How much per night.** 300 cases, divided by what a misreading could do:

```text
215/day   interpretive load   6400 ÷ 30 days — a full sweep in a month, after
                              which the re-check period sustains itself exactly
 30/day   templates only      a SENTINEL, not coverage: a structural regression
                              there is a property of the parser, not of the
                              entry, so any sample finds it. Covering all 71600
                              would buy with 71600 checks what 30 establish
 55/day   no etymology        slow discovery. The event worth catching is the
                              source filling one in — per-entry, so it wants
                              coverage, but it guards nothing
```

The shares hold at any batch size, and a population that runs dry yields its
turns rather than shortening the batch. Within a population the entry
categories are spread, so a night is not spent on one kind of word.

**How often.** The re-check period adapts per entry rather than being fixed,
because the population is bimodal: 17.6% of interpretive-load entries changed
within 18 days against 7.5% of the rest, yet their median age is 268 days
against 118. Some are actively argued over; the rest have not moved in years.

```text
start at 30 days
page unchanged  →  double, capped at 180
page changed    →  back to 14
first audit     →  no change: never watched is not the same as stable
```

A re-check whose page and parser are both unchanged costs one request instead
of a walk. The parser side is a digest of the reading modules, not the release
version: a table can be widened a dozen times between two releases, and a
skipped walk must never sleep through the regression it exists to catch.

---

## Queue lifecycle

> **This section described three behaviours that have never happened and
> cannot happen.** They are recorded here as they were, struck through, because
> a document that quietly drops a false claim teaches nobody why it was false.
> Measured on the real ledger after 19 nightly runs: 0 archived items, 0
> `next_due_at` timestamps, every audited lemma at `attempts: 1`.

* ~~**Archiving** — three consecutive passes move a lemma to `archived`~~
* ~~**Re-audit** — archived entries carry `next_due_at` (30 days) and return
  to `pending`, so upstream changes are noticed~~
* ~~**Daily quotas** — 15% re-checks of expired archives~~

**Why they cannot happen.** A lemma that passes is written `status: "pass"`,
and no selector admits that status: the four pools ask for
`{priority, pending}`, `retry`, `manual_review` and `archived`-and-due, and the
top-up explicitly excludes `pass`. So a passed lemma is never selected again,
`consecutive_passes` can only ever hold 0 or 1, the threshold of 3 is
unreachable, and everything downstream of it — `archived`, `next_due_at`, the
re-check pool and its quota — is dead by construction rather than by
circumstance. Simulating 40 days over the real selector produces zero archived
items.

**What this costs.** The audit has no mechanism to notice that Wiktionary has
changed on a lemma it has already seen — which is the one thing a *continuous*
validation exists to do. The `source_hash` recorded per item is compared to
nothing, because nothing is ever re-visited.

**What still works.**

* **Daily quotas** — 40% new, 30% retries, 15% manual review. The three live
  pools are honoured; the fourth is always empty and its share is absorbed by
  the others, so a batch is never short.
* **Source hash** — recorded per audited item. The comparison that would use
  it is currently unreachable, see above.
* **Network isolation** — transient errors keep an item on `retry` without
  penalising its priority. `retry` and `manual_review` are *not* absorbing:
  those items are re-selected indefinitely, so a failing lemma is retried
  every night. Only success is terminal.
* **Category invalidation** — `--invalidate-category <name>` after a parser
  fix. This is today the **only** way to make the audit look at a lemma twice.

---

## Commands

Build the snapshot. Done once; `--force` is needed to replace it.

```bash
python tools/build_corpus.py --source api --progress \
  --output tools/validation/corpus_catalog.json
```

Run a batch.

```bash
python tools/validate_wiktionary.py \
  --seed-file tools/validation/corpus_catalog.json \
  --queue-file tools/validation/coverage-ledger.json \
  --batch-size 20 \
  --output-dir artifacts/wiktionary-validation
```

Run against frozen fixtures, without the network.

```bash
python tools/validate_wiktionary.py \
  --offline-fixtures tests/fixtures/entries.json \
  --seed-file tools/validation/sample_words.json \
  --batch-size 10 --output-dir artifacts/wiktionary-validation
```

Force a category back into the queue after a parser fix.

```bash
python tools/validate_wiktionary.py --invalidate-category compound
```

---

## Automation

`.github/workflows/wiktionary-daily-audit.yml` runs at 03:00 UTC daily.

The file lives on the **default branch** because GitHub reads `on: schedule`
only from there; a scheduled workflow committed elsewhere never fires. It
checks out the **validation branch**, runs against that branch's code, and
pushes the ledger back to it, so the released branch takes no automated
commits.

The offline suite runs before the batch: a run against broken code would
report source drift for what is plainly a regression.

---

## Testing the harness

```bash
pytest tests/test_validation_harness.py -v
```

These tests are offline, like the rest of the suite. They cover the ledger,
the batch selection, the invariants and the expectation matching — not the
network path, which is why a wrongly built source object once went unnoticed
until the first live run.
