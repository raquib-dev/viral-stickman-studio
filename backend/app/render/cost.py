"""Render cost estimator and budget cap. Pure functions; rates come from config/pricing.json."""
from __future__ import annotations

from dataclasses import dataclass, asdict


class PricingUnknown(ValueError):
    """The rate for this backend/resolution is not verified (null in pricing.json)."""


@dataclass
class CostEstimate:
    backend: str
    resolution: str
    clips: int
    seconds_per_clip: float
    rate_per_second: float
    base_usd: float
    retry_allowance: float
    max_usd: float

    def as_dict(self) -> dict:
        return asdict(self)


def rate(pricing: dict, backend: str, resolution: str) -> float:
    table = pricing.get(backend)
    if table is None:
        raise PricingUnknown(f"no pricing for backend {backend!r}")
    r = table.get(resolution)
    if r is None:
        raise PricingUnknown(f"{backend} {resolution} rate is not verified; set it in config/pricing.json first")
    return float(r)


def estimate(pricing: dict, backend: str, resolution: str, clips: int, seconds_per_clip: float = 10.0) -> CostEstimate:
    if clips < 0 or seconds_per_clip <= 0:
        raise ValueError("clips must be >= 0 and seconds_per_clip > 0")
    r = rate(pricing, backend, resolution)
    allowance = float(pricing.get("retry_allowance", 0.25))
    base = round(clips * seconds_per_clip * r, 4)
    return CostEstimate(backend, resolution, clips, seconds_per_clip, r, base, allowance,
                        round(base * (1 + allowance), 4))


def clip_cost(pricing: dict, backend: str, resolution: str, seconds: float) -> float:
    return round(seconds * rate(pricing, backend, resolution), 4)


def within_budget(spent_usd: float, next_clip_usd: float, cap_usd: float) -> bool:
    """Hard cap: never start a clip whose estimated cost would push spend past the cap."""
    return spent_usd + next_clip_usd <= cap_usd + 1e-9


def gemini_cost_from_tokens(output_tokens: int, usd_per_million: float = 17.50) -> float:
    """Actual Gemini spend from interaction.usage.total_output_tokens (pricing page: $17.50 / 1M)."""
    return round(output_tokens * usd_per_million / 1_000_000, 4)
