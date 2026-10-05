"""Experiment documents - one per registered experiment.

``scqo/experiments/_docs/<name>/README.md`` explains ONE experiment to the
person or agent about to run it: what it is for, its pulse sequence, the
theory behind the signal, and what a good result looks like. This module reads
and checks those documents; ``scripts/update_docs.py`` generates their figures
and ``tests/test_experiment_docs.py`` holds the census. Plan and rationale:
``docs/experiment-docs-plan.md``.

WHAT IS HAND-WRITTEN AND WHAT IS NOT. The prose is hand-written. The parameter
table, the estimator binding, the capabilities and the project are NOT copied
in - they stay in the registry (``scqo run <name> --help``). Two sections are
GENERATED from declarations on the experiment class (``scqo/requirements.py``),
between ``<!-- BEGIN generated: <key> -->`` markers:

* ``requires`` (section *Before running it*) - the device values that must
  already be right, and which experiments provide each one;
* ``outputs`` (section *Outputs*) - the fields ``update()`` may propose and
  the fit keys that are only reported.

So what an experiment needs and leaves behind is never hand-written prose: a
renamed field fails the declaration's test, and the documents follow. The
whole join, field by field, is ``_docs/DEPENDENCIES.md``.

Nothing true of one backend only is written here; a driver declares that on
its own subclass (``backend_notes``) and ``--help`` shows it where it applies.

The two kinds of figure are generated:

* ``sequence.svg`` (and ``sequence-<variant>.svg``) from the experiment's
  ``sequence_diagram``; deterministic text, compared with a fresh render.
* ``expected.png`` (and ``expected-<variant>.png``) from one run on the
  simulated backend, using the figure the scqat estimator writes into every run
  folder - or supplied by hand from a hardware run, which the front matter then
  says and the generator leaves alone. A PNG is only checked to exist: its
  bytes move with the matplotlib version.

THE DOCUMENT DRIVES THE GENERATION: a figure is produced exactly when the
document links it, a ``<variant>`` must be a key of the experiment's
``doc_variants``, and a generated-looking file nothing links is an orphan.

FRONT MATTER IS FLAT ``key: value`` LINES. scqo depends on no YAML parser and
this subset needs none; anything nested belongs on the class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: where the documents live - inside the package, so the CLI and the viewer
#: find them without knowing the repository layout (as viewer/templates does)
DOCS_DIR = Path(__file__).resolve().parent / "experiments" / "_docs"
DOC_FILE = "README.md"

#: the body's sections, in this order, as ``## <title>`` headings - fixed so a
#: reader (or an agent) can jump straight to the one it needs
SECTIONS = ("Purpose", "Before running it", "Pulse sequence", "Theory", "Outputs",
            "Expected result", "Traps", "References")

#: the generated blocks a document carries, each exactly once
BLOCKS = ("requires", "outputs")
DEPENDENCIES_FILE = "DEPENDENCIES.md"

REQUIRED_KEYS = ("experiment", "validated", "expected")
OPTIONAL_KEYS = ("expected_figure",)

#: the promotion checklist's three states (CLAUDE.md, *Experiment governance*)
_VALIDATED = re.compile(r"^(offline|unverified|hardware \S+ \d{4}-\d{2}-\d{2}\b.*)$")
#: where the expected figure came from: this generator, or a named hardware run
_EXPECTED = re.compile(r"^(simulated|hardware \S+ \d{4}-\d{2}-\d{2} \S+.*)$")
#: the file names reserved for the two figure kinds
_FIGURE = re.compile(r"^(sequence|expected)(?:-([a-z0-9_]+))?\.([a-z]+)$")
_FIGURE_EXT = {"sequence": "svg", "expected": "png"}
_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^## (.+?)\s*$")


@dataclass(frozen=True)
class Figure:
    """One linked figure with a reserved name."""

    file: str
    kind: str                # "sequence" | "expected"
    variant: str | None      # a doc_variants key; None = the default Parameters


@dataclass(frozen=True)
class ExperimentDoc:
    """One parsed document."""

    name: str
    meta: dict[str, str]
    body: str

    @property
    def folder(self) -> Path:
        return DOCS_DIR / self.name

    def sections(self) -> list[str]:
        """The ``##`` headings in order, ignoring fenced code."""
        out, fenced = [], False
        for line in self.body.splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
            elif not fenced:
                match = _HEADING.match(line)
                if match:
                    out.append(match.group(1))
        return out

    def images(self) -> list[str]:
        """Every RELATIVE image link, in order of first appearance."""
        out: list[str] = []
        for target in _IMAGE.findall(self.body):
            if "://" not in target and target not in out:
                out.append(target)
        return out

    def figures(self) -> list[Figure]:
        """The linked images that carry a reserved figure name."""
        out = []
        for target in self.images():
            match = _FIGURE.match(target)
            if match:
                out.append(Figure(target, match.group(1), match.group(2)))
        return out


def doc_path(name: str) -> Path:
    return DOCS_DIR / name / DOC_FILE


def has_doc(name: str) -> bool:
    return doc_path(name).is_file()


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a document into its front matter and its body.

    Flat ``key: value`` lines between two ``---`` lines; a blank line or a line
    starting with ``#`` is skipped. Anything else is refused, naming the line.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("a document opens with a '---' front matter block")
    meta: dict[str, str] = {}
    for number, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return meta, "\n".join(lines[number:]) + "\n"
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t" or ":" not in line:
            raise ValueError(
                f"front matter line {number}: {line!r} is not a flat 'key: value' "
                f"line. Nested values are not supported - put structure on the "
                f"experiment class (doc_variants)")
        key, _, value = line.partition(":")
        key = key.strip()
        if key in meta:
            raise ValueError(f"front matter line {number}: {key!r} appears twice")
        meta[key] = value.strip()
    raise ValueError("the front matter block never closes with '---'")


def load_doc(name: str) -> ExperimentDoc:
    """Read and parse one experiment's document."""
    meta, body = parse_front_matter(doc_path(name).read_text(encoding="utf-8"))
    return ExperimentDoc(name=name, meta=meta, body=body)


def check_doc(cls, doc: ExperimentDoc) -> list[str]:
    """Everything wrong with ``doc`` as the document of experiment ``cls``;
    ``[]`` when it is sound. Reads the folder, renders nothing."""
    problems: list[str] = []
    allowed = (*REQUIRED_KEYS, *OPTIONAL_KEYS)
    for key in doc.meta:
        if key not in allowed:
            problems.append(f"unknown front matter key {key!r}; allowed: {allowed}")
    for key in REQUIRED_KEYS:
        if not doc.meta.get(key):
            problems.append(f"front matter lacks {key!r}")
    if doc.meta.get("experiment") and doc.meta["experiment"] != doc.name:
        problems.append(
            f"front matter says experiment {doc.meta['experiment']!r} but the "
            f"folder is {doc.name!r}")
    if doc.name != cls.name:
        problems.append(f"folder {doc.name!r} documents {cls.name!r}")
    validated = doc.meta.get("validated", "")
    if validated and not _VALIDATED.match(validated):
        problems.append(
            f"validated: {validated!r} is not one of 'offline', 'unverified', "
            f"'hardware <chip> <YYYY-MM-DD>'")
    expected = doc.meta.get("expected", "")
    if expected and not _EXPECTED.match(expected):
        problems.append(
            f"expected: {expected!r} is neither 'simulated' nor "
            f"'hardware <chip> <YYYY-MM-DD> <run_id>'")

    if tuple(doc.sections()) != SECTIONS:
        problems.append(
            f"sections are {doc.sections()}; a document carries exactly "
            f"{list(SECTIONS)}, in that order")
    for key in BLOCKS:
        begin, end = block_markers(key)
        if doc.body.count(begin) != 1 or doc.body.count(end) != 1:
            problems.append(
                f"the generated block {key!r} must appear exactly once, as the "
                f"two lines {begin!r} and {end!r} (python scripts/update_docs.py "
                f"fills what is between them)")

    linked = set()
    for target in doc.images():
        match = _FIGURE.match(target)
        if match is None:
            if not (doc.folder / target).is_file():
                problems.append(f"links {target!r}, which is not in the folder")
            continue
        kind, variant, ext = match.groups()
        linked.add(target)
        if ext != _FIGURE_EXT[kind]:
            problems.append(
                f"{target!r}: a {kind} figure is a .{_FIGURE_EXT[kind]} file")
        if variant is not None and variant not in cls.doc_variants:
            problems.append(
                f"{target!r} names variant {variant!r}, which is not in "
                f"{cls.__name__}.doc_variants {sorted(cls.doc_variants)}")
        if not (doc.folder / target).is_file():
            problems.append(
                f"links {target!r}, which has not been generated - run "
                f"python scripts/update_docs.py"
                + (" --figures" if kind == "expected" else ""))
    for mandatory in ("sequence.svg", "expected.png"):
        if mandatory not in linked:
            problems.append(f"the document must show {mandatory}")
    if doc.folder.is_dir():
        for path in sorted(doc.folder.iterdir()):
            if _FIGURE.match(path.name) and path.name not in linked:
                problems.append(
                    f"{path.name} is in the folder but the document does not "
                    f"link it; link it or delete it")
    return problems


def doc_params(cls, variant: str | None = None):
    """The Parameters a figure is drawn for: the experiment's defaults on one
    placeholder target, its ``doc_parameters`` (what has no default), and a
    variant's overrides on top."""
    overrides = cls.doc_variants[variant] if variant is not None else {}
    return cls.Parameters(**{"targets": ["q"], **cls.doc_parameters, **overrides})


def sequence_svgs(cls, doc: ExperimentDoc) -> dict[str, str]:
    """``{file name: SVG text}`` for every sequence figure the document links."""
    from .sequence_diagram import render_svg

    return {
        fig.file: render_svg(cls.sequence_diagram(doc_params(cls, fig.variant)))
        for fig in doc.figures() if fig.kind == "sequence"
    }


def expected_requests(cls, doc: ExperimentDoc) -> dict[str, dict]:
    """``{file name: parameter overrides}`` for every expected figure the
    generator owns - none when the document says the figures are hardware's."""
    if doc.meta.get("expected") != "simulated":
        return {}
    return {
        fig.file: dict(cls.doc_variants[fig.variant]) if fig.variant else {}
        for fig in doc.figures() if fig.kind == "expected"
    }


# ----------------------------------------------------------- generated blocks
def block_markers(key: str) -> tuple[str, str]:
    return f"<!-- BEGIN generated: {key} -->", f"<!-- END generated: {key} -->"


def _cell(text: str) -> str:
    """One line of text, safe inside a Markdown table cell."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _names(names) -> str:
    return ", ".join(f"`{name}`" for name in names)


def render_requires_block(cls, classes) -> str:
    """The *Before running it* block: what must already be right, what it is
    used for, and which experiments provide it - the last column is the join of
    this experiment's requirements with every experiment's ``writes``."""
    from . import requirements as reqs

    provided = reqs.writers(classes)
    defaults = doc_params(cls)

    def provider(field: str) -> str:
        return _names(provided[field]) if field in provided else (
            "no shared experiment; set it by hand (`scqo set`) or by a "
            "backend's own writeback")

    def use(req) -> str:
        # a seed_ok line is what a bring-up experiment asks of the field it
        # is about to measure, so say it is not a calibration that is wanted
        return _cell(req.why) + (
            "; a starting value is enough (the design value will do)"
            if req.seed_ok else "")

    always = [r for r in cls.requirements() if r.applies(defaults)]
    other = [r for r in cls.requirements() if not r.applies(defaults)]
    begin, end = block_markers("requires")
    lines = [
        begin,
        f"GENERATED from `{cls.__name__}.requires` and its Parameters mixins - edit",
        "the declaration, then run `python scripts/update_docs.py`.",
        "",
        "The target is a " + " / ".join(f"`{kind}`" for kind in cls.target_kinds)
        + (f" carrying the operations {_names(cls.required_operations)}."
           if cls.required_operations else "."),
    ]
    if always:
        lines += ["", "These device values must already be right:", "",
                  "| value | held by | used for | provided by |", "|---|---|---|---|"]
        for req in always:
            note = f" (with the default `{req.condition()}`)" if req.when else ""
            lines.append(f"| `{req.field}` | {reqs.field_owner(req.field)} | "
                         f"{use(req)}{note} | {provider(req.field)} |")
    else:
        lines += ["", "With the default parameters it needs no device value "
                      "beyond what its target kind guarantees."]
    if other:
        lines += ["", "Needed only with a non-default setting:", "",
                  "| setting | value | held by | used for | provided by |",
                  "|---|---|---|---|---|"]
        for req in other:
            lines.append(f"| `{req.condition()}` | `{req.field}` | "
                         f"{reqs.field_owner(req.field)} | {use(req)} | "
                         f"{provider(req.field)} |")
    lines += ["",
              "A backend may need more than this - a knob only it consumes. "
              f"`scqo run {cls.name} --help` lists those where that driver is "
              "installed.",
              end]
    return "\n".join(lines)


def render_outputs_block(cls, classes) -> str:
    """The *Outputs* block: the fields ``update()`` may propose, with their
    catalog meaning, and the fit keys that are only reported."""
    from . import requirements as reqs

    begin, end = block_markers("outputs")
    lines = [
        begin,
        f"GENERATED from `{cls.__name__}.writes` and `.extracts` - edit the",
        "declaration, then run `python scripts/update_docs.py`.",
    ]
    if cls.writes:
        lines += ["", "Proposed by `update()`; each stays pending until it is accepted:",
                  "", "| field | held by | role | unit | meaning |",
                  "|---|---|---|---|---|"]
        for field in cls.writes:
            spec = reqs.field_spec(field)
            lines.append(f"| `{field}` | {reqs.field_owner(field)} | {spec.role} | "
                         f"{spec.unit or '-'} | {_cell(spec.doc)} |")
    else:
        lines += ["", "Record-only: `update()` proposes nothing."]
    if cls.extracts:
        lines += ["", "Reported in `result.fit` and never written:", "",
                  "| fit key | meaning |", "|---|---|"]
        lines += [f"| `{key}` | {_cell(meaning)} |"
                  for key, meaning in cls.extracts.items()]
    # Who NEEDS these fields is deliberately not listed here: that set grows
    # with every experiment that declares a requirement, and a document should
    # not change because another experiment did. DEPENDENCIES.md carries it.
    lines.append(end)
    return "\n".join(lines)


_RENDER = {"requires": render_requires_block, "outputs": render_outputs_block}


def with_blocks(text: str, cls, classes) -> str:
    """``text`` (a whole document) with every generated block re-rendered. A
    block whose markers are missing is left for ``check_doc`` to report."""
    for key in BLOCKS:
        begin, end = block_markers(key)
        if text.count(begin) == 1 and text.count(end) == 1:
            start, stop = text.index(begin), text.index(end) + len(end)
            text = text[:start] + _RENDER[key](cls, classes) + text[stop:]
    return text


def render_dependencies(classes: list[type]) -> str:
    """The text of ``_docs/DEPENDENCIES.md``: for every field some experiment
    requires or writes, who writes it and who needs it. This is the calibration
    order as data - and the answer to "what breaks if I rename this field"."""
    from . import requirements as reqs

    written, needed = reqs.writers(classes), reqs.dependents(classes)
    lines = [
        "# Field dependencies",
        "",
        "GENERATED by `python scripts/update_docs.py` - do not edit by hand.",
        "For every device field an experiment declares: which experiments' `update()`",
        "may write it and which experiments require it before they run. Joined from",
        "`Experiment.writes` and `Experiment.requires` (`scqo/requirements.py`).",
        "",
        "`writes` is checked against simulated runs: no experiment proposes a field it",
        "did not declare, and a documented experiment proposes every field it declared.",
        "`requires` is a reviewed list: so far it covers the capability mixins on every",
        "experiment and the documented experiments' own lines, so an empty *required by*",
        "means not declared yet, not unused.",
        "",
        "| field | held by | role | written by | required by |",
        "|---|---|---|---|---|",
    ]
    for field in sorted(set(written) | set(needed)):
        lines.append(
            f"| `{field}` | {reqs.field_owner(field)} | {reqs.field_spec(field).role} | "
            f"{_names(written.get(field, ())) or '-'} | "
            f"{_names(needed.get(field, ())) or '-'} |")
    return "\n".join(lines) + "\n"


def _first_sentence(text: str) -> str:
    match = re.match(r"(.+?[.;])(\s|$)", text.strip(), flags=re.S)
    sentence = match.group(1) if match else text.strip()
    return " ".join(sentence.rstrip(";").split()).replace("|", "\\|")


def render_index(classes: list[type]) -> str:
    """The text of ``_docs/README.md``: the documented experiments, shared
    first and then by project, and the names still owed a document."""
    from .experiments import PROJECT_SUMMARIES

    def rows(group: list[type]) -> list[str]:
        out = ["| experiment | what it does | validated |", "|---|---|---|"]
        for cls in group:
            meta = load_doc(cls.name).meta
            out.append(f"| [{cls.name}]({cls.name}/{DOC_FILE}) | "
                       f"{_first_sentence(cls.description)} | "
                       f"{meta.get('validated', '')} |")
        return out

    classes = sorted(classes, key=lambda c: c.name)
    documented = [cls for cls in classes if has_doc(cls.name)]
    owed = [cls.name for cls in classes if not has_doc(cls.name)]
    lines = [
        "# Experiment documents",
        "",
        "GENERATED by `python scripts/update_docs.py` - do not edit by hand.",
        "One folder per documented experiment: what it needs before it runs, its",
        "pulse sequence, what it writes, and what a good result looks like.",
        "Parameters are not repeated here; read them with `scqo run <name> --help`.",
        f"Which experiment provides what another needs: [{DEPENDENCIES_FILE}]"
        f"({DEPENDENCIES_FILE}).",
        "",
        f"**{len(documented)} of {len(classes)} registered experiments are documented.**",
        "",
        "## Shared",
        "",
        "Device-level calibration and characterization, for every chip and operator.",
        "",
    ]
    shared = [cls for cls in documented if cls.project is None]
    lines += rows(shared) if shared else ["None yet."]
    for project in sorted({cls.project for cls in classes if cls.project}):
        group = [cls for cls in documented if cls.project == project]
        summary = PROJECT_SUMMARIES.get(project, "")
        lines += ["", f"## Project `{project}`", "",
                  summary[:1].upper() + summary[1:] + ".", ""]
        lines += rows(group) if group else ["None yet."]
    if owed:
        lines += ["", "## Not documented yet", "",
                  ", ".join(f"`{name}`" for name in owed)]
    return "\n".join(lines) + "\n"
