"""Provider capability declarations and health status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a data provider can do — declared, never guessed.

    ``verified_live`` is True only when the provider's endpoint was actually
    called successfully from the build/verification environment. Providers
    with ``verified_live=False`` are labeled "unverified" everywhere.
    """

    name: str
    pairs: tuple[str, ...]  # supported symbols; ("*",) = any configured pair
    intervals: tuple[str, ...] = ("1d",)
    history_depth_days: int | None = None  # None = as far back as available
    rate_limit_per_minute: int | None = None
    latency_typical_ms: int | None = None
    license_notes: str = ""
    requires_key: bool = False
    verified_live: bool = False
    is_demo: bool = False

    def supports_pair(self, pair: str) -> bool:
        return "*" in self.pairs or pair.upper() in self.pairs

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "pairs": list(self.pairs),
            "intervals": list(self.intervals),
            "history_depth_days": self.history_depth_days,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "latency_typical_ms": self.latency_typical_ms,
            "license_notes": self.license_notes,
            "requires_key": self.requires_key,
            "verified_live": self.verified_live,
            "is_demo": self.is_demo,
        }


@dataclass
class ProviderHealth:
    """Result of a provider health check."""

    name: str
    reachable: bool
    checked_at: datetime
    latency_ms: float | None = None
    detail: str = ""
    circuit_state: str = "closed"  # closed | open | half_open

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "reachable": self.reachable,
            "checked_at": self.checked_at.isoformat(),
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "circuit_state": self.circuit_state,
        }
