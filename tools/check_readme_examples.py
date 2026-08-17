"""Check that every `$ etimo …` block in the README matches real output.

Run from the repository root, with a network connection:

    python tools/check_readme_examples.py

Not part of the test suite, and deliberately so: the suite is offline by
design, so that a red test always means the code changed. This asks the
opposite question — whether the *documentation* still matches what the tool
does — and only the live source can answer it. Both the tool and Wiktionary
move, so a README written once goes stale in two directions at once, and by
the time anyone notices it has been wrong for months.

Two differences are tolerated, and the README states both: the request count
and timing that close a summary line vary between runs, and blocks holding
several invocations drop the summary line altogether.
"""
import pathlib
import re
import shlex
import subprocess
import sys

ETIMO = ".venv/bin/etimo"
text = pathlib.Path("README.md").read_text()

# Summary lines end with counters that vary between runs; the README says so.
TAIL = re.compile(r"\s*·\s*\d+ requests?(?: \+ \d+ cached)? in [\d.]+s\s*$")

blocks = re.findall(r"```text\n(\$ etimo .*?)```", text, re.S)
failures = 0
for block in blocks:
    # A block may hold several invocations separated by blank lines.
    parts = re.split(r"\n(?=\$ etimo )", block.strip())
    for part in parts:
        command, _, expected = part.partition("\n")
        argv = shlex.split(command[2:])[1:]
        # stderr into the same stream, so prompts and tree interleave as they
        # do on a terminal. Capturing them apart reorders the output and
        # reports differences that no reader would ever see.
        got = subprocess.run(
            [ETIMO, *argv, "--no-color"], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=180
        )
        actual = got.stdout.strip()
        actual = "\n".join(TAIL.sub("", line) for line in actual.splitlines())
        # Blocks holding several invocations drop the summary line, as the
        # README states. Nothing else may differ.
        expected_lines = expected.strip().splitlines()
        actual_lines = actual.strip().splitlines()
        if len(parts) > 1:
            actual_lines = [
                line for line in actual_lines
                if not re.match(r"^\d+ steps? ·", line)
            ]
            while actual_lines and not actual_lines[-1].strip():
                actual_lines.pop()
        actual = "\n".join(actual_lines)
        expected = "\n".join(expected_lines)
        if actual.strip() != expected.strip():
            failures += 1
            print(f"✗ {command}")
            exp, act = expected.strip().splitlines(), actual.strip().splitlines()
            for i in range(max(len(exp), len(act))):
                e = exp[i] if i < len(exp) else "(missing)"
                a = act[i] if i < len(act) else "(missing)"
                if e != a:
                    print(f"    README: {e}\n    actual: {a}")
            print()
        else:
            print(f"✓ {command}")
print(f"\n{len(blocks)} blocks · {failures} mismatched")
sys.exit(1 if failures else 0)
