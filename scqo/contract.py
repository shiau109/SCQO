"""Canonical dataset contract per probing method.

Each probing method declares the dataset its probe must emit (and its estimator
consumes): the ``qubit`` dimension, the swept axis (name + unit), and the required
data variables. This is the explicit API between *driving* (any instrument's probe)
and *analysis* (the one shared estimator).

It also makes "support" a single, testable property: an instrument **supports** a
method exactly when its probe emits a dataset that conforms here — at which point the
shared estimator is guaranteed to apply. Drivers can therefore certify a probe with one
call (``Experiment.Contract.validate(probe_output)``); SCQO itself enforces it at
runtime in :meth:`Experiment.run`.

The contract is deliberately SCQO-neutral (e.g. ``idle_time_ns`` in ns), independent of
any estimator's internal coordinate names; the estimator-specific renaming lives in one
place (each ``estimate()``), so probe authors never depend on SCQAT's naming.
"""

from __future__ import annotations

from dataclasses import dataclass

import xarray as xr


class ContractError(ValueError):
    """Raised when a dataset does not conform to a method's canonical contract."""


@dataclass(frozen=True)
class DatasetContract:
    """The canonical dataset a single-sweep probing method's probe must emit.

    Attributes:
        sweep: name of the swept dimension/coordinate (e.g. ``"idle_time_ns"``).
        sweep_unit: documentary unit of the sweep axis (e.g. ``"ns"``, ``"Hz"``,
            ``"dimensionless"``); not enforced (xarray coords carry no units here).
        variables: data variables every conforming dataset must contain.
        qubit_dim: the per-qubit dimension/coordinate name (default ``"qubit"``).
    """

    sweep: str
    sweep_unit: str
    variables: tuple[str, ...]
    qubit_dim: str = "qubit"

    @property
    def dims(self) -> tuple[str, str]:
        """The dimensions every required variable must span: ``(qubit_dim, sweep)``."""
        return (self.qubit_dim, self.sweep)

    def validate(self, ds: xr.Dataset) -> None:
        """Raise :class:`ContractError` if ``ds`` does not conform.

        Checks that ``qubit_dim`` and ``sweep`` are present as both a dimension and a
        coordinate, and that each required variable exists and spans exactly those two
        dimensions. Extra variables/coordinates are allowed (e.g. a probe may also emit
        ``Q`` for a method whose estimator only reads ``I``).
        """
        problems: list[str] = []
        for dim in (self.qubit_dim, self.sweep):
            if dim not in ds.dims:
                problems.append(f"missing dimension {dim!r}")
            if dim not in ds.coords:
                problems.append(f"missing coordinate {dim!r}")
        want = {self.qubit_dim, self.sweep}
        for var in self.variables:
            if var not in ds.data_vars:
                problems.append(f"missing variable {var!r}")
                continue
            if set(ds[var].dims) != want:
                problems.append(
                    f"variable {var!r} has dims {tuple(ds[var].dims)}, expected {self.dims}"
                )
        if problems:
            raise ContractError(
                f"dataset does not conform to contract (sweep={self.sweep!r}, "
                f"variables={self.variables}): " + "; ".join(problems)
            )

    def conforms(self, ds: xr.Dataset) -> bool:
        """Return ``True`` iff ``ds`` conforms (non-raising form of :meth:`validate`)."""
        try:
            self.validate(ds)
            return True
        except ContractError:
            return False
