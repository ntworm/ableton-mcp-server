from __future__ import annotations

import dataclasses

import pytest

from groove_lab.dataset.config import BuildConfig


def test_defaults_match_the_specification() -> None:
    config = BuildConfig()
    assert config.steps == 32
    assert config.lanes == 18
    assert config.bars == 2
    assert config.grid_division == 16
    assert config.condition_dimensions == 16
    assert config.short_file_policy == "looped"
    assert config.split_ratios == (0.8, 0.1, 0.1)
    assert config.max_cluster_share == 0.05
    assert config.representation_loss_budget == 0.04
    assert config.seed == 20260831


def test_config_is_frozen() -> None:
    config = BuildConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.steps = 64  # type: ignore[misc]


def test_digest_is_stable_and_sensitive() -> None:
    assert BuildConfig().digest() == BuildConfig().digest()
    assert BuildConfig().digest() != BuildConfig(short_file_policy="padded").digest()
    assert len(BuildConfig().digest()) == 64


def test_short_file_policy_is_restricted() -> None:
    with pytest.raises(ValueError):
        BuildConfig(short_file_policy="whatever")
