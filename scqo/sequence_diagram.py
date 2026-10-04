"""Sequence diagrams - the neutral, schematic picture of an experiment's pulses.

An experiment's real sequence exists only inside each driver's ``probe()`` (a
QUA program, a Qblox ``Schedule``). This module holds the vendor-free
DECLARATION of that sequence, which an experiment returns from
``Experiment.sequence_diagram(params)``, and the one renderer that turns it
into an SVG for the experiment's document (``scqo/experiments/_docs/<name>/``).

A SCHEMATIC, NEVER AN EXECUTABLE SEQUENCE. Nothing here is to scale and nothing
here is played: a column is one time step, its width follows its labels, and a
swept block is drawn in the accent colour with the name of the sweep AXIS it
varies with. It is the picture the *Backend parity* rule (CLAUDE.md) talks
about - the one sequence both probes must realize - written down once.

LANES ARE ROLES, NOT DEVICE NAMES: ``q.xy`` / ``q.z`` / ``q.ro`` for a qubit,
``control.xy`` / ``coupler.z`` for a pair. A diagram is drawn from Parameters
alone and names no chip.

THE OUTPUT IS BYTE-STABLE. ``render_svg`` uses the standard library only, with
fixed geometry and fixed number formatting, so the committed ``sequence.svg``
can be compared byte for byte with a fresh render
(``scripts/update_docs.py --check``). That is why this is not matplotlib: its
SVG moves with the library version.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from xml.sax.saxutils import escape, quoteattr

#: what a block looks like. ``gate`` = a shaped pulse (label above it);
#: ``square`` / ``flattop`` = a pulse drawn by its envelope (label inside);
#: ``tone`` = a long low-amplitude tone; ``acquire`` = a readout pulse with its
#: acquisition; ``wait`` = an idle (a double arrow, no pulse); ``offset`` = a
#: DC level held for the step.
SHAPES = ("gate", "square", "flattop", "tone", "acquire", "wait", "offset")

#: a footnote is drawn on ONE line under the lanes and widens the figure to fit
MAX_NOTE_CHARS = 96


@dataclass(frozen=True)
class Block:
    """One thing on one lane during one step."""

    #: the lane key it is drawn on (a key of ``SequenceDiagram.lanes``)
    lane: str
    #: the text drawn with it: an operation name ("x90", "readout") or a role
    label: str
    shape: str = "gate"
    #: the sweep AXIS this block varies with - a ``Contract.sweeps`` name, or a
    #: tuple of them when one pulse carries two (a readout swept in frequency
    #: AND power)
    swept: str | tuple[str, ...] | None = None
    #: a footnote, numbered and printed under the lanes
    note: str | None = None

    def __post_init__(self) -> None:
        if self.shape not in SHAPES:
            raise ValueError(
                f"unknown block shape {self.shape!r}; expected one of {SHAPES}")
        if not self.label:
            raise ValueError("a block needs a label")
        if self.note and len(self.note) > MAX_NOTE_CHARS:
            raise ValueError(
                f"note on block {self.label!r} is {len(self.note)} characters; keep "
                f"a footnote within {MAX_NOTE_CHARS} - it is drawn on one line, and "
                f"the explanation belongs in the document's text")


    @property
    def axes(self) -> tuple[str, ...]:
        """The swept axes as a tuple, empty when the block is fixed."""
        if self.swept is None:
            return ()
        return (self.swept,) if isinstance(self.swept, str) else tuple(self.swept)


@dataclass(frozen=True)
class Repeat:
    """A bracket over consecutive steps that are played several times."""

    #: first and last step index it spans, both inclusive
    first: int
    last: int
    label: str
    swept: str | None = None


class SequenceDiagram:
    """An ordered list of steps over named lanes, plus repeat brackets.

    ``lanes`` maps a lane key to the label drawn beside it, top to bottom.
    Every ``step()`` is one time column; the blocks passed to it are
    simultaneous, at most one per lane.
    """

    def __init__(self, lanes: dict[str, str]) -> None:
        if not lanes:
            raise ValueError("a sequence diagram needs at least one lane")
        self.lanes: dict[str, str] = dict(lanes)
        self.steps: list[tuple[Block, ...]] = []
        #: in the order the brackets CLOSED, so an inner one precedes the
        #: bracket around it (``repeat_levels`` reads that order)
        self.repeats: list[Repeat] = []

    def step(self, *blocks: Block) -> None:
        """Append one time step holding ``blocks``, which play together."""
        if not blocks:
            raise ValueError("a step needs at least one block")
        seen: set[str] = set()
        for block in blocks:
            if block.lane not in self.lanes:
                raise ValueError(
                    f"block {block.label!r} names lane {block.lane!r}, which this "
                    f"diagram does not have; lanes are {list(self.lanes)}")
            if block.lane in seen:
                raise ValueError(
                    f"two blocks on lane {block.lane!r} in one step; a step holds "
                    f"at most one block per lane")
            seen.add(block.lane)
        self.steps.append(tuple(blocks))

    @contextmanager
    def repeat(self, label: str, *, swept: str | None = None) -> Iterator[None]:
        """Bracket the steps added inside the ``with`` body as repeated.

        ``label`` is the count as the reader should see it ("x N"); ``swept``
        names the sweep axis when the COUNT is what the experiment sweeps.
        Brackets nest - a block of shots holding a repeated pair - and the
        outer one is drawn around the inner.
        """
        first = len(self.steps)
        yield
        if len(self.steps) == first:
            raise ValueError(f"repeat {label!r} brackets no step")
        self.repeats.append(Repeat(first, len(self.steps) - 1, label, swept))

    def repeat_levels(self) -> list[int]:
        """How many bracket layers each of ``repeats`` encloses: 0 for an
        innermost bracket, one more than its deepest inner bracket otherwise."""
        levels: list[int] = []
        for k, rep in enumerate(self.repeats):
            inner = [levels[j] for j, other in enumerate(self.repeats[:k])
                     if rep.first <= other.first and other.last <= rep.last]
            levels.append(1 + max(inner) if inner else 0)
        return levels

    def swept_axes(self) -> set[str]:
        """Every sweep axis some block or repeat bracket is marked with."""
        axes = {axis for step in self.steps for block in step for axis in block.axes}
        axes |= {rep.swept for rep in self.repeats if rep.swept}
        return axes

    def notes(self) -> list[str]:
        """The footnotes, de-duplicated, in the order they first appear."""
        out: list[str] = []
        for step in self.steps:
            for block in step:
                if block.note and block.note not in out:
                    out.append(block.note)
        return out


# ---------------------------------------------------------------- rendering
# Fixed geometry, in px. There are no font metrics to ask, so text width is
# estimated from the glyph count; the widths only have to be generous enough
# that a label never leaves its column.
_FONT = 13.0
_SMALL = 11.0
_GLYPH = 0.62
_PAD = 14.0
_COL_MIN = 68.0
_INSET = 7.0
_PITCH = 84.0
_BASE = 52.0          # baseline, measured from the top of its lane band
_SHAPE_H = 26.0
_GATE_W = 44.0
_BRACKET_BAND = 32.0
_BRACKET_STEP = 22.0   # what each further bracket layer adds above the lanes
_NOTE_LINE = 17.0
#: running prose is narrower than the per-glyph bound the columns are sized
#: with (which has to hold for a label of capitals and digits)
_NOTE_FIT = 0.86

_INK = "#1f2328"
_MUTED = "#8c959f"
_FILL = "#e3e8ef"
_PAPER = "#ffffff"
_BORDER = "#d0d7de"
_ACCENT = "#bc4c00"
_ACCENT_FILL = "#ffe8d6"

_SANS = "Helvetica, Arial, sans-serif"
_MONO = "Consolas, Menlo, monospace"


def _n(value: float) -> str:
    """A coordinate as text: one decimal, no trailing zero, never '-0'."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _text_w(text: str, size: float) -> float:
    return len(text) * size * _GLYPH


def _text(x: float, y: float, text: str, *, size: float = _FONT, fill: str = _INK,
          anchor: str = "middle", family: str = _SANS, sup: str = "") -> str:
    tail = (f'<tspan font-size="{_n(size * 0.72)}" dy="{_n(-size * 0.38)}">'
            f"{escape(sup)}</tspan>") if sup else ""
    return (f'<text x="{_n(x)}" y="{_n(y)}" font-family={quoteattr(family)} '
            f'font-size="{_n(size)}" fill="{fill}" text-anchor="{anchor}">'
            f"{escape(text)}{tail}</text>")


def _arrow(x0: float, x1: float, y: float, colour: str) -> list[str]:
    """A horizontal double-headed arrow from x0 to x1."""
    head = 5.0
    return [
        f'<path d="M{_n(x0 + head)},{_n(y)} H{_n(x1 - head)}" fill="none" '
        f'stroke="{colour}" stroke-width="1.2"/>',
        f'<path d="M{_n(x0)},{_n(y)} l{_n(head)},{_n(-3.5)} v7 Z" fill="{colour}"/>',
        f'<path d="M{_n(x1)},{_n(y)} l{_n(-head)},{_n(-3.5)} v7 Z" fill="{colour}"/>',
    ]


def _block_svg(block: Block, x0: float, x1: float, base: float,
               marker: str) -> list[str]:
    """One block inside the column spanning x0..x1 on the lane at ``base``."""
    stroke = _ACCENT if block.swept else _INK
    fill = _ACCENT_FILL if block.swept else _FILL
    left, right = x0 + _INSET, x1 - _INSET
    mid = (x0 + x1) / 2
    top = base - _SHAPE_H
    inside_y = base - _SHAPE_H / 2 + _FONT * 0.35
    out: list[str] = []
    label_y = inside_y

    if block.shape == "gate":
        g0, g1 = mid - _GATE_W / 2, mid + _GATE_W / 2
        out.append(
            f'<path d="M{_n(g0)},{_n(base)} '
            f'C{_n(g0 + 0.34 * _GATE_W)},{_n(base)} {_n(mid - 0.2 * _GATE_W)},{_n(top)} '
            f'{_n(mid)},{_n(top)} '
            f'C{_n(mid + 0.2 * _GATE_W)},{_n(top)} {_n(g1 - 0.34 * _GATE_W)},{_n(base)} '
            f'{_n(g1)},{_n(base)} Z" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
        label_y = top - 6
    elif block.shape == "square":
        out.append(
            f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(right - left)}" '
            f'height="{_n(_SHAPE_H)}" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    elif block.shape == "flattop":
        ramp = 9.0
        out.append(
            f'<path d="M{_n(left)},{_n(base)} L{_n(left + ramp)},{_n(top)} '
            f'H{_n(right - ramp)} L{_n(right)},{_n(base)} Z" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.4"/>')
    elif block.shape == "tone":
        low = base - _SHAPE_H * 0.62
        out.append(
            f'<rect x="{_n(left)}" y="{_n(low)}" width="{_n(right - left)}" '
            f'height="{_n(base - low)}" fill="{fill}" fill-opacity="0.55" '
            f'stroke="{stroke}" stroke-width="1.2"/>')
        label_y = low - 6
    elif block.shape == "acquire":
        out.append(
            f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(right - left)}" '
            f'height="{_n(_SHAPE_H)}" fill="{_PAPER}" stroke="{stroke}" '
            f'stroke-width="1.4" stroke-dasharray="5 3"/>')
    elif block.shape == "wait":
        out += _arrow(left, right, base - 10, stroke)
        label_y = base - 17
    else:  # offset
        low = base - _SHAPE_H * 0.45
        out.append(
            f'<rect x="{_n(left)}" y="{_n(low)}" width="{_n(right - left)}" '
            f'height="{_n(base - low)}" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        label_y = low - 6

    out.append(_text(mid, label_y, block.label, fill=stroke, sup=marker))
    for row, axis in enumerate(block.axes):
        out.append(_text(mid, base + 15 + row * (_SMALL + 2), axis, size=_SMALL,
                         fill=_ACCENT, family=_MONO))
    return out


def _edge_levels(repeats: list[Repeat], edge: str) -> list[int]:
    """Per bracket, how many inner brackets end on the same ``edge`` (``"first"``
    or ``"last"`` step) stacked inside it - the layers it has to step outside of
    on that side."""
    levels: list[int] = []
    for k, rep in enumerate(repeats):
        inner = [levels[j] for j, other in enumerate(repeats[:k])
                 if rep.first <= other.first and other.last <= rep.last
                 and getattr(other, edge) == getattr(rep, edge)]
        levels.append(1 + max(inner) if inner else 0)
    return levels


def render_svg(diagram: SequenceDiagram) -> str:
    """The diagram as SVG text. Deterministic: the same diagram renders to the
    same bytes, with no timestamp, no id and no dependence on a font library."""
    if not diagram.steps:
        raise ValueError("a sequence diagram with no step has nothing to draw")
    notes = diagram.notes()
    marker = {note: str(k + 1) for k, note in enumerate(notes)}
    swept = diagram.swept_axes()

    gutter = max(_text_w(label, _FONT) for label in diagram.lanes.values()) + 16
    widths = []
    for step in diagram.steps:
        need = 0.0
        for block in step:
            label_w = _text_w(block.label, _FONT) + (9 if block.note else 0)
            need = max(need, label_w, *(_text_w(axis, _SMALL) for axis in block.axes))
        widths.append(max(_COL_MIN, need + 2 * _INSET + 10))
    left = _PAD + gutter
    edges = [left]
    for width in widths:
        edges.append(edges[-1] + width)
    # the lanes run on to the end of the longest footnote, so a long note
    # widens the figure instead of leaving it
    footnotes = [f"{marker[note]}  {note}" for note in notes]
    right = max([edges[-1], *(left + _text_w(line, _SMALL) * _NOTE_FIT
                              for line in footnotes)])

    levels = diagram.repeat_levels()
    lanes_top = _PAD + (_BRACKET_BAND + _BRACKET_STEP * max(levels)
                        if diagram.repeats else 0.0)
    base = {key: lanes_top + k * _PITCH + _BASE for k, key in enumerate(diagram.lanes)}
    lanes_bottom = lanes_top + len(diagram.lanes) * _PITCH
    footer = len(notes) + (1 if swept else 0)
    width = right + _PAD
    height = lanes_bottom + (footer * _NOTE_LINE + 6 if footer else 0) + _PAD

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}" '
        f'height="{_n(height)}" viewBox="0 0 {_n(width)} {_n(height)}" role="img">',
        f'<rect x="0.5" y="0.5" width="{_n(width - 1)}" height="{_n(height - 1)}" '
        f'rx="6" fill="{_PAPER}" stroke="{_BORDER}"/>',
    ]

    lefts = _edge_levels(diagram.repeats, "first")
    rights = _edge_levels(diagram.repeats, "last")
    for rep, level, left_level, right_level in zip(
            diagram.repeats, levels, lefts, rights):
        colour = _ACCENT if rep.swept else _MUTED
        # each layer out is one label row taller, so an outer bracket clears the
        # inner one's label; and 4 px wider on a side it SHARES with an inner
        # bracket - only there, so it does not lean into a neighbour for nothing
        x0 = edges[rep.first] + 2 - 4.0 * left_level
        x1 = edges[rep.last + 1] - 2 + 4.0 * right_level
        top = lanes_top + 4 - _BRACKET_STEP * level
        out.append(
            f'<rect x="{_n(x0)}" y="{_n(top)}" width="{_n(x1 - x0)}" '
            f'height="{_n(lanes_bottom - 4 + 3 * level - top)}" rx="4" fill="none" '
            f'stroke="{colour}" stroke-dasharray="4 3"/>')
        text = rep.label + (f"  ({rep.swept})" if rep.swept else "")
        out.append(_text((x0 + x1) / 2, top - 10, text, fill=colour))

    for key, label in diagram.lanes.items():
        y = base[key]
        out.append(_text(left - 10, y - 6, label, anchor="end"))
        out.append(f'<path d="M{_n(left)},{_n(y)} H{_n(right)}" fill="none" '
                   f'stroke="{_MUTED}" stroke-width="1"/>')

    for k, step in enumerate(diagram.steps):
        for block in step:
            out += _block_svg(block, edges[k], edges[k + 1], base[block.lane],
                              marker.get(block.note or "", ""))

    y = lanes_bottom + _NOTE_LINE
    for line in footnotes:
        out.append(_text(left, y, line, size=_SMALL, anchor="start"))
        y += _NOTE_LINE
    if swept:
        out.append(f'<rect x="{_n(left)}" y="{_n(y - 9)}" width="14" height="9" '
                   f'fill="{_ACCENT_FILL}" stroke="{_ACCENT}" stroke-width="1.2"/>')
        out.append(_text(left + 20, y, "swept; the name under it is the sweep axis",
                         size=_SMALL, fill=_ACCENT, anchor="start"))
    out.append("</svg>")
    return "\n".join(out) + "\n"
