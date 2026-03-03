"""Tests for RecordingExtractionTask value object."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.recording_extraction_task import (
    ExtractionTaskState,
    RecordingExtractionTask,
)


class TestRecordingExtractionTaskImmutability:
    """Test that RecordingExtractionTask is immutable (frozen dataclass)."""

    def test_task_is_frozen_dataclass(self) -> None:
        """Test that task is immutable (frozen=True)."""
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.PENDING,
        )

        with pytest.raises(AttributeError):
            task.state = ExtractionTaskState.EXTRACTING

    def test_task_creation_with_default_state(self) -> None:
        """Test task creation defaults to PENDING state."""
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )

        assert task.state == ExtractionTaskState.PENDING
        assert task.error is None

    def test_task_creation_with_error_state(self) -> None:
        """Test task creation with error message."""
        error_msg = "Connection timeout"
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.FAILED,
            error=error_msg,
        )

        assert task.state == ExtractionTaskState.FAILED
        assert task.error == error_msg


class TestRecordingExtractionTaskHashability:
    """Test that RecordingExtractionTask is hashable and deduplicates correctly."""

    def test_task_is_hashable(self) -> None:
        """Test that task can be hashed."""
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )

        hash_value = hash(task)
        assert isinstance(hash_value, int)

    def test_task_storable_in_set(self) -> None:
        """Test that tasks can be stored in a set."""
        task1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )
        task2 = RecordingExtractionTask(
            start_date=date(2024, 1, 22),
            end_date=date(2024, 1, 28),
            device_id="sensor.test_device",
        )

        task_set = {task1, task2}
        assert len(task_set) == 2
        assert task1 in task_set
        assert task2 in task_set

    def test_task_hash_consistent_with_equality(self) -> None:
        """Test that equal tasks have the same hash (state-agnostic equality)."""
        task1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.PENDING,
        )
        task2 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.COMPLETED,
        )

        assert task1 == task2
        assert hash(task1) == hash(task2)


class TestRecordingExtractionTaskEquality:
    """Test equality behavior of RecordingExtractionTask."""

    def test_tasks_equal_same_period_and_device_id(self) -> None:
        """Test that tasks are equal when period and device_id match."""
        task1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.PENDING,
        )
        task2 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.COMPLETED,
        )

        assert task1 == task2

    def test_tasks_not_equal_different_start_date(self) -> None:
        """Test that tasks are not equal when start_dates differ."""
        task1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )
        task2 = RecordingExtractionTask(
            start_date=date(2024, 1, 22),
            end_date=date(2024, 1, 28),
            device_id="sensor.test_device",
        )

        assert task1 != task2

    def test_tasks_not_equal_different_device_id(self) -> None:
        """Test that tasks are not equal when device_ids differ."""
        task1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.device_1",
        )
        task2 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.device_2",
        )

        assert task1 != task2

    def test_task_equality_with_non_task_object(self) -> None:
        """Test that task comparison with non-task returns False."""
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )

        assert task != "not a task"
        assert task != 123
        assert task != date(2024, 1, 15)


class TestExtractionTaskState:
    """Test ExtractionTaskState enum."""

    def test_all_states_defined(self) -> None:
        """Test that all expected states are defined."""
        assert ExtractionTaskState.PENDING.value == "pending"
        assert ExtractionTaskState.EXTRACTING.value == "extracting"
        assert ExtractionTaskState.COMPLETED.value == "completed"
        assert ExtractionTaskState.FAILED.value == "failed"
        assert ExtractionTaskState.CANCELLED.value == "cancelled"

    def test_state_transitions_are_possible(self) -> None:
        """Test creating tasks with different state transitions."""
        start = date(2024, 1, 15)
        end = date(2024, 1, 21)
        device = "sensor.test_device"

        pending_task = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.PENDING,
        )
        assert pending_task.state == ExtractionTaskState.PENDING

        extracting_task = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.EXTRACTING,
        )
        assert extracting_task.state == ExtractionTaskState.EXTRACTING

        completed_task = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.COMPLETED,
        )
        assert completed_task.state == ExtractionTaskState.COMPLETED

        failed_task = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.FAILED,
            error="Test error",
        )
        assert failed_task.state == ExtractionTaskState.FAILED
        assert failed_task.error == "Test error"

        cancelled_task = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.CANCELLED,
        )
        assert cancelled_task.state == ExtractionTaskState.CANCELLED


class TestRecordingExtractionTaskAttributes:
    """Test RecordingExtractionTask attributes and creation."""

    def test_task_attributes_accessible(self) -> None:
        """Test that all task attributes are accessible."""
        start_date = date(2024, 1, 15)
        end_date = date(2024, 1, 21)
        device_id = "sensor.test_device"

        task = RecordingExtractionTask(
            start_date=start_date,
            end_date=end_date,
            device_id=device_id,
            state=ExtractionTaskState.EXTRACTING,
            error="Test error",
        )

        assert task.start_date == start_date
        assert task.end_date == end_date
        assert task.device_id == device_id
        assert task.state == ExtractionTaskState.EXTRACTING
        assert task.error == "Test error"

    def test_task_string_representation(self) -> None:
        """Test that task has a meaningful string representation."""
        task = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )

        repr_str = repr(task)
        assert "RecordingExtractionTask" in repr_str
        assert "sensor.test_device" in repr_str


class TestRecordingExtractionTaskDeduplicationSemantics:
    """Test that task equality and hashing enforce proper deduplication."""

    def test_task_set_deduplication_with_state_changes(self) -> None:
        """Verify set properly deduplicates tasks with different states."""
        start = date(2024, 1, 15)
        end = date(2024, 1, 21)
        device = "sensor.test_device"

        task_pending = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.PENDING,
        )
        task_extracting = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.EXTRACTING,
        )
        task_completed = RecordingExtractionTask(
            start_date=start, end_date=end, device_id=device,
            state=ExtractionTaskState.COMPLETED,
        )

        task_set = {task_pending, task_extracting, task_completed}
        assert len(task_set) == 1
        assert hash(task_pending) == hash(task_extracting) == hash(task_completed)

    def test_task_inequality_with_different_device_same_period(self) -> None:
        """Verify tasks with same period but different devices are NOT equal."""
        task_device1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.device1",
        )
        task_device2 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.device2",
        )

        assert task_device1 != task_device2
        assert hash(task_device1) != hash(task_device2)
        assert len({task_device1, task_device2}) == 2

    def test_task_inequality_with_different_period_same_device(self) -> None:
        """Verify tasks with same device but different periods are NOT equal."""
        task_period1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
        )
        task_period2 = RecordingExtractionTask(
            start_date=date(2024, 1, 22),
            end_date=date(2024, 1, 28),
            device_id="sensor.test_device",
        )

        assert task_period1 != task_period2
        assert hash(task_period1) != hash(task_period2)
        assert len({task_period1, task_period2}) == 2

    def test_task_error_message_does_not_affect_equality(self) -> None:
        """Verify error message does not affect equality."""
        task_failed_reason1 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.FAILED,
            error="Connection timeout",
        )
        task_failed_reason2 = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.FAILED,
            error="Entity not found",
        )

        assert task_failed_reason1 == task_failed_reason2
        assert hash(task_failed_reason1) == hash(task_failed_reason2)

    def test_task_set_preservation_of_arbitrary_entry(self) -> None:
        """Verify set preserves one arbitrary entry when duplicates exist."""
        task_pending = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.PENDING,
        )
        task_completed = RecordingExtractionTask(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 21),
            device_id="sensor.test_device",
            state=ExtractionTaskState.COMPLETED,
        )

        task_set = {task_pending, task_completed}
        assert len(task_set) == 1

        retrieved_task = task_set.pop()
        assert retrieved_task == task_pending
        assert retrieved_task == task_completed
        assert retrieved_task.device_id == "sensor.test_device"
        assert retrieved_task.start_date == date(2024, 1, 15)
        assert retrieved_task.end_date == date(2024, 1, 21)
