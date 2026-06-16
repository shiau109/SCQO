"""Experiment registry — the catalog an AI agent chooses from.

A driver registers its concrete experiments at import time::

    from scqo import register
    @register
    class QbloxResonatorSpectroscopy(ResonatorSpectroscopy):
        def probe(self): ...

``catalog()`` then returns a JSON-friendly menu (name + description + parameter
schema) — the agent's list of available measurement approaches.

Drivers do not need the consumer to import their experiments package by hand: each
advertises it under the ``scqo.experiments`` entry-point group, and ``catalog()``/``get()``
discover and import them on first use (which runs their ``@register`` decorators).
"""

from __future__ import annotations

from importlib.metadata import entry_points

from .experiment import Experiment

_REGISTRY: dict[str, type[Experiment]] = {}
_ENTRY_POINT_GROUP = "scqo.experiments"
_discovered = False


def _discover() -> None:
    """Import every installed driver's experiments so the catalog is complete.

    Each driver advertises its experiments package under the ``scqo.experiments``
    entry-point group; loading it runs that package's ``@register`` decorators. Idempotent,
    and tolerant of a backend that fails to import (e.g. its vendor library is absent) — the
    offending backend is simply skipped rather than breaking discovery for the rest.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        try:
            ep.load()
        except Exception:
            continue


def register(cls: type[Experiment]) -> type[Experiment]:
    """Class decorator: add a concrete experiment to the catalog (keyed by ``cls.name``)."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must define a class-level `name` to be registered.")
    _REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> type[Experiment]:
    """Look up a registered experiment class by name."""
    _discover()
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown experiment {name!r}. Available: {sorted(_REGISTRY)}") from None


def catalog() -> list[dict]:
    """Return ``[{name, description, parameters_schema}, ...]`` for every registered experiment."""
    _discover()
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "parameters_schema": cls.Parameters.model_json_schema(),
        }
        for cls in _REGISTRY.values()
    ]
