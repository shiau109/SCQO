"""What an experiment needs before it runs and what it leaves behind - as data.

Both halves are DECLARED, by catalog field name, so that nothing about an
experiment's place in the calibration order lives only in prose:

* ``Experiment.requires`` - the device values that must already be right, each
  with one line saying what the experiment uses it for. A carrier of a
  capability inherits that capability's own requirements from its Parameters
  mixin (``REQUIRES`` on the mixin, conditional on a parameter where the need
  is), so forty reset carriers do not each restate the reset wait.
* ``Experiment.writes`` - the fields ``update()`` may propose.

FROM THOSE TWO, THE CALIBRATION ORDER IS COMPUTED, never written down: joining
every experiment's ``requires`` with every experiment's ``writes`` on the field
name gives "who provides what this one needs" (:func:`writers`) and "who is
waiting on what this one measures" (:func:`dependents`). The documents and the
catalog render that join.

WHAT KEEPS IT HONEST. A name outside ``catalog.ALL_FIELD_NAMES`` fails a test,
so renaming a field breaks every declaration that mentions it, by name.
``writes`` is checked against what simulated runs actually propose
(``tests/test_experiment_outputs.py``): no experiment proposes an undeclared
field, and a documented one proposes every field it declares - so a
conditional write on an undocumented experiment is declared from reading its
``update()``, not yet exercised. ``requires`` cannot be proven complete - a
driver reads much of its state straight out of the vendor tree, where no
neutral read is recorded - so it is a reviewed list whose names are checked,
not a derived one.

WHAT IS NOT HERE: anything true of one backend only. A knob only one driver
consumes (QM's own pi/2 amplitude) is declared by that driver's subclass, which
extends ``requires`` and carries its ``backend_notes``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import (
    ALL_FIELD_NAMES,
    CHANNELS,
    COMPOSITES,
    MODES,
    OPERATION_FIELDS,
    QUBIT_LIKE,
    FieldSpec,
)


@dataclass(frozen=True)
class Requirement:
    """One device value an experiment needs to be right before it runs."""

    #: a catalog field name; the roster resolves which entity of the target
    #: owns it (``q1.drive_freq_hz`` -> the drive channel ``xy1.q1``)
    field: str
    #: what the experiment uses it for - one line, no trailing period
    why: str
    #: ``(parameter, value)`` when the need exists only for that setting;
    #: None = always
    when: tuple[str, Any] | None = None
    #: True = a STARTING value is enough - the standing one, or the design
    #: value ``Experiment.anchor()`` falls back to. This is what a bring-up
    #: experiment needs of the very field it exists to measure: somewhere to
    #: centre its window, not a calibrated number.
    seed_ok: bool = False

    def applies(self, params) -> bool:
        """Whether these Parameters put the requirement in force."""
        return self.when is None or getattr(params, self.when[0], None) == self.when[1]

    def condition(self) -> str:
        """``"reset_method=active"`` for a conditional requirement, else ``""``."""
        if self.when is None:
            return ""
        name, value = self.when
        return f"{name}={str(value).lower() if isinstance(value, bool) else value}"

    def as_dict(self) -> dict:
        return {"field": self.field, "why": self.why,
                "when": self.condition() or None, "seed_ok": self.seed_ok}


def collect(cls) -> tuple[Requirement, ...]:
    """Every requirement of experiment ``cls``: its own, then each Parameters
    mixin's ``REQUIRES`` in MRO order. The first declaration of a
    ``(field, condition)`` wins, so an experiment may restate a mixin's line
    with its own reason."""
    out: list[Requirement] = []
    seen: set[tuple[str, Any]] = set()
    mixins = [req for klass in cls.Parameters.__mro__
              for req in vars(klass).get("REQUIRES", ())]
    for req in (*cls.requires, *mixins):
        key = (req.field, req.when)
        if key not in seen:
            seen.add(key)
            out.append(req)
    return tuple(out)


def unknown_fields(names) -> list[str]:
    """The names that are not catalog fields, sorted - ``[]`` when all are."""
    return sorted(set(names) - ALL_FIELD_NAMES)


def field_spec(field: str) -> FieldSpec:
    """The catalog spec of a field name (the first kind declaring it; a name
    never means two things across kinds)."""
    for family in (MODES, COMPOSITES):
        for spec in family.values():
            if field in spec.fields:
                return spec.fields[field]
    for spec in CHANNELS.values():
        if field in spec.fields:
            return spec.fields[field]
        if field in spec.line_fields:
            return spec.line_fields[field]
    if field in OPERATION_FIELDS:
        return OPERATION_FIELDS[field]
    raise KeyError(f"{field!r} is not a catalog field")


def field_owner(field: str) -> str:
    """Which kind of entity holds a field, in words: ``"drive channel"``,
    ``"flux line"``, ``"qubit mode"``, ``"qubit_pair"``, ``"operation"``."""
    for kind, spec in CHANNELS.items():
        if field in spec.fields:
            return f"{kind} channel"
        if field in spec.line_fields:
            return f"{kind} line"
    kinds = [kind for kind, spec in MODES.items() if field in spec.fields]
    if kinds:
        if set(kinds) <= set(QUBIT_LIKE):
            return "qubit mode"
        return " / ".join(kinds) + " mode"
    kinds = [kind for kind, spec in COMPOSITES.items() if field in spec.fields]
    if kinds:
        return " / ".join(kinds)
    if field in OPERATION_FIELDS:
        return "operation"
    raise KeyError(f"{field!r} is not a catalog field")


def writers(classes) -> dict[str, list[str]]:
    """``{field: [experiments whose update() may write it]}``, names sorted."""
    out: dict[str, list[str]] = {}
    for cls in sorted(classes, key=lambda c: c.name):
        for field in cls.writes:
            out.setdefault(field, []).append(cls.name)
    return out


def dependents(classes) -> dict[str, list[str]]:
    """``{field: [experiments that require it]}``, names sorted."""
    out: dict[str, list[str]] = {}
    for cls in sorted(classes, key=lambda c: c.name):
        for field in dict.fromkeys(req.field for req in collect(cls)):
            out.setdefault(field, []).append(cls.name)
    return out
