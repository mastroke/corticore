import time

from corticore.core.config import DecayConfig
from corticore.core.types import MemoryItem
from corticore.dynamics.decay import boost_on_access, decay_factor, decayed_salience


def make_item(last_accessed_at: float, salience: float = 1.0) -> MemoryItem:
    return MemoryItem(
        id="test",
        text="some memory",
        last_accessed_at=last_accessed_at,
        salience=salience,
    )


def test_decay_factor_is_one_at_zero_elapsed():
    config = DecayConfig(half_life_seconds=3600)
    now = time.time()
    item = make_item(last_accessed_at=now)
    assert decay_factor(item, config, now=now) == 1.0


def test_decay_factor_is_half_at_one_half_life():
    config = DecayConfig(half_life_seconds=3600)
    now = time.time()
    item = make_item(last_accessed_at=now - 3600)
    factor = decay_factor(item, config, now=now)
    assert abs(factor - 0.5) < 1e-9


def test_decay_factor_shrinks_over_multiple_half_lives():
    config = DecayConfig(half_life_seconds=3600)
    now = time.time()
    item = make_item(last_accessed_at=now - 3600 * 4)
    factor = decay_factor(item, config, now=now)
    assert abs(factor - 0.0625) < 1e-9  # 0.5^4


def test_decayed_salience_is_floored_at_min_salience():
    config = DecayConfig(half_life_seconds=1, min_salience=0.02)
    now = time.time()
    item = make_item(last_accessed_at=now - 1000, salience=1.0)
    assert decayed_salience(item, config, now=now) == 0.02


def test_boost_on_access_refreshes_recency_and_increments_count():
    config = DecayConfig(access_boost=0.2)
    now = time.time()
    item = make_item(last_accessed_at=now - 10_000, salience=0.5)

    boost_on_access(item, config, now=now)

    assert item.last_accessed_at == now
    assert item.access_count == 1
    assert abs(item.salience - 0.7) < 1e-9


def test_boost_on_access_caps_salience_at_one():
    config = DecayConfig(access_boost=0.5)
    item = make_item(last_accessed_at=time.time(), salience=0.9)

    boost_on_access(item, config)

    assert item.salience == 1.0
