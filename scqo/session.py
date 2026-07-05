"""Session — the single entry point used identically by humans and AI agents.

Everything crosses this boundary as plain JSON-able Python (dicts / lists), so the
same calls drive a manual notebook *and* an LLM tool-use loop:

    sess = Session(backend, state_path="scqo_state.json", data_root="D:/qpu_data")
    sess.catalog()                     # what can I measure? (with parameter schemas)
    sess.run("qubit_ramsey", {...})    # measure -> structured result (+ run_id)
    sess.find_runs(experiment="qubit_ramsey", qubit="q0")   # find my data
    sess.load_run(run_id)              # reload a saved run (record/params/result/figures)
    sess.device_state()                # current calibration (the SCQO config)
    sess.history()                     # every recorded change (the loop's memory)

No vendor/hardware object is ever exposed here. The Session owns the **authoritative
SCQO config + change history** (a :class:`~scqo.config.RecordingDevice` wrapping the
backend's vendor device) and, when ``data_root`` is given, a
:class:`~scqo.datastore.DataStore` that persists **every** run — dataset, parameters,
result, device snapshots, and the scqat analysis artifacts (figures included).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from . import registry
from .backend import Backend
from .config import RecordingDevice, _now
from .contract import ContractError
from .datastore import DataStore
from .experiment import Experiment
from .result import Outcome, Result


class Session:
    """Bind a backend and expose the experiment-level API over an SCQO-owned config."""

    def __init__(
        self,
        backend: Backend,
        *,
        state_path: str | None = None,
        data_root: str | Path | None = None,
        device_name: str = "device",
        state_sync: Literal["push", "pull"] = "pull",
        default_tags: list[str] | None = None,
        backend_label: str | None = None,
    ) -> None:
        self.backend = backend
        #: provenance label recorded on every run. The class name alone is ambiguous:
        #: SimulatedBackend serves both the demo device AND the virtual twin, so the
        #: lab config's backend mode (e.g. "qblox_sim") is passed through here.
        self.backend_label = backend_label or type(backend).__name__
        self._persist = state_path is not None
        #: authoritative SCQO config + history over the backend's vendor device. With
        #: ``state_sync="pull"`` (default) the vendor wins at startup and only history is
        #: loaded; ``"push"`` loads the saved SCQO config and pushes it into the vendor
        #: (only for devices SCQO fully owns — see scqo.config).
        self.device = RecordingDevice(backend.device, state_path=state_path, on_load=state_sync)
        #: run datastore (folders + rebuildable SQLite index); None disables persistence.
        self.datastore = DataStore(data_root, device_name=device_name) if data_root is not None else None
        self.default_tags = list(default_tags or [])

    def catalog(self) -> list[dict]:
        """List available measurements with their JSON parameter schemas."""
        return registry.catalog()

    def run(
        self,
        experiment: str,
        params: dict[str, Any],
        update: bool = True,
        *,
        tags: list[str] | None = None,
        note: str = "",
    ) -> dict:
        """Run an experiment by name; return its structured result as a dict.

        If ``update`` and at least one qubit succeeded, the fitted values for the
        successful qubits are written back through the SCQO config — recorded into the
        change history and pushed to the vendor device — and the SCQO state is persisted
        (when a ``state_path`` was given). A failed run (a non-conforming probe dataset or
        a raising estimator) is returned as a structured result with ``error`` set and
        every qubit marked failed, never raised: the Session boundary stays JSON in/out.

        With a ``data_root`` configured, **every** run — successful or failed — is saved
        to its own run folder and indexed; the returned dict gains ``run_id`` and
        ``data_path``. ``tags`` (merged with the Session's ``default_tags``) and ``note``
        are stored searchably. A persistence failure never destroys a measurement
        result: it is reported as ``datastore_error`` in the returned dict instead.
        """
        cls = registry.get(experiment)
        exp = cls(self.backend, cls.Parameters(**params))
        exp.device = self.device  # route reads/writes through the recording config

        started_at = _now()
        run_id: str | None = None
        run_dir: Path | None = None
        if self.datastore is not None:
            run_id, run_dir = self.datastore.new_run_dir(experiment)
            exp.artifact_dir = run_dir / "analysis"  # scqat writes metadata/figures here

        device_before = self.device.snapshot()
        self.device.set_context(experiment, run_id)
        updated = False
        try:
            try:
                result = exp.run()
            except Exception as err:  # probe/estimator failure -> structured result
                result = self._failure(cls, exp, err)
            else:
                if update and result.any_success:
                    # Writeback failures must not raise either, and must not destroy
                    # the measurement: the fit stays in the result, the error says
                    # the device was not (fully) updated.
                    try:
                        exp.update()
                        updated = True
                        if self._persist:
                            self.device.save()
                    except Exception as err:
                        result.error = (
                            f"measurement succeeded but device update/save failed "
                            f"(device may be partially updated): {type(err).__name__}: {err}"
                        )
        finally:
            self.device.set_context(None, None)

        payload = result.model_dump(mode="json")
        if self.datastore is not None:
            assert run_id is not None and run_dir is not None
            try:
                self.datastore.persist_run(
                    run_id=run_id,
                    run_dir=run_dir,
                    experiment=experiment,
                    params=exp.params,
                    dataset=exp.dataset,
                    result=payload,
                    device_before=device_before,
                    device_after=self.device.snapshot(),
                    started_at=started_at,
                    ended_at=_now(),
                    backend=self.backend_label,
                    updated_device=updated,
                    tags=list(dict.fromkeys([*self.default_tags, *(tags or [])])),
                    note=note,
                )
            except Exception as err:  # never lose a measurement over a save problem
                payload["datastore_error"] = f"{type(err).__name__}: {err}"
            else:
                payload["run_id"] = run_id
                payload["data_path"] = str(run_dir)
        return payload

    @staticmethod
    def _failure(cls: type[Experiment], exp: Experiment, err: Exception) -> Result:
        """Build an all-failed structured result for a run that could not complete."""
        outcome = Outcome.NO_DATA if isinstance(err, ContractError) else Outcome.FAILED
        qubits = getattr(exp.params, "qubits", [])
        return cls.Result(
            outcomes={q: outcome for q in qubits},
            error=f"{type(err).__name__}: {err}",
        )

    # ------------------------------------------------------------------ datastore
    def find_runs(self, **filters: Any) -> list[dict]:
        """Query saved runs (newest first). Filters: experiment, qubit, tag, since,
        until, outcome, device, limit. Returns [] when no ``data_root`` is configured."""
        if self.datastore is None:
            return []
        return self.datastore.find_runs(**filters)

    def load_run(self, run_id: str) -> dict:
        """Reload a saved run: record + parameters + result + figure paths (JSON-able)."""
        return self._require_datastore().load_run(run_id)

    def tag_run(
        self, run_id: str, *, add: list[str] | None = None,
        remove: list[str] | None = None, note: str | None = None,
    ) -> dict:
        """Add/remove searchable tags (or set the note) on an already-saved run."""
        return self._require_datastore().tag_run(run_id, add=add, remove=remove, note=note)

    def _require_datastore(self) -> DataStore:
        if self.datastore is None:
            raise RuntimeError("this Session has no data_root configured (no datastore)")
        return self.datastore

    # ------------------------------------------------------------------ state
    def device_state(self) -> dict:
        """Return a JSON snapshot of the authoritative SCQO calibration config."""
        return self.device.snapshot()

    def history(self) -> list[dict]:
        """Return the recorded change history (JSON-able): the loop's memory."""
        return [record.as_dict() for record in self.device.history()]
