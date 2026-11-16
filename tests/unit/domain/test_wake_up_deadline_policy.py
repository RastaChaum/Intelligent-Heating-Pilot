"""Tests for WakeUpDeadlinePolicy: when a source's value counts as a deadline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.wake_up_deadline_policy import (
    WakeUpDeadlinePolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ReadingIssue,
    WakeUpReading,
)

NOW = datetime(2026, 11, 15, 22, 0, tzinfo=UTC)
HORIZON = timedelta(hours=24)


@pytest.fixture
def policy() -> WakeUpDeadlinePolicy:
    return WakeUpDeadlinePolicy()


def test_a_value_inside_the_horizon_is_the_deadline(policy: WakeUpDeadlinePolicy) -> None:
    value = NOW + timedelta(hours=7)
    assert policy.judge(WakeUpReading(value=value), NOW, HORIZON) == value


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(minutes=-1), timedelta(days=-3)])
def test_now_and_the_past_give_no_deadline(policy: WakeUpDeadlinePolicy, offset: timedelta) -> None:
    assert policy.judge(WakeUpReading(value=NOW + offset), NOW, HORIZON) is None


def test_exactly_at_the_horizon_is_kept(policy: WakeUpDeadlinePolicy) -> None:
    value = NOW + HORIZON
    assert policy.judge(WakeUpReading(value=value), NOW, HORIZON) == value


def test_beyond_the_horizon_gives_no_deadline(policy: WakeUpDeadlinePolicy) -> None:
    value = NOW + HORIZON + timedelta(seconds=1)
    assert policy.judge(WakeUpReading(value=value), NOW, HORIZON) is None


@pytest.mark.parametrize("issue", list(ReadingIssue))
def test_a_reading_with_an_issue_gives_no_deadline(
    policy: WakeUpDeadlinePolicy, issue: ReadingIssue
) -> None:
    assert policy.judge(WakeUpReading(issue=issue), NOW, HORIZON) is None
