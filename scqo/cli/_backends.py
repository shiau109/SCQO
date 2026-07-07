"""Session building for the CLI: device -> cycle -> setup -> backend.

Real instruments are served by DRIVER packages that register a factory under the
``scqo.backends`` entry-point group (name = the backend family)::

    [project.entry-points."scqo.backends"]
    qblox = "lchqb.scqo_backend:build_backend"

A factory is ``build_backend(cfg: LabConfig, setup: dict) -> Backend`` — ``setup``
is the device's current era record from its cooldown registry (backend, the
``instrument_config`` folder holding the vendor config files, the port map).
``simulated`` (demo qubits, synthetic data) is built in here, so query commands,
practice runs and CI need no driver at all.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from scqo import LabConfig, Session, load_lab_config, make_session
from scqo.backend import Backend

#: Demo device for the built-in simulated backend (unified across the lab — the QM
#: repo's old q1/q2 demo names were retired with the CLI consolidation).
DEMO_QUBITS = {
    "q0": {"readout_freq": 5.95e9, "drive_freq": 3.87e9, "pi_amp": 0.20, "readout_amp": 0.25},
    "q1": {"readout_freq": 6.05e9, "drive_freq": 4.01e9, "pi_amp": 0.18, "readout_amp": 0.22},
}

#: backend family -> (what provides it, which venv on the lab machines)
SERVED_BY = {
    "qblox": ("LCHQBDriver", ".venv-qblox"),
    "qm": ("LCHQMDriver", ".venv-qm"),
    "simulated": ("scqo built-in", "any venv"),
}


def default_qubits(sess: Session) -> list[str]:
    """Measurable qubits for 'run on everything' defaults.

    The device tree may also contain couplers (lab convention: ``c*``, e.g. ``c12``)
    modeled as transmon elements without a usable readout port — measuring one fails
    on hardware. Only ``q*`` elements are measurement targets by default; pass
    --qubits to override explicitly.
    """
    return [q for q in sess.device_state() if q.startswith("q")]


def ensure_demo_experiments() -> None:
    """Make the simulated backend usable with NO driver installed.

    scqo core registers nothing (its experiment classes are abstract — no probe);
    the catalog normally fills via the drivers' ``scqo.experiments`` entry points.
    For pure-simulated use (the view venv, SCQO CI) this registers a probe-less
    subclass for every core experiment — but only for names still ABSENT from the
    catalog, so a driver's registration is never shadowed.
    """
    from scqo import catalog, register
    from scqo import experiments as _exp
    from scqo.experiment import Experiment

    registered = {entry["name"] for entry in catalog()}  # triggers entry-point discovery
    for attr in _exp.__all__:
        cls = getattr(_exp, attr)
        if isinstance(cls, type) and issubclass(cls, Experiment) and getattr(cls, "name", None):
            if cls.name not in registered:
                register(type(f"Sim{cls.__name__}", (cls,), {"probe": lambda self: None,
                                                             "__doc__": cls.__doc__}))


def _demo_session(cfg: LabConfig) -> tuple[Session, LabConfig]:
    from scqo.testing import InMemoryDevice, SimulatedBackend

    ensure_demo_experiments()
    backend: Backend = SimulatedBackend(InMemoryDevice(DEMO_QUBITS))
    return make_session(backend, cfg, backend_label="simulated"), cfg


def build_session(config_path: str | None = None) -> tuple[Session, LabConfig]:
    """Resolve device -> active cycle -> current setup -> backend; return a Session.

    The user names only the SAMPLE (``device`` in user.toml, else the [lab] default);
    the sample's cooldown registry says which instrument carries it right now and
    where that instrument's vendor config lives. No device anywhere = the built-in
    simulated demo (nothing saved). Every missing link fails loudly naming the exact
    manager command that creates it.
    """
    cfg = load_lab_config(config_path)
    if cfg.device is None:
        return _demo_session(cfg)
    if cfg.data_root is None:
        raise SystemExit(
            f"device {cfg.device!r} is selected but no data_root is configured in "
            f"{cfg.source or 'the lab config'} — the device's cooldown registry lives under it"
        )

    from scqo.datastore import active_cooldown, current_setup, load_cooldowns

    cycles = load_cooldowns(cfg.data_root, cfg.device)  # loud on a broken registry
    fix = (f"scqo cooldown start cd1 --backend <qblox|qm|simulated> "
           f"[--instrument-config <folder>]   (device {cfg.device!r})")
    if not cycles:
        raise SystemExit(f"device {cfg.device!r} has no cooldown registry yet — the manager runs:\n  {fix}")
    active = active_cooldown(cycles)
    if active is None:
        raise SystemExit(f"device {cfg.device!r} has no ACTIVE cooldown cycle — start the next one:\n  {fix}")
    setup = current_setup(active[1])
    if setup is None:
        raise SystemExit(
            f"cycle {active[0]!r} of {cfg.device!r} has no setup in effect yet (all are "
            f"future-dated) — fix the [[{active[0]}.setup]] 'since' dates in its cooldowns.toml"
        )

    family = setup["backend"]
    if family == "simulated":
        return _demo_session(cfg)
    for ep in entry_points(group="scqo.backends"):
        if ep.name == family:
            backend = ep.load()(cfg, setup)  # a factory ImportError propagates with its traceback
            return make_session(backend, cfg, backend_label=family), cfg
    provider, venv = SERVED_BY[family]
    raise SystemExit(
        f"device {cfg.device!r} is on backend {family!r} (cycle {active[0]}, setup since "
        f"{setup['since']}), and that driver is not registered in this environment.\n"
        f"- wrong venv? activate D:\\github\\{venv} (the one that has {provider})\n"
        f"- already in {venv}? then {provider} was never (re)installed here: entry points\n"
        f"  register at INSTALL time — re-run its `uv pip install -e` line (INSTALL §1/§5)"
    )
