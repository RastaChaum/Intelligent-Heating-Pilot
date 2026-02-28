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
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )

        # Attempting to modify a frozen dataclass should raise FrozenInstanceError
        with pytest.raises(AttributeError):
            task.state = ExtractionTaskState.EXTRACTING

    def test_task_creation_with_default_state(self) -> None:
        """Test task creation defaults to PENDING state."""
        task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        assert task.state == ExtractionTaskState.PENDING
        assert task.error is None

    def test_task_creation_with_error_state(self) -> None:
        """Test task creation with error message."""
        error_msg = "Connection timeout"
        task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
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
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        # Should not raise any exception
        hash_value = hash(task)
        assert isinstance(hash_value, int)

    def test_task_storable_in_set(self) -> None:
        """Test that tasks can be stored in a set."""
        task1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )
        task2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 16),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        task_set = {task1, task2}
        assert len(task_set) == 2
        assert task1 in task_set
        assert task2 in task_set

    def test_task_hash_consistent_with_equality(self) -> None:
        """Test that equal tasks have the same hash (state-agnostic equality).

        This validates task deduplication: two tasks with same date and device_id
        are considered equal regardless of state or climate entity.
        """
        task1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )
        task2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.different_room",
            state=ExtractionTaskState.COMPLETED,
        )

        # Tasks should be equal based on date and device_id only
        assert task1 == task2
        assert hash(task1) == hash(task2)


class TestRecordingExtractionTaskEquality:
    """Test equality behavior of RecordingExtractionTask."""

    def test_tasks_equal_same_date_and_device_id(self) -> None:
        """Test that tasks are equal when date and device_id match."""
        task1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )
        task2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.COMPLETED,
        )

        # State difference should not affect equality
        assert task1 == task2

    def test_tasks_not_equal_different_date(self) -> None:
        """Test that tasks are not equal when dates differ."""
        task1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )
        task2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 16),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        assert task1 != task2

    def test_tasks_not_equal_different_device_id(self) -> None:
        """Test that tasks are not equal when device_ids differ."""
        task1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device_1",
            climate_entity_id="climate.living_room",
        )
        task2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device_2",
            climate_entity_id="climate.living_room",
        )

        assert task1 != task2

    def test_task_equality_with_non_task_object(self) -> None:
        """Test that task comparison with non-task returns NotImplemented."""
        task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
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
        # PENDING → EXTRACTING
        pending_task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )
        assert pending_task.state == ExtractionTaskState.PENDING

        # EXTRACTING
        extracting_task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.EXTRACTING,
        )
        assert extracting_task.state == ExtractionTaskState.EXTRACTING

        # COMPLETED
        completed_task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.COMPLETED,
        )
        assert completed_task.state == ExtractionTaskState.COMPLETED

        # FAILED
        failed_task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.FAILED,
            error="Test error",
        )
        assert failed_task.state == ExtractionTaskState.FAILED
        assert failed_task.error == "Test error"

        # CANCELLED
        cancelled_task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.CANCELLED,
        )
        assert cancelled_task.state == ExtractionTaskState.CANCELLED


class TestRecordingExtractionTaskAttributes:
    """Test RecordingExtractionTask attributes and creation."""

    def test_task_attributes_accessible(self) -> None:
        """Test that all task attributes are accessible."""
        extraction_date = date(2024, 1, 15)
        device_id = "sensor.test_device"
        climate_entity_id = "climate.living_room"

        task = RecordingExtractionTask(
            extraction_date=extraction_date,
            device_id=device_id,
            climate_entity_id=climate_entity_id,
            state=ExtractionTaskState.EXTRACTING,
            error="Test error",
        )

        assert task.extraction_date == extraction_date
        assert task.device_id == device_id
        assert task.climate_entity_id == climate_entity_id
        assert task.state == ExtractionTaskState.EXTRACTING
        assert task.error == "Test error"

    def test_task_string_representation(self) -> None:
        """Test that task has a meaningful string representation."""
        task = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        # Dataclass should have default repr
        repr_str = repr(task)
        assert "RecordingExtractionTask" in repr_str
        assert "datetime.date(2024, 1, 15)" in repr_str
        assert "sensor.test_device" in repr_str


class TestRecordingExtractionTaskDeduplicationSemantics:
    """Test that task equality and hashing enforce proper deduplication.

    Critical feature: Same (date, device_id) with different state or climate entity
    should be treated as IDENTICAL for set operations (no duplicates).
    """

    def test_task_set_deduplication_with_state_changes(self) -> None:
        """Verify set properly deduplicates tasks with different states.

        This is CRITICAL: A retry scenario where task progresses from
        PENDING → EXTRACTING → COMPLETED should still be ONE entry in cache tracking.
        """
        # Create tasks representing same extraction with different states
        task_pending = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )
        task_extracting = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.garage",  # Different entity doesn't matter
            state=ExtractionTaskState.EXTRACTING,
        )
        task_completed = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.bathroom",  # Different entity doesn't matter
            state=ExtractionTaskState.COMPLETED,
        )

        # All three tasks must deduplicate to ONE set entry
        task_set = {task_pending, task_extracting, task_completed}
        assert len(task_set) == 1, (
            "Tasks with same date+device must be equal regardless of state or climate_entity. "
            f"Expected 1 unique task, got {len(task_set)}"
        )

        # Verify hashes are identical for deduplication
        assert hash(task_pending) == hash(task_extracting) == hash(task_completed)

    def test_task_equality_ignores_climate_entity_id(self) -> None:
        """Verify equality does NOT depend on climate_entity_id.

        This allows a single device to have multiple climate entities,
        but still be tracked as same task (by device + date).
        """
        task_a = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device1",
            climate_entity_id="climate.living_room",
        )
        task_b = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device1",
            climate_entity_id="climate.garage",  # Completely different
        )

        # Must be equal even with different climate entity
        assert task_a == task_b, "Equality must ignore climate_entity_id"
        assert hash(task_a) == hash(task_b), "Hash must ignore climate_entity_id"

    def test_task_inequality_with_different_device_same_date(self) -> None:
        """Verify tasks with same date but different devices are NOT equal."""
        task_device1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device1",
            climate_entity_id="climate.living_room",
        )
        task_device2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.device2",  # Different device
            climate_entity_id="climate.living_room",
        )

        assert task_device1 != task_device2, "Different devices must NOT be equal"
        assert hash(task_device1) != hash(
            task_device2
        ), "Different devices must have different hashes"

        # Verify they create two distinct set entries
        task_set = {task_device1, task_device2}
        assert len(task_set) == 2, "Different devices should create separate set entries"

    def test_task_inequality_with_different_date_same_device(self) -> None:
        """Verify tasks with same device but different dates are NOT equal."""
        task_date1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )
        task_date2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 16),  # Different date
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
        )

        assert task_date1 != task_date2, "Different dates must NOT be equal"
        assert hash(task_date1) != hash(task_date2), "Different dates must have different hashes"

        # Verify they create two distinct set entries
        task_set = {task_date1, task_date2}
        assert len(task_set) == 2, "Different dates should create separate set entries"

    def test_task_error_message_does_not_affect_equality(self) -> None:
        """Verify error message doesn't affect equality (for deduplication).

        A failed and a retried task should be considered same for tracking.
        """
        task_failed_reason1 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.FAILED,
            error="Connection timeout",
        )
        task_failed_reason2 = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.garage",
            state=ExtractionTaskState.FAILED,
            error="Entity not found",  # Different error
        )

        # Must be equal despite different error messages
        assert task_failed_reason1 == task_failed_reason2
        assert hash(task_failed_reason1) == hash(task_failed_reason2)

    def test_task_set_preservation_of_arbitrary_entry(self) -> None:
        """Verify set preserves one arbitrary entry when duplicates exist.

        Python sets keep only ONE of equal objects. Test verifies this behavior
        for our task equality semantics.
        """
        task_pending = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.living_room",
            state=ExtractionTaskState.PENDING,
        )
        task_completed = RecordingExtractionTask(
            extraction_date=date(2024, 1, 15),
            device_id="sensor.test_device",
            climate_entity_id="climate.garage",
            state=ExtractionTaskState.COMPLETED,
        )

        task_set = {task_pending, task_completed}
        assert len(task_set) == 1

        # Set contains exactly ONE of the two (which one is unpredictable, but only one)
        retrieved_task = task_set.pop()
        assert retrieved_task == task_pending
        assert retrieved_task == task_completed
        assert retrieved_task.device_id == "sensor.test_device"
        assert retrieved_task.extraction_date == date(2024, 1, 15)
