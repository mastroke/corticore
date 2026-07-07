"""Zero-setup defaults for corticore.

Every value here has a sane default so `Memory("agent.db")` works with no
further configuration. v2 backends/algorithms should extend this dataclass
rather than inventing parallel config paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecayConfig:
    """Controls how salience fades over time (see `dynamics/decay.py`)."""

    half_life_seconds: float = 7 * 24 * 3600  # a week, by default
    min_salience: float = 0.01
    access_boost: float = 0.15  # salience bump each time a memory is recalled


@dataclass
class ConsolidationConfig:
    """Controls `reflect()` behavior (see `dynamics/consolidate.py`)."""

    duplicate_similarity_threshold: float = 0.92
    merge_similarity_threshold: float = 0.80
    forget_threshold: float = 0.05  # prune memories whose decayed salience drops below this


@dataclass
class RetrievalConfig:
    """Controls `recall()` behavior (see `dynamics/retrieval.py`)."""

    keyword_weight: float = 0.35
    similarity_weight: float = 0.65
    default_k: int = 5


@dataclass
class Config:
    decay: DecayConfig = field(default_factory=DecayConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
