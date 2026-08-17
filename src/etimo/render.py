"""Rendering the etymological tree in the terminal.

Three views on the same result: the tree, which shows the forks; the chain,
which follows the main line only; and JSON, for piping the output elsewhere.

The tree alternates two kinds of line — the relation ("inherited from Latin")
and the form ("focus «hearth»") — because the manner of the passage matters as
much as the form reached: a borrowing and an inheritance tell different
stories, and flattening both into an arrow would make them indistinguishable.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

from .models import DefinitionStatement, Node, Sense, Terminal
from .walker import Result


class Style:
    """ANSI colours, switchable off as a whole.

    Honours the NO_COLOR convention and disables itself when the output is not
    a terminal, so pipes receive clean text.

    The palette carries one distinction beyond decoration: **what the source
    says is coloured differently from what etimo says about it**. Glosses,
    quoted etymologies and attributions are Wiktionary speaking, in italics;
    relations, terminals and notes are the tool speaking. Both are in English,
    so without the distinction a reader has no way of telling a citation from a
    comment — and telling them apart is the whole premise of the project.

    Where colour is unavailable the distinction survives in punctuation:
    everything quoted from the source is wrapped in «guillemets».
    """

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = (
            enabled
            and sys.stdout.isatty()
            and os.environ.get("NO_COLOR") is None
            and os.environ.get("TERM") != "dumb"
        )

    def _paint(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def lemma(self, text: str) -> str:
        return self._paint(text, "1")

    def language(self, text: str) -> str:
        return self._paint(text, "2;37")

    def gloss(self, text: str) -> str:
        return self._paint(text, "3;36")

    def quoted(self, text: str) -> str:
        """Words taken from the source, as opposed to our own."""
        return self._paint(text, "3;36")

    def relation(self, text: str) -> str:
        return self._paint(text, "35")

    def terminal(self, text: str) -> str:
        return self._paint(text, "1;33")

    def limit(self, text: str) -> str:
        return self._paint(text, "1;31")

    def dim(self, text: str) -> str:
        return self._paint(text, "2")

    def structure(self, text: str) -> str:
        return self._paint(text, "2")


def _render_form(node: Node, style: Style) -> str:
    """The line of a form: lemma, language code, gloss."""
    form = node.form

    if not form.lemma:
        text = style.dim("(form not specified)")
    else:
        text = style.lemma(form.lemma)

    if form.variants:
        # The entry gave more than one spelling; showing only the one we walked
        # would hide that the source offered both.
        text += style.dim(", ") + style.dim(", ".join(form.variants))

    text += " " + style.language(f"({form.language})")

    if form.transliteration:
        text += " " + style.dim(f"[{form.transliteration}]")
    if form.gloss:
        text += " " + style.gloss(f"«{form.gloss}»")

    return text


def _render_terminal(terminal: Terminal, style: Style) -> str:
    """The line closing a branch, distinguishing the two kinds of ending."""
    text = f"{terminal.symbol} {terminal.label}"
    return style.terminal(text) if terminal.is_linguistic else style.limit(text)


def _group_by_relation(children: list[Node]) -> list[tuple[str | None, list[Node]]]:
    """Merge children that share the same relation line.

    A compound yields several children bound by the same relationship:
    repeating "formed with affixes from" above each would be noise.
    """
    groups: list[tuple[str | None, list[Node]]] = []

    for child in children:
        label = None if child.relation is None else child.relation.describe(
            child.form.language
        )
        if groups and groups[-1][0] == label:
            groups[-1][1].append(child)
        else:
            groups.append((label, [child]))

    return groups


def _connectors(index: int, total: int, prefix: str) -> tuple[str, str]:
    """Prefix of the head line and prefix of the lines depending on it."""
    last = index == total - 1
    return prefix + ("└─ " if last else "├─ "), prefix + ("   " if last else "│  ")


def _children_lines(children: list[Node], prefix: str, style: Style) -> list[str]:
    """The forms of a group of children, each with its own subtree."""
    lines: list[str] = []
    for index, child in enumerate(children):
        head, body = _connectors(index, len(children), prefix)
        lines.append(head + _render_form(child, style))
        lines.extend(_subtree_lines(child, body, style))
    return lines


def _subtree_lines(node: Node, prefix: str, style: Style) -> list[str]:
    """Everything below a node's line: note, branches, terminal."""
    lines: list[str] = []

    if node.note:
        lines.append(prefix + style.dim(f"· {node.note}"))

    # Conjectures attached to a node that also has children belong here, right
    # under the form they qualify — an entry can state a chain *and* offer
    # candidates for one of its stages, and printing them after the whole
    # subtree would leave them looking like nobody's.
    if node.hypotheses and node.terminal is None:
        lines.extend(_hypotheses_lines(node, prefix, style))

    groups = _group_by_relation(node.children)
    total = len(groups) + (1 if node.terminal is not None else 0)

    for index, (label, children) in enumerate(groups):
        head, body = _connectors(index, total, prefix)
        if label is None:
            # No relation declared: the children move up one level.
            lines.extend(_children_lines(children, prefix, style))
        else:
            lines.append(head + style.relation(label))
            if any(child.from_definition for child in children):
                # Under the relation, not under the child: the caveat is about
                # where we read this link, not about the word it reaches.
                lines.append(body + style.dim("· as stated in the definition"))
            lines.extend(_children_lines(children, body, style))

    if node.terminal is not None:
        head, body = _connectors(total - 1, total, prefix)
        lines.append(head + _render_terminal(node.terminal, style))
        if node.source_text:
            lines.append(
                body
                + style.dim("the entry says: ")
                + style.quoted(f"«{node.source_text}»")
            )
        lines.extend(_hypotheses_lines(node, body, style))
    return lines


def _hypotheses_lines(node: Node, prefix: str, style: Style) -> list[str]:
    """Conjectural derivations, below the terminal and visibly distinct."""
    lines: list[str] = []
    for hypothesis in node.hypotheses:
        text = style.dim(
            f"perhaps {hypothesis.form.lemma} ({hypothesis.form.language})"
        )
        if hypothesis.form.gloss:
            text += " " + style.quoted(f"«{hypothesis.form.gloss}»")
        if hypothesis.attribution:
            # Quoted even without colour: the guillemets are what tells the
            # entry's sentence from our summary of it on a monochrome terminal.
            text += style.dim(" — ") + style.quoted(f"«{hypothesis.attribution}»")
        lines.append(prefix + text)
    return lines


def senses(word: str, options: list[Sense], style: Style | None = None) -> str:
    """The homographs a spelling covers, numbered as `--sense` expects them.

    Shows the meaning and the first ancestor of each, because those are what a
    reader can recognise. "The third etymology" is not something anyone knows
    in advance.
    """
    style = style or Style()
    how_many = _NUMBER.get(len(options), str(len(options)))
    lines = [f"«{style.lemma(word)}» is {how_many} different words here. Which one?", ""]

    width = max((len(o.part_of_speech) for o in options), default=0)
    for option in options:
        summary = option.definition or style.dim("no definition given")
        number = style.lemma(str(option.index))
        line = f"  {number}  {option.part_of_speech:<{width}}  {summary}"
        if option.ancestor is not None:
            line += "  " + style.relation(
                f"< {option.ancestor.lemma} ({option.ancestor.language})"
            )
        lines.append(line)
    return "\n".join(lines)


_NUMBER = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


def pointer_choices(
    word: str, options: list[DefinitionStatement], style: Style | None = None
) -> str:
    """The lemmas a form points at, named rather than numbered.

    Unlike homographs, which the source numbers and nothing else, these targets
    have names — so `--as poco` asks for one directly, and nobody has to learn
    an order first.
    """
    style = style or Style()
    how_many = _NUMBER.get(len(options), str(len(options)))
    lines = [
        f"«{style.lemma(word)}» is a form of {how_many} different words. Which one?",
        "",
    ]

    width = max((len(o.part_of_speech) for o in options), default=0)
    for option in options:
        target = option.forms[0].lemma
        summary = option.gloss or style.dim("no gloss given")
        lines.append(
            f"  {style.lemma(target):<{width + 12}} "
            f"{style.dim(option.part_of_speech):<{width}}  {summary}"
        )
    return "\n".join(lines)


def _resolution_lines(result: Result, style: Style) -> list[str]:
    """The header shown when an inflected form was resolved to its lemma.

    Kept outside the tree on purpose. `andato` does not descend from `andare`,
    it is the same word inflected; drawn as a branch it would read as the first
    etymological step, which is precisely what it is not.
    """
    if not result.resolved or result.asked_for is None:
        return []

    asked = result.asked_for
    return [
        f"{style.lemma(asked.lemma)} {style.language(f'({asked.language})')} "
        f"{style.dim('—')} {style.relation(result.resolution)}",
        style.dim("the history below is the lemma's"),
        "",
    ]


def tree(result: Result, style: Style | None = None) -> str:
    """Full tree view, with every fork."""
    style = style or Style()
    lines = _resolution_lines(result, style)
    lines.append(_render_form(result.start, style))
    lines.extend(_subtree_lines(result.start, "", style))
    lines.append("")
    lines.append(_summary(result, style))
    return "\n".join(lines)


def chain(result: Result, style: Style | None = None) -> str:
    """Linear view: the main branch only, one link per line."""
    style = style or Style()
    path = result.start.main_chain()
    lines = _resolution_lines(result, style)
    lines.append(_render_form(path[0], style))

    for node in path[1:]:
        manner = node.relation.describe(node.form.language) if node.relation else ""
        lines.append(
            f"  {style.structure('←')} {_render_form(node, style)}  {style.dim(manner)}"
        )

    last = path[-1]
    if last.terminal is not None:
        lines.append(f"  {style.structure('←')} {_render_terminal(last.terminal, style)}")

    lines.append("")
    lines.append(_summary(result, style))
    return "\n".join(lines)


def _links_skipping_stages(node: Node) -> int:
    """How many links in the tree may hide intermediate stages."""
    here = 1 if node.skips_stages else 0
    return here + sum(_links_skipping_stages(child) for child in node.children)


def _summary(result: Result, style: Style) -> str:
    """The closing line: how many jumps and how they ended."""
    steps = result.steps
    steps_part = f"{steps} step" if steps == 1 else f"{steps} steps"

    terminals = [n.terminal for n in result.start.terminals() if n.terminal]
    tally = Counter(t.label for t in terminals)

    if not tally:
        terminals_part = "no terminal reached"
    elif len(tally) == 1 and sum(tally.values()) == 1:
        terminals_part = f"terminal: {next(iter(tally))}"
    else:
        detail = ", ".join(f"{n}× {label}" for label, n in tally.most_common())
        terminals_part = f"{sum(tally.values())} terminals: {detail}"

    parts = [steps_part]

    # Counted over the whole tree and stated as its own figure rather than as
    # a share of the steps: the steps are the longest branch, so on a forked
    # tree "N of which" would compare two different things.
    skipping = _links_skipping_stages(result.start)
    if skipping:
        parts.append(
            f"{skipping} link may skip stages"
            if skipping == 1
            else f"{skipping} links may skip stages"
        )

    parts.append(terminals_part)
    if result.available_senses > 1:
        parts.append(f"etymology {result.chosen_sense} of {result.available_senses}")

    if result.cache_hits:
        parts.append(
            f"{result.requests} requests + {result.cache_hits} cached "
            f"in {result.duration:.1f}s"
        )
    else:
        parts.append(f"{result.requests} requests in {result.duration:.1f}s")

    return style.dim(" · ".join(parts))


def _node_json(node: Node) -> dict:
    """Serialise a node, preserving the fact/conjecture distinction."""
    data: dict = {
        "lemma": node.form.lemma,
        "language": node.form.language,
        "language_name": node.form.language_name,
        "reconstructed": node.form.reconstructed,
    }
    if node.form.gloss:
        data["gloss"] = node.form.gloss
    if node.form.transliteration:
        data["transliteration"] = node.form.transliteration
    if node.form.variants:
        data["variants"] = list(node.form.variants)
    if node.relation is not None:
        data["relation"] = node.relation.name.lower()
        # False when the source only claims an ultimate origin, leaving open
        # what stood between this form and its parent. A consumer counting
        # links needs to know which ones it can count.
        data["contiguous"] = node.relation.implies_contiguity
    if node.note:
        data["note"] = node.note
    if node.source_text:
        data["source_text"] = node.source_text
    if node.from_definition:
        # A separate field, not a phrase inside the note: a program filtering
        # for claims read synchronically must be able to find them.
        data["from_definition"] = True
    if node.terminal is not None:
        data["terminal"] = {
            "type": node.terminal.name.lower(),
            "label": node.terminal.label,
            "linguistic": node.terminal.is_linguistic,
        }
    if node.hypotheses:
        data["hypotheses"] = [
            {
                "lemma": h.form.lemma,
                "language": h.form.language,
                "attribution": h.attribution,
            }
            for h in node.hypotheses
        ]
    if node.children:
        data["ancestors"] = [_node_json(child) for child in node.children]
    return data


def as_json(
    result: Result,
    indent: bool = True,
    options: list[Sense] | None = None,
) -> str:
    """The whole result as JSON, with the metadata of the query.

    When the spelling covers several unrelated words, they are all listed and
    `ambiguous` is set. A program reading this can tell that a choice was made
    on its behalf — and which alternatives it had — instead of receiving one
    answer as though it were the only one.
    """
    data: dict = {
        "word": result.start.form.lemma,
        "language": result.start.form.language,
        "steps": result.steps,
        "available_etymologies": result.available_senses,
        "chosen_etymology": result.chosen_sense,
        "network_requests": result.requests,
        "cache_hits": result.cache_hits,
    }
    if result.ambiguous_pointer:
        data["ambiguous_pointer"] = True
        data["points_at"] = [
            {
                "lemma": option.forms[0].lemma,
                "part_of_speech": option.part_of_speech,
                "gloss": option.gloss,
                "relation": option.wording,
                "chosen": option.forms[0].lemma == result.start.form.lemma,
            }
            for option in result.pointer_options
        ]
    if result.resolved and result.asked_for is not None:
        # Not part of the tree: a consumer must be able to tell that the word
        # it asked about is a form of the one whose history follows.
        data["asked_for"] = {
            "lemma": result.asked_for.lemma,
            "language": result.asked_for.language,
            "relation_to_lemma": result.resolution,
        }
    if options is not None:
        data["ambiguous"] = len(options) > 1
        data["senses"] = [
            {
                "index": option.index,
                "part_of_speech": option.part_of_speech,
                "definition": option.definition,
                "chosen": option.index == result.chosen_sense,
                **(
                    {"ancestor": {"lemma": option.ancestor.lemma,
                                  "language": option.ancestor.language}}
                    if option.ancestor is not None
                    else {}
                ),
            }
            for option in options
        ]
    data["tree"] = _node_json(result.start)
    return json.dumps(data, ensure_ascii=False, indent=2 if indent else None)
