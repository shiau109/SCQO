"""Lab configuration — so students run scripts without editing any repo.

One small TOML file tells every script where data goes, which device this is, and
which backend to use. Resolution order:

1. an explicit path passed to :func:`load`;
2. the ``SCQO_CONFIG`` environment variable;
3. ``~/.scqo/config.toml`` (per-user; the lab installs a canonical copy);
4. built-in defaults (simulated backend, no persistence) — everything still works,
   nothing is saved.

Example ``~/.scqo/config.toml``::

    [lab]
    data_root   = "D:/qpu_data"
    device_name = "SQ4B_v3"          # the SAMPLE (physical chip) name — never the instrument
    state_path  = "D:/qpu_data/SQ4B_v3/scqo_state.json"
    backend     = "simulated"        # "qblox" / "qm" on the control PC
    state_sync  = "pull"             # "push" only for devices SCQO fully owns
    default_tags = ["cooldown7"]     # stamped on every run; edit once per cooldown

Driver-specific keys live in their own tables (e.g. ``[qblox]``) and are passed
through untouched in :attr:`LabConfig.extras`.

**Two instruments carrying two different samples?** Each vendor table may override
``device_name`` / ``state_path`` with the sample mounted on *that* instrument —
switching ``backend`` then switches the device automatically (no second config file,
no way to write runs under the wrong sample)::

    [qblox]
    config_dir  = "D:/qpu_data/chipA/qblox_state"
    device_name = "chipA"
    state_path  = "D:/qpu_data/chipA/scqo_state.json"

    [qm]
    state_dir   = "D:/qpu_data/chipB/qm_state"
    device_name = "chipB"
    state_path  = "D:/qpu_data/chipB/scqo_state.json"

**Standing per-experiment parameter defaults** live in a second, optional TOML file —
default ``~/.scqo/parameters.toml``, overridable with ``parameters_file`` in ``[lab]``
(swap files per project) or in a vendor table (two samples, two parameter sets). One
top-level table per experiment; values sit between the code defaults and whatever the
caller passes — code defaults < this file < caller/CLI::

    [resonator_spectroscopy]
    frequency_span_hz = 15e6
    num_points = 201

A ``parameters_file`` that is named but missing raises (like a mistyped config path),
and an existing file that does not parse raises too — this file changes what gets
measured, so it never fails silently. Only the implicit default path may be absent
(code defaults apply). Tables for experiments not installed here (e.g. contrib) are
kept untouched; a typo'd KEY inside a table surfaces when that experiment runs.

**Per-user overlay** — on a multi-account server with one machine-wide shared config
(``$SCQO_CONFIG``), each account may keep ``~/.scqo/user.toml`` with PERSONAL keys
only (flat, no tables)::

    backend = "qm"                    # which instrument I measure — the sample follows
    default_tags = ["projA"]          # appended to the shared tags, deduped
    # parameters_file = "~/projB.toml"     # OPTIONAL — only to use a DIFFERENT file;
    #                                      # ~/.scqo/parameters.toml applies automatically
    #                                      # (when set, it beats the vendor table and [lab])

Any other key is rejected loudly: machine wiring (data_root, device_name, state_path,
state_sync, vendor tables) belongs to the shared lab config. The overlay applies only
on top of a FOUND base config — never to the built-in defaults. ``$SCQO_USER_CONFIG``
selects a different overlay file, or disables the overlay entirely with ``none``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .backend import Backend
from .session import Session

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib

DEFAULT_PATH = Path.home() / ".scqo" / "config.toml"
PARAMS_DEFAULT_PATH = Path.home() / ".scqo" / "parameters.toml"
USER_DEFAULT_PATH = Path.home() / ".scqo" / "user.toml"
ENV_VAR = "SCQO_CONFIG"
USER_ENV_VAR = "SCQO_USER_CONFIG"
#: The only keys a per-user overlay may set. Machine wiring (data_root, device_name,
#: state_path, state_sync, vendor tables) belongs to the shared lab config — a user
#: cannot repoint where data lands or which sample an instrument carries.
USER_ALLOWED_KEYS = ("backend", "default_tags", "parameters_file")


def _backend_family(backend: str) -> str | None:
    """The vendor table a backend reads overrides from ("qblox_sim" -> "qblox")."""
    for family in ("qblox", "qm"):
        if backend == family or backend == f"{family}_sim":
            return family
    return None


def _load_parameter_defaults(path_setting: str | None) -> tuple[dict[str, dict], Path | None]:
    """Parse the optional per-experiment parameter-defaults TOML (see module docstring).

    A ``parameters_file`` that is named but missing raises; only the implicit
    ``PARAMS_DEFAULT_PATH`` may be absent (code defaults apply, nothing to merge).
    A file that exists but does not parse — or whose top level is not experiment
    tables — raises as well: this file changes what gets measured, so it must never
    fail silently (deliberately NOT the warn-and-ignore devices.toml convention).
    """
    if path_setting is not None:
        path = Path(path_setting).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"parameters_file not found: {path}")
    else:
        path = PARAMS_DEFAULT_PATH
        if not path.is_file():
            return {}, None
    with open(path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as err:
            raise ValueError(f"invalid parameter-defaults file {path}: {err}") from None
    for name, table in raw.items():
        if not isinstance(table, dict):
            raise ValueError(
                f"{path}: top-level keys must be experiment tables like [resonator_spectroscopy]; "
                f"{name!r} belongs inside one"
            )
    return raw, path


def _load_user_overlay() -> tuple[dict, Path | None]:
    """Resolve + parse the per-user overlay (flat top-level keys, no tables).

    ``$SCQO_USER_CONFIG``: unset -> the default ``~/.scqo/user.toml`` (absent =
    silently no overlay); ``"none"``/empty -> disabled (subprocess-test hermeticity);
    a path -> that file, and a missing file raises (an explicitly named overlay never
    fails silently). Malformed TOML, a key outside :data:`USER_ALLOWED_KEYS`, or a
    wrongly typed value raise ValueError naming the file — this file changes which
    instrument a run lands on.
    """
    env = os.environ.get(USER_ENV_VAR)
    if env is not None:
        if env.strip().lower() in ("", "none"):
            return {}, None
        path = Path(env).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"${USER_ENV_VAR} points to a missing user overlay: {env}")
    else:
        path = USER_DEFAULT_PATH
        if not path.is_file():
            return {}, None
    with open(path, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as err:
            raise ValueError(f"invalid user overlay {path}: {err}") from None
    unknown = sorted(set(raw) - set(USER_ALLOWED_KEYS))
    if unknown:
        raise ValueError(
            f"{path}: key(s) {', '.join(map(repr, unknown))} are not allowed in a user overlay "
            f"(allowed: {', '.join(USER_ALLOWED_KEYS)}). Machine wiring like data_root/"
            f"device_name/state_path belongs to the shared lab config."
        )
    for key in ("backend", "parameters_file"):
        if key in raw and not isinstance(raw[key], str):
            raise ValueError(f"{path}: {key!r} must be a string, got {type(raw[key]).__name__}")
    tags = raw.get("default_tags")
    if tags is not None and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        raise ValueError(f"{path}: 'default_tags' must be a list of strings")
    return raw, path


@dataclass(frozen=True)
class LabConfig:
    """Parsed lab configuration (see module docstring for the file format)."""

    data_root: Path | None = None
    device_name: str = "device"
    state_path: Path | None = None
    backend: str = "simulated"  # scripts dispatch on this: simulated | qblox | qm
    state_sync: str = "pull"
    default_tags: list[str] = field(default_factory=list)
    parameter_defaults: dict[str, dict] = field(default_factory=dict)  # [experiment] tables from parameters.toml
    extras: dict = field(default_factory=dict)  # non-[lab] tables, passed through
    source: Path | None = None  # which file was loaded (None = built-in defaults)
    parameters_source: Path | None = None  # which parameters file was loaded (None = none found)
    user_source: Path | None = None  # which per-user overlay was applied (None = none)


def load(path: str | Path | None = None) -> LabConfig:
    """Load the lab config (explicit path -> $SCQO_CONFIG -> ~/.scqo/config.toml -> defaults).

    An explicitly named config (argument or ``$SCQO_CONFIG``) that does not exist is an
    error: silently falling back to "simulated, save nothing" would discard a day of data
    over a typo. Only the implicit ``~/.scqo/config.toml`` may be absent.
    """
    if path is not None and not Path(path).is_file():
        raise FileNotFoundError(f"lab config not found: {path}")
    env = os.environ.get(ENV_VAR)
    if path is None and env and not Path(env).is_file():
        raise FileNotFoundError(f"${ENV_VAR} points to a missing lab config: {env}")
    candidates = [Path(p) for p in (path, env, DEFAULT_PATH) if p]
    for candidate in candidates:
        if candidate.is_file():
            with open(candidate, "rb") as f:
                raw = tomllib.load(f)
            lab = raw.pop("lab", {})
            # Per-user overlay (personal keys only; applies only ON TOP of a found base
            # config — with no base config a backend switch could run a real instrument
            # unsaved). The overlaid backend is set BEFORE vendor resolution, so the
            # vendor table — and with it the sample — follows the chosen instrument.
            user, user_source = _load_user_overlay()
            if "backend" in user:
                lab["backend"] = user["backend"]
            backend = lab.get("backend", "simulated")
            # Per-backend overrides: the vendor table of the ACTIVE backend may name
            # the sample mounted on that instrument (device = the physical sample),
            # so switching backend switches device — see the module docstring.
            family = _backend_family(backend)
            vendor = raw.get(family, {}) if family else {}
            device_name = vendor.get("device_name", lab.get("device_name", "device"))
            state_path = vendor.get("state_path", lab.get("state_path"))
            # Standing parameter defaults: [lab] parameters_file, overridable per vendor
            # table (two samples want two parameter sets), else ~/.scqo/parameters.toml.
            # The user's own choice beats both (user > vendor > lab).
            params_file = vendor.get("parameters_file", lab.get("parameters_file"))
            if "parameters_file" in user:
                params_file = user["parameters_file"]
            parameter_defaults, parameters_source = _load_parameter_defaults(params_file)
            # Tags: shared (cooldown etc.) first, the user's project tags appended, deduped.
            default_tags = list(lab.get("default_tags", []))
            if user.get("default_tags"):
                default_tags = list(dict.fromkeys([*default_tags, *user["default_tags"]]))
            # expanduser: lets a config say data_root = "~/qpu_data" (macOS/Linux idiom)
            return LabConfig(
                data_root=Path(lab["data_root"]).expanduser() if lab.get("data_root") else None,
                device_name=device_name,
                state_path=Path(state_path).expanduser() if state_path else None,
                backend=backend,
                state_sync=lab.get("state_sync", "pull"),
                default_tags=default_tags,
                parameter_defaults=parameter_defaults,
                extras=raw,
                source=candidate,
                parameters_source=parameters_source,
                user_source=user_source,
            )
    # No config.toml at all: the per-user parameters file still applies — standing
    # experiment preferences are independent of the backend wiring.
    parameter_defaults, parameters_source = _load_parameter_defaults(None)
    return LabConfig(parameter_defaults=parameter_defaults, parameters_source=parameters_source)


def make_session(backend: Backend, cfg: LabConfig) -> Session:
    """Build a Session wired to the lab config (datastore, state file, default tags)."""
    return Session(
        backend,
        state_path=str(cfg.state_path) if cfg.state_path else None,
        data_root=cfg.data_root,
        device_name=cfg.device_name,
        state_sync=cfg.state_sync,  # type: ignore[arg-type]
        default_tags=cfg.default_tags,
        parameter_defaults=cfg.parameter_defaults,
        parameter_defaults_source=str(cfg.parameters_source) if cfg.parameters_source else None,
        backend_label=cfg.backend,  # provenance: "qblox_sim" vs "qblox" vs "simulated" ...
    )
