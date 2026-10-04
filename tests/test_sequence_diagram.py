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
    HELD_LABEL,
    MAX_NOTE_CHARS,
    Block,
    SequenceDiagram,
    held,
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


def test_one_block_may_carry_two_swept_axes():
    """A readout swept in frequency AND power is one pulse, so both axes are
    marked on it and both names are drawn under it."""
    diagram = SequenceDiagram({"readout": "q.ro"})
    block = Block("readout", "readout", "acquire", swept=("power_dbm", "detuning_hz"))
    diagram.step(block)
    assert block.axes == ("power_dbm", "detuning_hz")
    assert Block("readout", "readout").axes == ()
    assert diagram.swept_axes() == {"power_dbm", "detuning_hz"}
    svg = render_svg(diagram)
    assert ">power_dbm<" in svg and ">detuning_hz<" in svg


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
    (lambda: SequenceDiagram({"a": "A"}).step(held("a")), "continues nothing"),
    (lambda: Block("a", HELD_LABEL, "square", swept="axis", held=True),
     "takes its axis and footnote from it"),
    (lambda: _gate_then_held(), "a gate cannot be held"),
])
def test_malformed_diagrams_are_refused_by_name(build, message):
    with pytest.raises(ValueError, match=message):
        build()


def test_repeat_refuses_an_empty_body():
    diagram = SequenceDiagram({"a": "A"})
    with pytest.raises(ValueError, match="brackets no step"):
        with diagram.repeat("x 2"):
            pass
    with pytest.raises(ValueError, match="brackets no step"):
        with diagram.repeat("x 2"):
            with diagram.repeat("x 3"):
                pass
    assert diagram.repeats == []


def _nested() -> SequenceDiagram:
    """A block of shots holding a repeated pair - the shape of a tracking
    experiment (blocks of probes) or of a shot loop around a two-round reset."""
    diagram = SequenceDiagram({"drive": "q.xy", "readout": "q.ro"})
    with diagram.repeat("x num_blocks", swept="block_idx"):
        diagram.step(Block("drive", "thermal reset", "wait"))
        with diagram.repeat("x num_probes"):
            diagram.step(Block("drive", "x180", "gate"))
            diagram.step(Block("readout", "readout", "acquire"))
    return diagram


def test_repeat_brackets_nest_and_the_outer_one_is_drawn_around_the_inner():
    diagram = _nested()
    # closing order: the inner bracket first
    assert [(r.label, r.first, r.last) for r in diagram.repeats] == [
        ("x num_probes", 1, 2), ("x num_blocks", 0, 2)]
    assert diagram.repeat_levels() == [0, 1]
    svg = render_svg(diagram)
    xml.dom.minidom.parseString(svg)
    rects = [node for node in xml.dom.minidom.parseString(svg).getElementsByTagName("rect")
             if node.getAttribute("stroke-dasharray") == "4 3"]
    inner, outer = rects

    def box(node):
        x, y = float(node.getAttribute("x")), float(node.getAttribute("y"))
        return (x, y, x + float(node.getAttribute("width")),
                y + float(node.getAttribute("height")))

    ix0, iy0, ix1, iy1 = box(inner)
    ox0, oy0, ox1, oy1 = box(outer)
    assert ox0 < ix0 and oy0 < iy0 and ox1 > ix1 and oy1 > iy1
    # ... and the two labels are on rows of their own
    rows = {node.getAttribute("y") for node in
            xml.dom.minidom.parseString(svg).getElementsByTagName("text")
            if node.firstChild.data.startswith("x num_")}
    assert len(rows) == 2


def test_an_outer_bracket_steps_out_only_on_an_edge_it_shares():
    """A bracket that holds an inner one somewhere in its middle keeps the plain
    inset, so it does not reach into the bracket next to it."""
    diagram = SequenceDiagram({"a": "A"})
    with diagram.repeat("x 2"):
        diagram.step(Block("a", "one", "gate"))
    with diagram.repeat("x 3"):
        diagram.step(Block("a", "two", "gate"))
        with diagram.repeat("x 4"):
            diagram.step(Block("a", "three", "gate"))
        diagram.step(Block("a", "four", "gate"))
    assert diagram.repeat_levels() == [0, 0, 1]     # closing order: x2, x4, x3
    rects = [node for node in xml.dom.minidom.parseString(
        render_svg(diagram)).getElementsByTagName("rect")
        if node.getAttribute("stroke-dasharray") == "4 3"]
    neighbour, _inner, outer = rects
    neighbour_right = (float(neighbour.getAttribute("x"))
                       + float(neighbour.getAttribute("width")))
    assert neighbour_right < float(outer.getAttribute("x"))


def test_two_brackets_side_by_side_are_both_innermost():
    diagram = SequenceDiagram({"a": "A"})
    with diagram.repeat("x 2"):
        diagram.step(Block("a", "one", "gate"))
    with diagram.repeat("x 3"):
        diagram.step(Block("a", "two", "gate"))
    assert diagram.repeat_levels() == [0, 0]


def _gate_then_held() -> None:
    diagram = SequenceDiagram({"a": "A"})
    diagram.step(Block("a", "x180", "gate"))
    diagram.step(held("a"))


def _pulse_rects(svg: str) -> list[tuple[float, float]]:
    """(x, width) of every solid pulse rectangle, left to right."""
    rects = [node for node in xml.dom.minidom.parseString(svg).getElementsByTagName("rect")
             if node.getAttribute("stroke-width") == "1.4"
             and not node.getAttribute("stroke-dasharray")]
    return sorted((float(n.getAttribute("x")), float(n.getAttribute("width")))
                  for n in rects)


def test_a_held_block_is_drawn_as_one_shape_across_its_steps():
    """A flux pulse that stays on while the drive lane waits and then plays:
    one rectangle from the first column to the end of the last, one label."""
    def build(hold: bool) -> SequenceDiagram:
        diagram = SequenceDiagram({"drive": "q.xy", "flux": "q.z"})
        diagram.step(Block("drive", "wait", "wait", swept="wait_time_ns"),
                     Block("flux", "flux pulse", "square", note="held to the end"))
        diagram.step(Block("drive", "drive", "square"),
                     *([held("flux")] if hold else []))
        diagram.step(Block("drive", "after", "square"))
        return diagram

    diagram = build(hold=True)
    assert diagram.held_through(0, "flux") == 1
    assert diagram.held_through(1, "drive") == 1     # nothing holds it
    assert diagram.swept_axes() == {"wait_time_ns"}
    assert diagram.notes() == ["held to the end"]

    svg = render_svg(diagram)
    assert HELD_LABEL not in svg
    assert svg.count(">flux pulse<") == 1
    (flux_x, flux_w), = [r for r in _pulse_rects(svg) if r not in _pulse_rects(
        render_svg(build(hold=False)))]
    drives = [r for r in _pulse_rects(svg) if r != (flux_x, flux_w)]
    # the flux pulse starts with the wait column and ends with the drive pulse
    assert flux_x < drives[0][0]
    assert flux_x + flux_w == pytest.approx(drives[0][0] + drives[0][1])
    # ... and holding it widens no column
    assert svg.split('width="', 1)[1].split('"', 1)[0] == render_svg(
        build(hold=False)).split('width="', 1)[1].split('"', 1)[0]


def test_a_held_run_may_span_more_than_two_steps():
    diagram = SequenceDiagram({"a": "A", "b": "B"})
    diagram.step(Block("a", "tone", "tone"), Block("b", "one", "gate"))
    diagram.step(held("a"), Block("b", "two", "gate"))
    diagram.step(held("a"), Block("b", "three", "gate"))
    assert diagram.held_through(0, "a") == 2
    xml.dom.minidom.parseString(render_svg(diagram))


def test_a_single_bracket_keeps_its_geometry():
    """Nesting must not move a figure that has none: the committed SVGs of the
    documents are compared byte for byte."""
    diagram = SequenceDiagram({"drive": "q.xy"})
    with diagram.repeat("x N", swept="num_rounds"):
        diagram.step(Block("drive", "x180", "gate"))
    svg = render_svg(diagram)
    assert '<rect x="64.2" y="50" width="64" height="76" rx="4"' in svg
    assert 'y="40"' in svg  # the bracket label's baseline
