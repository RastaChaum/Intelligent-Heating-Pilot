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
    """Test that RecordingExtractionTask is hashable."""

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
        """Test that equal tasks have the same hash."""
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
