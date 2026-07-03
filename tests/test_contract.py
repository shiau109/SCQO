"""Canonical-contract conformance: every method's (simulated) probe output conforms,
run() enforces the contract, and validate() rejects non-conforming data.

These are the SCQO-side conformance checks; a real driver runs the same
``Experiment.Contract.validate(probe_output)`` against its own probe.
"""

from __future__ import annotations

import pytest

from scqo import ContractError, DatasetContract
from scqo.experiments import QubitPowerRabi, QubitRamsey, ResonatorSpectroscopy
from scqo.testing import InMemoryDevice, SimulatedBackend


def _device() -> InMemoryDevice:
    return InMemoryDevice(
        {
            "q0": {"readout_freq": 5.95e9, "drive_freq": 3.87e9, "pi_amp": 0.2},
            "q1": {"readout_freq": 6.05e9, "drive_freq": 4.01e9, "pi_amp": 0.18},
        }
    )


# Concrete (unregistered) subclasses: SimulatedBackend never calls probe().
class _Res(ResonatorSpectroscopy):
    def probe(self):
        return None


class _Ram(QubitRamsey):
    def probe(self):
        return None


class _PR(QubitPowerRabi):
    def probe(self):
        return None


CASES = [
    (_Res, "detuning_hz"),
    (_Ram, "idle_time_ns"),
    (_PR, "amp_factor"),
]


def _acquire(cls):
    backend = SimulatedBackend(_device())
    exp = cls(backend, cls.Parameters(qubits=["q0", "q1"]))
    exp.sweep_axes = exp.define_sweep()
    return exp, backend.acquire(exp)


@pytest.mark.parametrize("cls, sweep", CASES)
def test_simulated_probe_output_conforms(cls, sweep):
    exp, ds = _acquire(cls)
    # the declared contract's sweep axis matches define_sweep, and the dataset conforms
    assert cls.Contract.sweep == sweep
    assert cls.Contract.dims == ("qubit", sweep)
    exp.Contract.validate(ds)  # does not raise
    assert exp.Contract.conforms(ds)


def test_run_enforces_contract():
    """A backend that drops a required variable makes run() raise ContractError
    (before estimate() ever sees the data)."""

    class DropIBackend(SimulatedBackend):
        def acquire(self, experiment):
            return super().acquire(experiment).drop_vars("I")

    exp = _Ram(DropIBackend(_device()), _Ram.Parameters(qubits=["q0"]))
    with pytest.raises(ContractError):
        exp.run()


def test_validate_rejects_nonconforming():
    contract = DatasetContract(sweep="idle_time_ns", sweep_unit="ns", variables=("I", "Q"))
    _, ds = _acquire(_Ram)

    contract.validate(ds)  # baseline: conforms

    with pytest.raises(ContractError):
        contract.validate(ds.drop_vars("Q"))  # missing required variable

    with pytest.raises(ContractError):
        contract.validate(ds.rename({"idle_time_ns": "t"}))  # missing sweep dim/coord
