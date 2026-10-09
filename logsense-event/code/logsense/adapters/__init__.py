"""Deterministic syntax-adapter routing for evidence intake."""

from .registry import (
    AdapterRegistry,
    AdapterSelection,
    SyntaxAdapter,
    load_default_registry,
)

__all__ = ["AdapterRegistry", "AdapterSelection", "SyntaxAdapter", "load_default_registry"]
