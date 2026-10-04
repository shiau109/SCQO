"""The sequence-diagram model and its SVG renderer (`scqo/sequence_diagram.py`).

The renderer's one hard promise is that its output is a pure function of the
diagram - `scripts/update_docs.py --check` compares a committed `sequence.svg`
with a fresh render, so anything non-deterministic here turns into a document
that is "stale" on every machine but the one that wrote it.
"""

from __future__ import annotations

import xml.dom.minidom

import pytest

from scqo.sequence_diagram import (
    MAX_NOTE_CHARS,
    Block,
    SequenceDiagram,
    render_svg,
)


def _ramsey_like() -> SequenceDiagram:
    diagram = SequenceDiagram({"drive": "q.xy", "readout": "q.ro"})
    diagram.step(Block("drive", "x90", "gate"))
    diagram.step(Block("drive", "idle", "wait", swept="idle_time_ns"))
    diagram.step(Block("drive", "x90", "gate", note="phase ramp"))
    diagram.step(Block("readout", "readout", "acquire"))
    return diagram


def test_render_is_deterministic_well_formed_ascii():
    first = render_svg(_ramsey_like())
    assert first == render_svg(_ramsey_like())
    assert first.isascii() and first.endswith("</svg>\n")
    xml.dom.minidom.parseString(first)  # well-formed
    assert "\r" not in first


def test_swept_axis_and_notes_reach_the_figure():
    diagram = _ramsey_like()
    assert diagram.swept_axes() == {"idle_time_ns"}
    assert diagram.notes() == ["phase ramp"]
    svg = render_svg(diagram)
    assert "idle_time_ns" in svg          # the axis name is drawn under its block
    assert "1  phase ramp" in svg         # the numbered footnote
    assert "swept; the name under it" in svg  # the legend appears with a sweep


def test_no_legend_without_a_sweep():
    diagram = SequenceDiagram({"drive": "q.xy"})
    diagram.step(Block("drive", "x180", "gate"))
    assert diagram.swept_axes() == set()
    assert "swept;" not in render_svg(diagram)


def test_labels_are_escaped():
    diagram = SequenceDiagram({"drive": "q.xy"})
    diagram.step(Block("drive", "a<b & c", "square"))
    svg = render_svg(diagram)
    assert "a&lt;b &amp; c" in svg
    xml.dom.minidom.parseString(svg)


def test_repeat_bracket_carries_its_swept_count():
    diagram = SequenceDiagram({"drive": "q.xy"})
    with diagram.repeat("x N", swept="num_rounds"):
        diagram.step(Block("drive", "x180", "gate"))
        diagram.step(Block("drive", "idle", "wait"))
    assert [(r.first, r.last) for r in diagram.repeats] == [(0, 1)]
    assert diagram.swept_axes() == {"num_rounds"}
    assert "x N  (num_rounds)" in render_svg(diagram)


def test_every_shape_renders():
    diagram = SequenceDiagram({"a": "lane"})
    for shape in ("gate", "square", "flattop", "tone", "acquire", "wait", "offset"):
        diagram.step(Block("a", shape, shape))
    xml.dom.minidom.parseString(render_svg(diagram))


def test_a_long_note_widens_the_figure_instead_of_leaving_it():
    short = SequenceDiagram({"a": "lane"})
    short.step(Block("a", "x", "gate", note="short"))
    wide = SequenceDiagram({"a": "lane"})
    wide.step(Block("a", "x", "gate", note="n" * MAX_NOTE_CHARS))

    def width(svg: str) -> float:
        return float(svg.split('width="', 1)[1].split('"', 1)[0])

    assert width(render_svg(wide)) > width(render_svg(short))


@pytest.mark.parametrize("build, message", [
    (lambda: SequenceDiagram({}), "at least one lane"),
    (lambda: Block("a", "x", "wavy"), "unknown block shape"),
    (lambda: Block("a", "", "gate"), "needs a label"),
    (lambda: Block("a", "x", "gate", note="n" * (MAX_NOTE_CHARS + 1)), "footnote"),
    (lambda: SequenceDiagram({"a": "A"}).step(), "at least one block"),
    (lambda: SequenceDiagram({"a": "A"}).step(Block("b", "x")), "does not have"),
    (lambda: SequenceDiagram({"a": "A"}).step(Block("a", "x"), Block("a", "y")),
     "at most one block per lane"),
    (lambda: render_svg(SequenceDiagram({"a": "A"})), "nothing to draw"),
])
def test_malformed_diagrams_are_refused_by_name(build, message):
    with pytest.raises(ValueError, match=message):
        build()


def test_repeat_refuses_nesting_and_an_empty_body():
    diagram = SequenceDiagram({"a": "A"})
    with pytest.raises(ValueError, match="do not nest"):
        with diagram.repeat("x 2"):
            with diagram.repeat("x 3"):
                pass
    with pytest.raises(ValueError, match="brackets no step"):
        with diagram.repeat("x 2"):
            pass
    assert diagram.repeats == []
