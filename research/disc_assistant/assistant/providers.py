"""Shared provider identity. Adapters are injected explicitly; no hidden fallback."""
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    version: str
    execution: Literal['local', 'remote']


class ProviderUnavailable(RuntimeError):
    """Provider transport/model unavailable; distinct from unrecognized input."""


class InvalidProviderResult(ValueError):
    """Provider output violates the application contract; never execute it."""
