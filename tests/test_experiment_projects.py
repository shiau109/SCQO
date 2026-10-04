"""Shared experiments versus project experiments (`Experiment.project`).

An experiment with no project is SHARED - device-level calibration or
characterization. One that declares a project serves a single study. The
classification is declared, so these tests are what keeps it honest: the
summaries table tracks the declared set in both directions, and the `scqo run`
listing keeps project experiments out of the shared menu.
"""

from __future__ import annotations

import pytest

from scqo import catalog
from scqo import experiments as registry
from scqo.cli._backends import ensure_demo_experiments
from scqo.cli._engine import (
    _catalog_listing_lines,
    _check_project_flags,
    _schema_epilog,
)
from scqo.experiment import Experiment
from scqo.experiments import PROJECT_SUMMARIES

#: the CORE classes, selected by type from the exported names - another test's
#: @register must never widen this (same guard as test_model_experiments.CORE)
CORE = [obj for obj in (getattr(registry, n) for n in registry.__all__)
        if isinstance(obj, type) and issubclass(obj, Experiment)]

#: Synthetic entries: golden-line tests must not depend on the live registry.
ENTRIES = [
    {"name": "aaa_shared", "maturity": "core", "project": None,
     "capabilities": ["flux"]},
    {"name": "bbb_study", "maturity": "core", "project": "MpembaEP_trotter",
     "capabilities": ["flux", "qubit_reset"]},
    {"name": "ccc_shared", "maturity": "core", "project": None, "capabilities": []},
]


def test_project_summaries_track_the_declared_set():
    """A declared project with no summary, or a summary no experiment declares,
    would make the listing and the document index lie about what exists."""
    declared = {cls.project for cls in CORE if cls.project}
    assert set(PROJECT_SUMMARIES) == declared
    for name, summary in PROJECT_SUMMARIES.items():
        assert summary and summary.isascii() and "`" not in summary, name
        assert not summary.endswith("."), name  # the renderers add punctuation


def test_the_project_experiments_are_exactly_these():
    """The classification is a decision, so it is pinned: moving an experiment
    in or out of a project is a deliberate edit here too."""
    assert {cls.name: cls.project for cls in CORE if cls.project} == {
        "qc_trotter_compensation": "MpembaEP_trotter",
        "qc_unidirectional_trotter": "MpembaEP_trotter",
    }


def test_catalog_carries_the_project():
    ensure_demo_experiments()
    entries = {entry["name"]: entry for entry in catalog()}
    assert entries["qubit_ramsey"]["project"] is None
    assert entries["qc_unidirectional_trotter"]["project"] == "MpembaEP_trotter"


def test_bare_listing_is_the_shared_menu():
    lines = _catalog_listing_lines(ENTRIES, width=80)
    names = "\n".join(lines[:-3])
    assert "aaa_shared" in names and "ccc_shared" in names
    assert "bbb_study" not in "\n".join(lines)
    assert lines[-3] == ("# projects: MpembaEP_trotter(1)    "
                         "list one: scqo run --project <name>")
    # the capability footer counts the SHARED menu only
    assert lines[-2].startswith("# capabilities: ") and "flux(1)" in lines[-2]
    assert "qubit_reset(0)" in lines[-2]
    assert lines[-1].startswith("# filter: scqo run --capability <name>")


def test_no_projects_line_when_nothing_declares_one():
    shared_only = [e for e in ENTRIES if not e["project"]]
    assert not any(line.startswith("# projects:")
                   for line in _catalog_listing_lines(shared_only, width=80))


def test_project_listing():
    lines = _catalog_listing_lines(ENTRIES, project="MpembaEP_trotter")
    assert lines[0].startswith("# project: MpembaEP_trotter - ")
    assert lines[0].endswith("[1 experiment]") and lines[0].isascii()
    assert lines[1:] == ["bbb_study"]


def test_capability_filter_covers_the_shared_menu_only():
    lines = _catalog_listing_lines(ENTRIES, capabilities=["flux"])
    assert lines[0].endswith("[1 experiment]")
    assert lines[1:] == ["aaa_shared"]


@pytest.mark.parametrize("args, message", [
    (("MpembaEP_trotter", "qubit_ramsey", []), "drop the experiment name"),
    (("MpembaEP_trotter", None, ["flux"]), "pick one"),
    (("no_such_project", None, []), "unknown project: no_such_project"),
])
def test_project_flag_refusals(args, message):
    with pytest.raises(SystemExit, match=message):
        _check_project_flags(*args)


def test_help_names_the_project(monkeypatch, tmp_path):
    epilog = _schema_epilog("qc_unidirectional_trotter", None)
    assert f"project: MpembaEP_trotter - {PROJECT_SUMMARIES['MpembaEP_trotter']}" in epilog
    assert "project:" not in _schema_epilog("qubit_ramsey", None)
