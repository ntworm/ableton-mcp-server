from __future__ import annotations

import pytest

from AbletonMCPServer_RemoteScript import (
    _verified_attribute_boolean_steps,
    _verified_attribute_numeric_steps,
    _verified_attribute_string_steps,
)
from tests.remote_fakes import FakeAutomationEnvelope, FakeBrowser


class DeferredAttributeTarget:
    def __init__(self) -> None:
        self.value = 0.0
        self.enabled = False
        self.name = "Before"


def _completed_value(steps: object) -> object:
    with pytest.raises(StopIteration) as completed:
        next(steps)  # type: ignore[arg-type]
    return completed.value.value


def test_attribute_numeric_steps_return_observed_value() -> None:
    target = DeferredAttributeTarget()
    steps = _verified_attribute_numeric_steps(
        target,
        attribute="value",
        expected=0.75,
        result_key="value",
        retries=2,
    )
    next(steps)
    assert _completed_value(steps) == {"value": 0.75}


def test_attribute_boolean_and_string_steps_return_observed_values() -> None:
    target = DeferredAttributeTarget()
    bool_steps = _verified_attribute_boolean_steps(
        target,
        attribute="enabled",
        expected=True,
        result_key="enabled",
        retries=2,
    )
    next(bool_steps)
    assert _completed_value(bool_steps) == {"enabled": True}

    string_steps = _verified_attribute_string_steps(
        target,
        attribute="name",
        expected="After",
        result_key="name",
        retries=2,
    )
    next(string_steps)
    assert _completed_value(string_steps) == {"name": "After"}


def test_browser_and_automation_fakes_expose_required_capabilities() -> None:
    browser = FakeBrowser.with_operator()
    assert browser.instruments.children[0].name == "Operator"
    assert browser.instruments.children[0].uri == "query:Instruments#Operator"

    envelope = FakeAutomationEnvelope()
    envelope.insert_step(1.0, 0.0, 0.5)
    assert envelope.steps == [(1.0, 0.0, 0.5)]
