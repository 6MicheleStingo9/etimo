<!-- Development happens on prog_validation/wikitionary-daily-audit.
     main holds the released tool and takes no direct commits. -->

Closes #

## What changes, and why

## How it was verified

<!-- Tests alone are not an answer here. Two things this project asks for: -->

- [ ] **The check can fail.** If this adds or changes a check, break the code on
      purpose and confirm it goes red. Half the checks written here could not
      fail at first draft.
- [ ] **Measurements report what they measured.** A figure without its
      denominator is a statement about a slice dressed as a statement about the
      corpus.

## What this does *not* establish

<!-- Say plainly what remains unverified. `etimo` never presents a limit of the
     tool as a fact about the language, and neither should a pull request. -->

---

- [ ] `pytest -q` green (offline; a red test means the code changed, never that Wiktionary did)
- [ ] `ruff check src tests tools` and `mypy src/etimo` clean
- [ ] If the README's examples changed: `python tools/check_readme_examples.py`
