"""What an experiment needs and what it writes are declared - and checked here.

`Experiment.requires` / `.writes` / `.extracts` (`scqo/requirements.py`) feed the
catalog, the documents' generated sections and the field-dependency table, so a
wrong declaration would misstate the calibration order everywhere at once.

* NAMES: every declared field is a catalog field, every condition names a real
  parameter. Renaming a field in `catalog.py` fails here, at each declaration.
* `writes` IS EXACT where it can be exercised: on the simulated backend an
  experiment never proposes a field it did not declare, and a DOCUMENTED one
  proposes every field it declared, over its default Parameters and its
  `doc_variants` (the conditional paths a document has to show anyway).
* `extracts` names exactly the fit keys that are reported and never written.

`requires` cannot be proven complete - drivers read much of their state straight
from the vendor tree - so only its names and conditions are checked.

This module runs every experiment once on the simulated backend, like
`test_model_experiments.test_every_experiment_runs_clean`, but in suggest mode.
"""

from __future__ import annotations

import pytest

import test_model_experiments as base
from scqo import Session, catalog
from scqo import experiment_docs as docs
from scqo import experiments as registry
from scqo.cli._backends import ensure_demo_experiments
from scqo.requirements import (
    Requirement,
    collect,
    dependents,
    field_owner,
    field_spec,
    unknown_fields,
    writers,
)
from scqo.testing import (
    InMemoryDevice,
    SimulatedBackend,
    demo_components,
    demo_design,
    demo_vendor_state,
)

CORE = {name: registry.get(name) for name in base.CORE}


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    """The chain demo device of test_model_experiments, with the same seeded
    values, in a session of this module's own."""
    tmp = tmp_path_factory.mktemp("outputs")
    roster = demo_components(base.CHAIN_QUBITS, tunable=True, chain=True)
    design = demo_design(roster, base.CHAIN_QUBITS)
    vendor = InMemoryDevice(roster, demo_vendor_state(roster, design))
    s = Session(SimulatedBackend(vendor), roster, design=design,
                scqo_dir=tmp / "scqo", data_root=tmp / "data",
                device_name="chipT", setup_name="sim", cooldown_id="cd1",
                parameter_defaults=base.OFFLINE_DEFAULTS)
    s.set_values({f"fl.{q}.{field}": value for q in base.CHAIN_QUBITS
                  for field, value in base.REFERENCE_BLOBS.items()})
    s.set_values({f"fl.{q}.readout_depletion_s": 1e-6 for q in base.CHAIN_QUBITS})
    s.set_values({f"xy_{q}.{q}.parity_delta_f_hz": 250e3 for q in base.CHAIN_QUBITS})
    return s


# ---------------------------------------------------------------------- names
@pytest.mark.parametrize("name", sorted(CORE))
def test_declared_fields_are_catalog_fields(name):
    cls = CORE[name]
    assert unknown_fields(cls.writes) == [], f"{name}.writes"
    assert unknown_fields(req.field for req in collect(cls)) == [], f"{name}.requires"
    assert len(set(cls.writes)) == len(cls.writes), f"{name}.writes repeats a field"
    overlap = set(cls.extracts) & set(cls.writes)
    assert not overlap, f"{name}: {sorted(overlap)} are both written and fit-only"


@pytest.mark.parametrize("name", sorted(CORE))
def test_requirement_conditions_name_real_parameters(name):
    cls = CORE[name]
    fields = cls.Parameters.model_fields
    for req in collect(cls):
        assert req.why and not req.why.endswith("."), (name, req.field)
        if req.when is not None:
            assert req.when[0] in fields, (
                f"{name}: requirement {req.field!r} is conditional on "
                f"{req.when[0]!r}, which {cls.Parameters.__name__} does not have")


def test_every_catalog_field_resolves_to_an_owner_and_a_spec():
    """The documents print these for any declared field, so none may raise."""
    from scqo.catalog import ALL_FIELD_NAMES  # the module, via sys.modules

    for field in sorted(ALL_FIELD_NAMES):
        assert field_owner(field)
        assert field_spec(field).role in ("fact", "knob", "monitor")
    with pytest.raises(KeyError):
        field_owner("not_a_field")


# ------------------------------------------------------------------ mechanics
def test_mixin_requirements_reach_every_carrier():
    """A capability's needs are declared once, on its Parameters mixin."""
    reset = {req.field for req in collect(CORE["qubit_relaxation"])}
    assert "thermalization_time_s" in reset
    # a carrier of no capability and with no lines of its own needs nothing
    assert all(collect(cls) == () or collect(cls) for cls in CORE.values())
    ramsey = collect(CORE["qubit_ramsey"])
    assert ramsey[0].field == "drive_freq_hz"  # the experiment's own lines lead


def test_a_condition_decides_whether_a_requirement_applies():
    cls = CORE["qubit_ramsey"]
    thermal = cls.Parameters(targets=["q"])
    active = cls.Parameters(targets=["q"], reset_method="active")

    def fields(params):
        return {req.field for req in collect(cls) if req.applies(params)}

    assert "thermalization_time_s" in fields(thermal)
    assert "readout_depletion_s" not in fields(thermal)
    assert "readout_depletion_s" in fields(active)
    assert "thermalization_time_s" not in fields(active)
    assert Requirement("x", "y", when=("use_state_discrimination", True)).condition() \
        == "use_state_discrimination=true"


def test_an_experiment_may_restate_a_mixin_line_with_its_own_reason():
    class Mixin(CORE["qubit_ramsey"].Parameters):
        pass

    class Restating(CORE["qubit_ramsey"]):
        Parameters = Mixin
        requires = (Requirement("thermalization_time_s", "its own reason",
                                when=("reset_method", "thermal")),)

    lines = [req for req in collect(Restating) if req.field == "thermalization_time_s"]
    assert [req.why for req in lines] == ["its own reason"]


def test_a_condition_the_parameters_refuse_is_not_a_requirement():
    """`qubit_thermal_population` rejects reset_method='active' (an active reset
    removes what it measures), so what an active reset needs is not listed."""
    cls = CORE["qubit_thermal_population"]
    with pytest.raises(ValueError, match="refused"):
        cls.Parameters(targets=["q"], reset_method="active")
    conditions = {req.condition() for req in collect(cls)}
    assert "reset_method=active" not in conditions
    assert "reset_method=thermal" in conditions
    # ... while a carrier that allows the setting keeps the lines
    assert "reset_method=active" in {
        req.condition() for req in collect(CORE["qubit_relaxation"])}


def test_an_unconditional_need_supersedes_a_conditional_one_for_the_same_field():
    """`qubit_t1_ade` discriminates every shot: its threshold is needed always,
    so the reset mixin's 'with reset_method=active' line for it says nothing."""
    lines = [req for req in collect(CORE["qubit_t1_ade"])
             if req.field == "readout_threshold"]
    assert [req.when for req in lines] == [None]
    # the active reset's OTHER need is still conditional
    depletion = [req for req in collect(CORE["qubit_t1_ade"])
                 if req.field == "readout_depletion_s"]
    assert [req.condition() for req in depletion] == ["reset_method=active"]


def test_a_condition_may_list_alternatives():
    """Six target gates are played from two knobs: one line per knob, each
    conditional on ANY of its gates."""
    cls = CORE["qubit_deterministic_benchmarking"]
    by_field = {req.field: req for req in collect(cls)}
    assert by_field["pi_amp"].condition() == "target_gate=x180 / y180"
    assert by_field["pi_amp_x90"].condition() == "target_gate=x90 / y90 / -x90 / -y90"
    assert by_field["pi_amp"].as_dict()["when"] == "target_gate=x180 / y180"
    pi_gate = cls.Parameters(targets=["q"])
    half_gate = cls.Parameters(targets=["q"], target_gate="-y90")
    assert by_field["pi_amp"].applies(pi_gate)
    assert not by_field["pi_amp_x90"].applies(pi_gate)
    assert by_field["pi_amp_x90"].applies(half_gate)
    assert not by_field["pi_amp"].applies(half_gate)


def test_a_class_with_required_parameters_of_its_own_keeps_every_condition():
    """The refusal test needs a baseline that validates; without one a failure
    could not be pinned on the setting, so nothing is dropped."""
    from pydantic import Field

    class Needy(CORE["qubit_relaxation"].Parameters):
        must_be_given: int = Field(..., description="no default")

    class Carrier(CORE["qubit_relaxation"]):
        Parameters = Needy

    assert {req.condition() for req in collect(Carrier)} == {
        req.condition() for req in collect(CORE["qubit_relaxation"])}


def test_the_join_gives_providers_and_dependents():
    classes = list(CORE.values())
    assert "qubit_spectroscopy" in writers(classes)["drive_freq_hz"]
    assert "qubit_relaxation" in writers(classes)["thermalization_time_s"]
    assert "qubit_ramsey" in dependents(classes)["drive_freq_hz"]


def test_catalog_carries_requires_and_writes():
    ensure_demo_experiments()
    entry = next(e for e in catalog() if e["name"] == "qubit_ramsey")
    assert entry["writes"] == list(CORE["qubit_ramsey"].writes)
    assert entry["requires"][0] == {
        "field": "drive_freq_hz",
        "why": CORE["qubit_ramsey"].requires[0].why, "when": None, "seed_ok": False}
    seeded = next(e for e in catalog() if e["name"] == "resonator_spectroscopy")
    assert seeded["requires"][0] == {
        "field": "readout_freq_hz", "why": "the swept window is centred on it",
        "when": None, "seed_ok": True}
    assert {"field": "thermalization_time_s",
            "when": "reset_method=thermal"}.items() <= next(
        r for r in entry["requires"] if r["field"] == "thermalization_time_s").items()
    assert entry["backend_notes"] == []  # a driver's subclass supplies these


# ------------------------------------------------- writes against a real run
def _observed(session, name):
    """(fields proposed, fit keys) over the default Parameters and every
    doc_variants set, on the simulated backend."""
    cls = CORE[name]
    proposed: set[str] = set()
    fit_keys: set[str] = set()
    for overrides in ({}, *cls.doc_variants.values()):
        out = session.run(name, {"targets": base._targets_for(name), **overrides})
        assert out.get("error") is None, out.get("error")
        proposed |= {s["field"] for s in out["suggestions"]}
        for per_target in (out.get("fit") or {}).values():
            fit_keys |= set(per_target)
    return proposed, fit_keys


@pytest.mark.parametrize("name", sorted(CORE))
def test_update_proposes_only_what_is_declared(session, name):
    cls = CORE[name]
    proposed, fit_keys = _observed(session, name)
    undeclared = proposed - set(cls.writes)
    assert not undeclared, (
        f"{name}.update() proposed {sorted(undeclared)}, which `writes` does not "
        f"declare. Add them: the catalog, the documents and the dependency table "
        f"all read `writes`.")
    if not docs.has_doc(name):
        return
    # A documented experiment is held to equality: its doc_variants exist to
    # exercise the conditional paths, so a declared field nothing proposed is
    # either a stale declaration or a missing variant.
    unproposed = set(cls.writes) - proposed
    assert not unproposed, (
        f"{name} declares `writes` {sorted(unproposed)} that no simulated run "
        f"proposed (default Parameters + doc_variants {sorted(cls.doc_variants)})")
    unexplained = fit_keys - set(cls.writes) - set(cls.extracts)
    assert not unexplained, (
        f"{name}: fit keys {sorted(unexplained)} are neither written nor in "
        f"`extracts` - the document's Outputs section would not mention them")
    absent = set(cls.extracts) - fit_keys
    assert not absent, f"{name}.extracts names keys no run returned: {sorted(absent)}"
