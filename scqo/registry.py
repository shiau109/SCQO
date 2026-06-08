"""Experiment registry — the catalog an AI agent chooses from.

A driver registers its concrete experiments at import time::

    from scqo import register
    @register
    class QbloxResonatorSpectroscopy(ResonatorSpectroscopy):
        def probe(self): ...

``catalog()`` then returns a JSON-friendly menu (name + description + parameter
schema) — the agent's list of available measurement approaches.
"""

from __future__ import annotations

from .experiment import Experiment

_REGISTRY: dict[str, type[Experiment]] = {}


def register(cls: type[Experiment]) -> type[Experiment]:
    """Class decorator: add a concrete experiment to the catalog (keyed by ``cls.name``)."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must define a class-level `name` to be registered.")
    _REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> type[Experiment]:
    """Look up a registered experiment class by name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown experiment {name!r}. Available: {sorted(_REGISTRY)}") from None


def catalog() -> list[dict]:
    """Return ``[{name, description, parameters_schema}, ...]`` for every registered experiment."""
    return [
        {
            "name": cls.name,
            "description": cls.description,
            "parameters_schema": cls.Parameters.model_json_schema(),
        }
        for cls in _REGISTRY.values()
    ]
