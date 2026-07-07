"""Forgetting: the lead differentiator.

Every stored memory has a `salience` (set when it's remembered, boosted each
time it's recalled) that fades exponentially with time since last access.
`recall()` ranks by decay-adjusted score, and `reflect()` prunes memories
whose decayed salience drops below `ConsolidationConfig.forget_threshold`.

This is deliberately simple (exponential half-life) so it is easy to reason
about and to replace: see `research/papers.yaml` for candidate upgrades
(e.g. Nemori-style self-organizing decay, Memoria's fateful-forgetting model).
"""

from __future__ import annotations

import math
import time

from corticore.core.config import DecayConfig
from corticore.core.types import MemoryItem


def decay_factor(item: MemoryItem, config: DecayConfig, now: float | None = None) -> float:
    """Exponential decay factor in (0, 1] based on time since last access."""
    now = now if now is not None else time.time()
    elapsed = max(0.0, now - item.last_accessed_at)
    if config.half_life_seconds <= 0:
        return 1.0
    return math.pow(0.5, elapsed / config.half_life_seconds)


def decayed_salience(item: MemoryItem, config: DecayConfig, now: float | None = None) -> float:
    """Current effective salience after decay, floored at `min_salience`."""
    factor = decay_factor(item, config, now)
    return max(config.min_salience, item.salience * factor)


def boost_on_access(item: MemoryItem, config: DecayConfig, now: float | None = None) -> None:
    """Mutate `item` in place to reflect a recall: refresh recency, bump salience."""
    now = now if now is not None else time.time()
    item.last_accessed_at = now
    item.access_count += 1
    item.salience = min(1.0, item.salience + config.access_boost)
