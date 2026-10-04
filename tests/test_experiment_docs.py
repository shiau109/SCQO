"""Every experiment carries a document, and its generated parts are current.

`scqo/experiments/_docs/<name>/README.md` (read by `scqo/experiment_docs.py`,
plan in `docs/experiment-docs-plan.md`) explains one experiment: purpose, pulse
sequence, theory, expected result. This file is the census and the staleness
check - it runs no simulation, so it stays in the fast set:

* every core experiment has a document or is in ``UNDOCUMENTED``, and that list
  may only SHRINK - a name in it that has gained a document fails here, so the
  list cannot quietly go stale either;
* a document has the front matter, the fixed sections and the two generated
  blocks, links only figures that exist, and leaves no generated-looking orphan
  in its folder;
* the sequence diagram marks every ``Contract.sweeps`` axis - the one link
  between the declared picture and the dataset the probes must return;
* every ``sequence*.svg`` and the index equal a fresh render.

The expected-result PNGs are only checked to exist: they come from a simulated
run (`scripts/update_docs.py --figures`) and their bytes follow the matplotlib
version.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scqo import experiment_docs as docs
from scqo import experiments as registry
from scqo.experiment import Experiment
from scqo.experiment_docs import ExperimentDoc, check_doc, parse_front_matter

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "update_docs.py"

#: the CORE catalog, by type from the exported names - another test's @register
#: must never widen this (same guard as test_model_experiments.CORE)
CORE = {obj.name: obj for obj in (getattr(registry, n) for n in registry.__all__)
        if isinstance(obj, type) and issubclass(obj, Experiment)}

#: experiments still owed a document. THIS LIST MAY ONLY SHRINK: writing a
#: document means deleting its name here, and a new experiment never joins it -
#: it ships with its document (CLAUDE.md, promotion checklist).
UNDOCUMENTED = frozenset({
    "qc_trotter_compensation", "qc_unidirectional_trotter",
})

DOCUMENTED = sorted(name for name in CORE if docs.has_doc(name))


@pytest.fixture(scope="module")
def update_docs():
    spec = importlib.util.spec_from_file_location("update_docs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["update_docs"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------- census
def test_every_experiment_is_documented_or_listed():
    missing = sorted(name for name in CORE
                     if name not in UNDOCUMENTED and not docs.has_doc(name))
    assert not missing, (
        f"registered without a document: {missing}. Write "
        f"scqo/experiments/_docs/<name>/README.md (docs/experiment-docs-plan.md); "
        f"UNDOCUMENTED is not the place for a new experiment.")


def test_undocumented_list_only_shrinks():
    gained = sorted(name for name in UNDOCUMENTED if docs.has_doc(name))
    assert not gained, f"documented now - delete from UNDOCUMENTED: {gained}"
    retired = sorted(UNDOCUMENTED - set(CORE))
    assert not retired, f"no longer registered - delete from UNDOCUMENTED: {retired}"


def test_no_document_folder_without_an_experiment():
    folders = {path.name for path in docs.DOCS_DIR.iterdir() if path.is_dir()}
    assert folders <= set(CORE), sorted(folders - set(CORE))


def test_an_undocumented_experiment_declares_no_diagram_by_name():
    """The base hook refuses rather than drawing an empty picture."""
    name = sorted(UNDOCUMENTED)[0]
    cls = CORE[name]
    if "sequence_diagram" in vars(cls):
        pytest.skip(f"{name} already declares its diagram")
    with pytest.raises(NotImplementedError, match=cls.__name__):
        cls.sequence_diagram(None)


# ------------------------------------------------------------- each document
@pytest.mark.parametrize("name", DOCUMENTED)
def test_document_is_sound(name):
    problems = check_doc(CORE[name], docs.load_doc(name))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("name", DOCUMENTED)
def test_sequence_diagram_marks_every_sweep_axis(name):
    """A sweep axis the picture does not show is a sequence the reader cannot
    reconstruct - and the usual way a new axis lands without its diagram."""
    cls = CORE[name]
    for variant in (None, *cls.doc_variants):
        diagram = cls.sequence_diagram(docs.doc_params(cls, variant))
        unmarked = set(cls.Contract.sweeps) - diagram.swept_axes()
        assert not unmarked, (
            f"{name} ({variant or 'default'}): sweep axes {sorted(unmarked)} are "
            f"not marked `swept` on any block or repeat bracket")


def _active_reset_params(name):
    """Parameters asking for a two-round active reset, or None where the
    experiment has no reset capability or its Parameters refuse the method."""
    cls = CORE[name]
    if "reset_method" not in cls.Parameters.model_fields:
        return None
    try:
        return cls.Parameters(targets=["q"], reset_method="active",
                              active_reset_rounds=2)
    except ValueError:
        return None


ACTIVE_RESET_CARRIERS = [name for name in DOCUMENTED if _active_reset_params(name)]


@pytest.mark.parametrize("name", ACTIVE_RESET_CARRIERS)
def test_sequence_diagram_draws_the_reset_it_was_asked_for(name):
    """A diagram is a function of Parameters, but a document only ever renders
    the defaults. The reset is the setting every carrier shares, so it is the
    one checked on all of them: an active reset is drawn as its bracketed pair,
    also inside an experiment's own per-shot or per-block bracket."""
    from scqo.sequence_diagram import render_svg

    cls = CORE[name]
    diagram = cls.sequence_diagram(_active_reset_params(name))
    render_svg(diagram)
    labels = [block.label for step in diagram.steps for block in step]
    assert "thermal reset" not in labels and "x180 if e" in labels, name
    assert "x 2" in [rep.label for rep in diagram.repeats], name
    assert not set(cls.Contract.sweeps) - diagram.swept_axes(), name


def test_a_foreign_flux_source_is_drawn_on_the_source_lane():
    cls = CORE["qubit_spectroscopy_flux_pulse"]
    own = cls.sequence_diagram(cls.Parameters(targets=["q"]))
    foreign = cls.sequence_diagram(cls.Parameters(targets=["q"], flux_component="c"))
    assert own.lanes["flux"] == "q.z" and foreign.lanes["flux"] == "source.z"


def test_a_mapped_readout_is_drawn_on_the_member():
    """qubit_power_rabi on a coupler: the closing readout is the three-step map
    onto a pair member, on lanes of the member's own."""
    cls = CORE["qubit_power_rabi"]
    diagram = cls.sequence_diagram(cls.Parameters(
        targets=["c"], drive_line="xy2", readout_member="q1",
        use_state_discrimination=True))
    assert list(diagram.lanes.values()) == ["q.xy", "member.xy", "member.ro"]
    tail = [(block.lane, block.label) for step in diagram.steps[-3:] for block in step]
    assert tail == [("member_drive", "selective x180"), ("member_drive", "x180"),
                    ("member_readout", "readout")]
    assert diagram.swept_axes() == set(cls.Contract.sweeps)


@pytest.mark.parametrize("name", DOCUMENTED)
def test_doc_variants_are_valid_parameters(name):
    cls = CORE[name]
    for variant in cls.doc_variants:
        assert variant.replace("_", "").isalnum() and variant == variant.lower(), (
            f"{name}: variant {variant!r} becomes a file name - lower case, "
            f"digits and underscores only")
        docs.doc_params(cls, variant)  # raises on an unknown field or bad value


def test_figure_tables_name_documented_experiments_and_valid_parameters(update_docs):
    """`FIGURE_PREREQUISITES` / `FIGURE_PARAMETERS` are only exercised by
    `update_docs.py --figures`, which no test runs: a renamed experiment or
    parameter there would surface the next time someone redraws a figure."""
    for name, earlier in update_docs.FIGURE_PREREQUISITES.items():
        assert name in DOCUMENTED, name
        for entry in earlier:
            first, settings = (entry, {}) if isinstance(entry, str) else entry
            assert first in CORE, f"{name}: prerequisite {first!r} is not registered"
            CORE[first].Parameters(targets=["q"], **settings)
    for name, settings in update_docs.FIGURE_PARAMETERS.items():
        assert name in DOCUMENTED, name
        assert settings, f"{name}: an empty entry says nothing"
        CORE[name].Parameters(targets=["q"], **settings)
        text = docs.doc_path(name).read_text(encoding="utf-8")
        figure = text.split("## Expected result", 1)[1].split("## Traps", 1)[0]
        for field, value in settings.items():
            if isinstance(value, bool):
                shown = str(value).lower()
            elif isinstance(value, (list, tuple)):
                shown = "[" + ", ".join(f"{item:g}" for item in value) + "]"
            else:
                shown = f"{value:g}"
            assert f"{field}={shown}" in figure, (
                f"{name}: its figure is drawn with {field}={shown}; the document "
                f"has to say so beside the figure")


def test_generated_files_are_current(update_docs):
    """Every linked sequence figure and the index equal a fresh render."""
    stale = update_docs.stale_doc_files(update_docs.experiment_doc_files())
    assert not stale, (
        f"stale generated files: {[str(p.relative_to(REPO_ROOT)) for p in stale]}.\n"
        "Run `python scripts/update_docs.py` and commit the result.")


# ------------------------------------------------------------ the checker
def test_front_matter_is_flat_key_value():
    meta, body = parse_front_matter("---\nexperiment: x\n# a comment\n\n"
                                    "validated: offline\n---\n# x\n")
    assert meta == {"experiment": "x", "validated": "offline"}
    assert body == "# x\n"


@pytest.mark.parametrize("text, message", [
    ("# no front matter\n", "opens with"),
    ("---\nexperiment: x\n", "never closes"),
    ("---\nvariants:\n  beat: 1\n---\n", "not a flat"),
    ("---\nexperiment: x\nexperiment: y\n---\n", "appears twice"),
])
def test_front_matter_refusals(text, message):
    with pytest.raises(ValueError, match=message):
        parse_front_matter(text)


#: the empty generated blocks every document carries
MARKERS = "\n".join(line for key in docs.BLOCKS for line in docs.block_markers(key))


def _sections(titles=docs.SECTIONS, *, markers: bool = True) -> str:
    """A body's worth of section headings, with the generated-block markers."""
    body = "\n".join(f"## {title}\n\ntext\n" for title in titles)
    return (MARKERS + "\n" + body) if markers else body


def _doc(tmp_path, monkeypatch, *, meta=None, body=None, files=()):
    """A document for qubit_ramsey in a scratch docs folder."""
    monkeypatch.setattr(docs, "DOCS_DIR", tmp_path)
    folder = tmp_path / "qubit_ramsey"
    folder.mkdir()
    for file in files:
        (folder / file).write_bytes(b"x")
    default_body = ("# qubit_ramsey\n\n![s](sequence.svg)\n\n![e](expected.png)\n\n"
                    + _sections())
    return ExperimentDoc(
        name="qubit_ramsey",
        meta={"experiment": "qubit_ramsey", "validated": "offline",
              "expected": "simulated", **(meta or {})},
        body=default_body if body is None else body)


def test_checker_accepts_a_minimal_document(tmp_path, monkeypatch):
    doc = _doc(tmp_path, monkeypatch, files=("sequence.svg", "expected.png"))
    assert check_doc(CORE["qubit_ramsey"], doc) == []


@pytest.mark.parametrize("meta, message", [
    ({"validated": "yes"}, "validated: 'yes'"),
    ({"validated": "hardware 5Q4C 2026-09-22"}, None),
    ({"expected": "hardware 5Q4C 2026-09-22"}, "expected:"),       # no run id
    ({"expected": "hardware 5Q4C 2026-09-22 20260922-101500"}, None),
    ({"experiment": "qubit_echo"}, "front matter says experiment"),
    ({"owner": "someone"}, "unknown front matter key 'owner'"),
])
def test_checker_reads_the_front_matter(tmp_path, monkeypatch, meta, message):
    doc = _doc(tmp_path, monkeypatch, meta=meta,
               files=("sequence.svg", "expected.png"))
    problems = check_doc(CORE["qubit_ramsey"], doc)
    if message is None:
        assert problems == []
    else:
        assert any(message in problem for problem in problems), problems


def test_checker_refuses_sections_out_of_order(tmp_path, monkeypatch):
    doc = _doc(tmp_path, monkeypatch, files=("sequence.svg", "expected.png"),
               body="![s](sequence.svg) ![e](expected.png)\n"
                    + _sections(tuple(reversed(docs.SECTIONS))))
    assert any("in that order" in p for p in check_doc(CORE["qubit_ramsey"], doc))


def test_checker_ignores_headings_inside_code_fences(tmp_path, monkeypatch):
    doc = _doc(tmp_path, monkeypatch, files=("sequence.svg", "expected.png"))
    fenced = doc.body + "\n```\n## Not a section\n```\n"
    doc = ExperimentDoc(doc.name, doc.meta, fenced)
    assert check_doc(CORE["qubit_ramsey"], doc) == []


def test_checker_figure_rules(tmp_path, monkeypatch):
    body = ("![s](sequence.svg) ![e](expected.png) ![v](expected-nope.png) "
            "![w](sequence-beat.png) ![o](other.png)\n" + _sections())
    doc = _doc(tmp_path, monkeypatch, body=body,
               files=("sequence.svg", "expected.png", "expected-stray.png"))
    problems = "\n".join(check_doc(CORE["qubit_ramsey"], doc))
    assert "variant 'nope', which is not in" in problems      # unknown variant
    assert "a sequence figure is a .svg file" in problems     # wrong type
    assert "links 'other.png', which is not in the folder" in problems
    assert "expected-stray.png is in the folder" in problems  # orphan
    assert "has not been generated" in problems               # linked, missing


def test_checker_requires_both_figures(tmp_path, monkeypatch):
    doc = _doc(tmp_path, monkeypatch, body=_sections())
    problems = "\n".join(check_doc(CORE["qubit_ramsey"], doc))
    assert "must show sequence.svg" in problems
    assert "must show expected.png" in problems


def test_checker_requires_the_generated_blocks(tmp_path, monkeypatch):
    doc = _doc(tmp_path, monkeypatch, files=("sequence.svg", "expected.png"),
               body="![s](sequence.svg) ![e](expected.png)\n"
                    + _sections(markers=False))
    problems = "\n".join(check_doc(CORE["qubit_ramsey"], doc))
    assert "generated block 'requires' must appear exactly once" in problems
    assert "generated block 'outputs' must appear exactly once" in problems


def test_blocks_are_filled_from_the_declarations_and_only_they_change():
    cls, classes = CORE["qubit_ramsey"], list(CORE.values())
    text = "before\n" + MARKERS + "\nafter\n"
    filled = docs.with_blocks(text, cls, classes)
    assert filled.startswith("before\n") and filled.endswith("\nafter\n")
    assert docs.with_blocks(filled, cls, classes) == filled  # idempotent
    # the requirement table names who provides each value - the join with `writes`
    assert "| `drive_freq_hz` | drive channel |" in filled
    assert "`qubit_spectroscopy`" in filled
    # a requirement whose condition is the DEFAULT sits in the main table...
    assert "(with the default `reset_method=thermal`)" in filled
    # ...and one that needs a non-default setting is listed apart
    assert "| `reset_method=active` | `readout_depletion_s` |" in filled
    # outputs: the catalog supplies holder, role, unit and meaning
    assert "| `t2_star_s` | qubit mode | fact | s |" in filled
    assert "| `detuning_error_hz` |" in filled
    # a document without markers is left alone (check_doc reports it instead)
    assert docs.with_blocks("no markers\n", cls, classes) == "no markers\n"


def test_a_starting_value_requirement_says_so():
    """A bring-up experiment needs of the field it measures only a place to
    start; the block must not read as if a calibration were wanted."""
    cls, classes = CORE["resonator_spectroscopy"], list(CORE.values())
    row = next(line for line in docs.render_requires_block(cls, classes).splitlines()
               if line.startswith("| `readout_freq_hz`"))
    assert "a starting value is enough" in row
    ramsey = docs.render_requires_block(CORE["qubit_ramsey"], classes)
    assert "a starting value is enough" not in ramsey


def test_a_table_cell_never_breaks_its_row():
    """A catalog doc may contain a pipe (`|f_1 - f_2|`) or span lines."""
    text = docs.render_outputs_block(CORE["qubit_ramsey"], list(CORE.values()))
    row = next(line for line in text.splitlines()
               if line.startswith("| `parity_delta_f_hz`"))
    assert row.replace("\\|", "").count("|") == 6


def test_dependencies_table_joins_writers_and_dependents():
    text = docs.render_dependencies(list(CORE.values()))
    row = next(line for line in text.splitlines() if line.startswith("| `drive_freq_hz`"))
    cells = row.split("|")
    assert "`qubit_spectroscopy`" in cells[4] and "`qubit_ramsey`" in cells[4]
    assert "`qubit_ramsey`" in cells[5]
    # a capability's requirement reaches every carrier without being restated
    reset = next(line for line in text.splitlines()
                 if line.startswith("| `thermalization_time_s`")).split("|")
    assert "`qubit_relaxation`" in reset[4]
    assert "`qubit_echo`" in reset[5]


def test_index_lists_every_core_experiment_once(update_docs):
    text = docs.render_index(list(CORE.values()))
    for name in CORE:
        assert text.count(f"`{name}`") + text.count(f"[{name}]") == 1, name
