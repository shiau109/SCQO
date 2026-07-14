"""Backend — bridges an abstract experiment to a concrete instrument (or a simulator).

The backend owns the device model and knows how to *acquire* data for an experiment.
This is the only seam where vendor APIs (qm-qua, qblox-scheduler) appear.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import xarray as xr

from .device import DeviceModel

if TYPE_CHECKING:
    from .experiment import Experiment


class Backend(ABC):
    """An instrument adapter."""

    @property
    @abstractmethod
    def device(self) -> DeviceModel:
        """The device model whose state experiments read and update."""

    @abstractmethod
    def acquire(self, experiment: "Experiment") -> xr.Dataset:
        """Realize and execute ``experiment`` on this backend, returning labelled data.

        Hardware backends call ``experiment.probe()`` to produce a native program
        (a QUA program or a Qblox ``Schedule``), run it, and return the result as an
        ``xarray.Dataset`` with a ``qubit`` dimension plus the experiment's sweep axes.
        The simulated backend ignores ``probe`` and calls ``experiment.simulate`` instead.
        """

    def power_context(self, qubits: list[str]) -> dict:
        """Raw per-qubit output-chain values behind ``readout_power_dbm`` at run end.

        Vendor-specific keys (QM: full_scale_power_dbm + readout amplitude; Qblox:
        output_att + pulse_amp + the nominal full scale), stamped into each run
        record as PROVENANCE ONLY — never re-applied. The default is ``{}``: the
        simulated backend has no output chain.
        """
        return {}
