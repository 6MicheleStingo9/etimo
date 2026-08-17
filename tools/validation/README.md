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

## Queue lifecycle

* **Archiving** — three consecutive passes move a lemma to `archived`, freeing
  queue capacity.
* **Daily quotas** — each batch is allocated 40% new lemmas, 30% retries, 15%
  manual review, 15% re-checks of expired archives.
* **Re-audit** — archived entries carry `next_due_at` (30 days) and return to
  `pending` afterwards, so upstream changes are noticed.
* **Source hash** — each audited item records the raw page hash. A failure
  with an unchanged hash is a parser regression; with a changed hash, source
  drift.
* **Network isolation** — transient errors keep an item on `retry` without
  penalising its priority.
* **Category invalidation** — `--invalidate-category <name>` after a parser
  fix.

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
