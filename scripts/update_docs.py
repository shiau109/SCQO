"""Regenerate the DERIVED parts of the docs from the code they describe.

Hand-kept lists rot. `report.py` already applies that rule to the viewer's field
orders (catalog-derived, never hand-kept); this script applies it to the docs.
Two blocks in CLAUDE.md:

* the registered-experiment census, which had drifted to 31 of 41 by the v3.1.0
  cut - missing both cryoscopes, both broadband scans and `qubit_ramsey_phasor`,
  the flagship feature of that very release.
* the experiment -> scqat estimator map. The binding rule is 1:1 in BOTH
  directions (CLAUDE.md -> Terminology), and the tree does not yet conform: this
  block is what makes each exception visible instead of folklore, and
  `tests/test_one_estimator_per_experiment.py` is what keeps the list shrinking.

And the generated parts of the experiment documents
(`scqo/experiments/_docs/`, read by `scqo/experiment_docs.py`): every
`sequence*.svg` a document links, rendered from the experiment's
`sequence_diagram`; the two blocks inside each document that come from the
class's `requires` / `writes` / `extracts`; the index `_docs/README.md`; and the
field-dependency table `_docs/DEPENDENCIES.md`.

    python scripts/update_docs.py            # rewrite whatever is stale, in place
    python scripts/update_docs.py --check    # exit 1 if anything is stale (CI)
    python scripts/update_docs.py --figures [NAME ...]
                                             # also redraw the expected-result PNGs

`tests/test_docs_current.py` and `tests/test_experiment_docs.py` run the --check
form, so a new @register or a changed sequence without a refresh fails the suite.

`--figures` is separate on purpose. An expected-result PNG comes from one run on
the simulated backend and its bytes move with the matplotlib version, so it is
only ever checked to EXIST; redraw it when the experiment's `simulate()` or its
estimator's figure changes, and before a release. A document whose front matter
says `expected: hardware ...` keeps the figure someone put there.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
EXPERIMENTS = REPO_ROOT / "scqo" / "experiments"

BLOCKS = {
    "experiments": "<!-- {} generated: experiments -->",
    "estimator-map": "<!-- {} generated: estimator-map -->",
}

COLUMNS = 3


def _core_experiments() -> list[type]:
    """The CORE experiment classes, taken from the EXPORTED names.

    Deliberately not `scqo.catalog()`: several test modules `@register`
    deliberately-broken fixture experiments at import time, so under the full suite
    the live registry is wider than the shipped one (46 vs 41 when this was written,
    which is how CI caught it while an isolated run passed). Selection is by TYPE,
    matching `tests/test_model_experiments.py`'s `CORE` and `test_capabilities` -
    `__all__` also re-exports the registry functions and the driver-facing capability
    surface, and a name-exclusion list would need editing every time one is added.
    """
    sys.path.insert(0, str(REPO_ROOT))
    import scqo.experiments as registry
    from scqo.experiment import Experiment

    return sorted(
        (
            obj
            for obj in (getattr(registry, n) for n in registry.__all__)
            if isinstance(obj, type) and issubclass(obj, Experiment)
        ),
        key=lambda c: c.name,
    )


def experiment_names() -> list[str]:
    return [cls.name for cls in _core_experiments()]


# ----------------------------------------------------------------- estimator map
def _resolve_bare(class_name: str) -> str:
    """`from scqat.estimators import X` names no subpackage - ask scqat which one.

    The fallback is the class name itself, so a missing scqat degrades the block
    rather than breaking the build; the row stays unique per experiment either way.
    """
    try:
        import scqat.estimators as agg

        module = getattr(agg, class_name).__module__  # scqat.estimators.<pkg>.estimator
        parts = module.split(".")
        return parts[2] if len(parts) > 2 else class_name
    except Exception:
        return class_name


def module_estimators() -> dict[str, str]:
    """`scqo/experiments/<stem>.py` -> the scqat estimator SUBPACKAGE it imports.

    Keyed on the subpackage, not the class: `readout_fidelity` serves two
    experiments through two thin subclasses, and that shared binding is exactly
    what the 1:1 rule is about, so class-keying would hide it.

    Private helpers (`scqat.estimators._twin_axis`) are not bindings and are
    skipped, as is any imported name that is not an `*Estimator`.
    """
    out: dict[str, str] = {}
    for path in sorted(EXPERIMENTS.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("scqat.estimators"):
                continue
            classes = [a.name for a in node.names if a.name.endswith("Estimator")]
            if not classes:
                continue
            parts = node.module.split(".")
            if len(parts) > 2:
                if parts[2].startswith("_"):
                    continue  # a shared function module, not a binding
                out[path.stem] = parts[2]
            else:
                out[path.stem] = _resolve_bare(classes[0])
    return out


def estimator_map() -> tuple[dict[str, list[str]], list[str]]:
    """(estimator -> [experiment names], [experiments binding none]).

    Resolved through the MRO, so an experiment that inherits `estimate()` from a
    parent experiment rather than defining its own is attributed to the estimator
    it actually runs, not counted as binding none.
    """
    by_module = module_estimators()
    bound: dict[str, list[str]] = {}
    unbound: list[str] = []
    for cls in _core_experiments():
        estimator = None
        for ancestor in cls.__mro__:
            mod = getattr(ancestor, "__module__", "")
            if not mod.startswith("scqo.experiments."):
                continue
            hit = by_module.get(mod.rsplit(".", 1)[-1])
            if hit:
                estimator = hit
                break
        if estimator is None:
            unbound.append(cls.name)
        else:
            bound.setdefault(estimator, []).append(cls.name)
    return {k: sorted(v) for k, v in sorted(bound.items())}, sorted(unbound)


# -------------------------------------------------------------------- renderers
def render_experiments() -> str:
    names = experiment_names()
    rows = -(-len(names) // COLUMNS)  # ceil
    width = max(len(n) for n in names) + 2
    lines = []
    for r in range(rows):
        # column-major, so the alphabetical order reads DOWN each column -
        # the same shape `scqo run` prints.
        cells = [names[r + c * rows] for c in range(COLUMNS) if r + c * rows < len(names)]
        lines.append("".join(cell.ljust(width) for cell in cells).rstrip())

    begin = BLOCKS["experiments"].format("BEGIN")
    end = BLOCKS["experiments"].format("END")
    return "\n".join(
        [
            begin,
            f"**{len(names)} registered experiments.** This list is GENERATED from the registry",
            "(`scqo.catalog()`) - refresh it with `python scripts/update_docs.py`. Descriptions are",
            "catalog-quality and live in the registry, never here: read one with",
            "`scqo run <name> --help`, or browse by capability with `scqo run --capability <name>`.",
            "",
            "```",
            *lines,
            "```",
            end,
        ]
    )


def render_estimator_map() -> str:
    bound, unbound = estimator_map()
    shared = [e for e, xs in bound.items() if len(xs) > 1]
    begin = BLOCKS["estimator-map"].format("BEGIN")
    end = BLOCKS["estimator-map"].format("END")
    lines = [
        begin,
        "**GENERATED** - refresh with `python scripts/update_docs.py`. Which scqat estimator",
        "each experiment binds, resolved through the MRO (so an inherited `estimate()` is",
        "attributed to the estimator it actually runs). The rule is ONE estimator per",
        "experiment and ONE experiment per estimator - see **Terminology**. A row naming two",
        "experiments, or a name in the trailing line, is a KNOWN VIOLATION carried in",
        "`tests/test_one_estimator_per_experiment.py`; that list may only shrink.",
        "",
        "| scqat estimator | experiments |",
        "|---|---|",
    ]
    for estimator, experiments in bound.items():
        mark = " **(shared)**" if len(experiments) > 1 else ""
        lines.append(f"| `{estimator}` | {', '.join(experiments)}{mark} |")
    lines.append("")
    if unbound:
        lines.append(
            "Binds no estimator (fits inline - also a violation): "
            + ", ".join(f"`{n}`" for n in unbound)
            + "."
        )
    else:
        lines.append("Every registered experiment binds an estimator.")
    lines.append(
        f"Shared bindings: {len(shared)}"
        + ((" - " + ", ".join(f"`{e}`" for e in shared) + ".") if shared else ".")
    )
    lines.append(end)
    return "\n".join(lines)


RENDERERS = {"experiments": render_experiments, "estimator-map": render_estimator_map}


# ---------------------------------------------------------- experiment documents
def experiment_doc_files() -> dict[Path, str]:
    """Every file under `scqo/experiments/_docs` with a GENERATED part -> its wanted
    text: the sequence figures each document links, each document itself with its
    generated blocks re-rendered (the prose around them is kept as it is), the
    index, and the field-dependency table."""
    classes = _core_experiments()
    from scqo import experiment_docs as docs

    wanted: dict[Path, str] = {}
    for cls in classes:
        if docs.has_doc(cls.name):
            doc = docs.load_doc(cls.name)
            for file, svg in docs.sequence_svgs(cls, doc).items():
                wanted[doc.folder / file] = svg
            path = docs.doc_path(cls.name)
            wanted[path] = docs.with_blocks(path.read_text(encoding="utf-8"),
                                            cls, classes)
    wanted[docs.DOCS_DIR / docs.DOC_FILE] = docs.render_index(classes)
    wanted[docs.DOCS_DIR / docs.DEPENDENCIES_FILE] = docs.render_dependencies(classes)
    return wanted


def stale_doc_files(wanted: dict[Path, str]) -> list[Path]:
    """The generated files that are missing or differ from a fresh render.

    Compared as TEXT, so a checkout that turned LF into CRLF is not stale."""
    return [path for path, text in wanted.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != text]


#: experiments run and ACCEPTED on the fresh demo session before a figure's own
#: run, for the few experiments that refuse to start on a device nothing has
#: measured yet. It is the calibration order of the document's "Before running
#: it" table, played once - not a second place to keep that order: an entry is
#: needed only where the experiment has a hard gate. An entry is an experiment
#: name, or ``(name, parameters)`` where the gate is opened by a non-default run.
_BEAT_RAMSEY = ("qubit_ramsey", {"ramsey_model": "beat"})
FIGURE_PREREQUISITES: dict[str, tuple[str | tuple[str, dict], ...]] = {
    # refuses without the stored |g> / |e> centres
    "qubit_thermal_population": ("single_shot_readout",),
    # refuses without a governed depletion wait (the Stark tone's ring-up)
    "qubit_resonator_stark": ("resonator_spectroscopy",),
    # refuse without the depletion wait (the shot cadence), the stored centres
    # (the trace discrimination) and the parity splitting (the fixed idle)
    "qubit_parity_switch_continuous": (
        "resonator_spectroscopy", "single_shot_readout", _BEAT_RAMSEY),
    "qubit_parity_switch_discrete": (
        "resonator_spectroscopy", "single_shot_readout", _BEAT_RAMSEY),
}

#: Parameters a document's simulated figure is drawn with, under the variant's
#: own. Only for an experiment whose defaults the demo device cannot hold or
#: that are not the setting its estimator is meant to be read at - and the
#: document says so beside the figure.
FIGURE_PARAMETERS: dict[str, dict] = {
    # the fit reads a population: on raw I/Q its rates are not physical
    "qubit_parametric_drive_time": {"use_state_discrimination": True},
    # ramp_v has no default: the run is refused without one
    "pair_coupler_spectroscopy_swap": {"ramp_v": [0.14, 0.0]},
    # the ridge is read only with a prior angle; this is the simulated one
    # (a quarter of a full transfer over the default four rounds)
    "qc_swap_flux_stark": {"swap_angle_rad": 0.196},
    # the demo's shot is a few us long, so the default 30 s record is more shots
    # than max_num_shots allows
    "qubit_parity_switch_continuous": {"record_time_s": 2.0},
    "qubit_parity_switch_discrete": {"record_time_s": 2.0},
}


def write_expected_figures(names: list[str]) -> int:
    """Redraw the simulated expected-result PNGs of the named documents (all of
    them when `names` is empty). Returns the number of problems, each printed.

    One fresh simulated session per figure, in a temporary data root: the run
    folder's `analysis/<target>/*.png` are the scqat estimator's own figures,
    which is the point - the document shows what a run folder shows.
    """
    import os
    import shutil
    import tempfile

    os.environ.setdefault("MPLBACKEND", "Agg")
    classes = {cls.name: cls for cls in _core_experiments()}
    from scqo import Session
    from scqo import experiment_docs as docs
    from scqo.cli._backends import default_targets
    from scqo.testing import SimulatedBackend, demo_device

    unknown = sorted(set(names) - set(classes))
    if unknown:
        print(f"--figures: not a registered experiment: {', '.join(unknown)}",
              file=sys.stderr)
        return len(unknown)

    def simulate(cls, overrides: dict, tmp: Path) -> list[Path]:
        # tunable, so the flux experiments have a flux line to sweep
        roster, design, vendor = demo_device(tunable=True)
        session = Session(SimulatedBackend(vendor), roster, design=design,
                          scqo_dir=tmp / "scqo", data_root=tmp / "data",
                          device_name="demo", setup_name="sim", cooldown_id="cd1")
        targets = default_targets(session, cls.name)[:1]
        for entry in FIGURE_PREREQUISITES.get(cls.name, ()):
            earlier, settings = (entry, {}) if isinstance(entry, str) else entry
            ran = session.run(earlier, {"targets": targets, **settings}, update="apply")
            if ran.get("error"):
                raise RuntimeError(f"prerequisite {earlier}: {ran['error']}")
        overrides = {**FIGURE_PARAMETERS.get(cls.name, {}), **overrides}
        out = session.run(cls.name, {"targets": targets, **overrides}, update="none")
        if out.get("error"):
            raise RuntimeError(out["error"])
        return sorted((Path(out["data_path"]) / "analysis").rglob("*.png"))

    problems = 0
    for name in names or sorted(classes):
        cls = classes[name]
        if not docs.has_doc(name):
            if names:
                print(f"{name}: no document at {docs.doc_path(name)}", file=sys.stderr)
                problems += 1
            continue
        doc = docs.load_doc(name)
        requests = docs.expected_requests(cls, doc)
        if not requests:
            print(f"{name}: expected figures are {doc.meta.get('expected')!r} - left alone")
            continue
        wanted = doc.meta.get("expected_figure", "")
        for file, overrides in requests.items():
            tmp = Path(tempfile.mkdtemp(prefix="scqo-docs-"))
            try:
                figures = simulate(cls, overrides, tmp)
                # the stem itself, or its tail after the estimator's own prefix
                # ("time_domain" picks ramsey_time_domain) - never a substring,
                # which six of readout_frequency's figures would share
                matches = [f for f in figures
                           if f.stem == wanted or f.stem.endswith("_" + wanted)
                           ] if wanted else figures
                if len(matches) != 1:
                    print(f"{name}: expected_figure={wanted!r} selects "
                          f"{[f.stem for f in matches]} of {[f.stem for f in figures]}; "
                          f"name exactly one in the front matter", file=sys.stderr)
                    problems += 1
                    continue
                shutil.copyfile(matches[0], doc.folder / file)
                print(f"{name}: wrote {file} from {matches[0].name}")
            except Exception as err:
                print(f"{name}: {file}: {type(err).__name__}: {err}", file=sys.stderr)
                problems += 1
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    return problems


def current_block(text: str, key: str) -> str:
    begin, end = BLOCKS[key].format("BEGIN"), BLOCKS[key].format("END")
    return text[text.index(begin) : text.index(end) + len(end)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if stale instead of rewriting")
    ap.add_argument("--figures", nargs="*", metavar="NAME",
                    help="also redraw the simulated expected-result PNGs (every "
                         "document, or only the named experiments)")
    args = ap.parse_args()
    if args.check and args.figures is not None:
        ap.error("--figures redraws PNGs and --check writes nothing; pick one")

    text = CLAUDE_MD.read_text(encoding="utf-8")
    stale = []
    for key, render in RENDERERS.items():
        begin, end = BLOCKS[key].format("BEGIN"), BLOCKS[key].format("END")
        if begin not in text or end not in text:
            print(f"{CLAUDE_MD.name}: missing the {key} markers", file=sys.stderr)
            return 2
        have, wanted = current_block(text, key), render()
        if have != wanted:
            stale.append(key)
            text = text.replace(have, wanted)

    doc_files = experiment_doc_files()
    stale_files = stale_doc_files(doc_files)

    if args.check:
        if stale:
            print(f"{CLAUDE_MD.name}: STALE generated block(s): {', '.join(stale)}.",
                  file=sys.stderr)
        for path in stale_files:
            print(f"STALE generated file: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
        if stale or stale_files:
            print("Run `python scripts/update_docs.py` and commit the result.",
                  file=sys.stderr)
            return 1
        print(f"{CLAUDE_MD.name}: generated blocks are current")
        print("experiment documents: generated files are current")
        return 0

    if stale:
        CLAUDE_MD.write_text(text, encoding="utf-8", newline="\n")
        print(f"{CLAUDE_MD.name}: rewrote {', '.join(stale)}")
    else:
        print(f"{CLAUDE_MD.name}: generated blocks are current")
    for path in stale_files:
        path.write_text(doc_files[path], encoding="utf-8", newline="\n")
        print(f"rewrote {path.relative_to(REPO_ROOT)}")
    if not stale_files:
        print("experiment documents: generated files are current")

    if args.figures is not None and write_expected_figures(args.figures):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
