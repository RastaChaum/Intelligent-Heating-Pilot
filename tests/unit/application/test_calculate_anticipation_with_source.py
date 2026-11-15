"""SC-001: a source deadline is anticipated exactly like a schedule slot with the same time and target."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.slot_sources import (
    CombinedTimeslotReader,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    CalculateAnticipationUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IPresetTemperatureResolver,
    ISchedulerReader,
    IWakeUpSourceReader,
)
from custom_components.intelligent_heating_pilot.domain.services import (
    DeadTimeCalculationService,
    PredictionService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    ScheduledTimeslot,
    SlotAction,
    WakeUpReading,
    WakeUpSourceConfig,
)

NOW = datetime(2026, 11, 15, 23, 0, tzinfo=UTC)
DEADLINE = NOW + timedelta(hours=6, minutes=30)
TARGET = 21.0
ALARM = "sensor.phone_next_alarm"


def _use_case(reader: ISchedulerReader) -> CalculateAnticipationUseCase:
    environment = Mock()
    environment.get_current_environment = AsyncMock(
        return_value=EnvironmentState(
            indoor_temperature=17.0,
            outdoor_temp=5.0,
            indoor_humidity=60.0,
            cloud_coverage=None,
            timestamp=NOW,
        )
    )
    cycles = AsyncMock(spec=HeatingCycleLifecycleManager)
    cycles.get_cycles_for_target_time = AsyncMock(return_value=[])
    cycles.device_id = "device"
    lhs = AsyncMock(spec=LhsLifecycleManager)
    lhs.get_contextual_lhs = AsyncMock(return_value=2.0)
    lhs.get_global_lhs = AsyncMock(return_value=2.0)
    dead_time = Mock(spec=DeadTimeCalculationService)
    dead_time.calculate_average_dead_time = Mock(return_value=None)
    return CalculateAnticipationUseCase(
        scheduler_reader=reader,
        environment_reader=environment,
        climate_data_reader=Mock(),
        heating_cycle_manager=cycles,
        lhs_lifecycle_manager=lhs,
        prediction_service=PredictionService(),
        dead_time_calculator=dead_time,
        auto_learning=True,
        default_dead_time_minutes=0.0,
    )


def _scheduler_reader() -> ISchedulerReader:
    reader = Mock(spec=ISchedulerReader)
    reader.get_next_timeslot = AsyncMock(
        return_value=ScheduledTimeslot(
            target_time=DEADLINE, target_temp=TARGET, timeslot_id="slot", scheduler_entity="s"
        )
    )
    return reader


def _source_reader() -> ISchedulerReader:
    schedulers = Mock(spec=ISchedulerReader)
    schedulers.get_next_timeslot = AsyncMock(return_value=None)
    values = Mock(spec=IWakeUpSourceReader)
    values.read = Mock(return_value=WakeUpReading(value=DEADLINE))
    presets = Mock(spec=IPresetTemperatureResolver)
    presets.resolve = Mock(return_value=None)
    return CombinedTimeslotReader(
        schedulers,
        values,
        [WakeUpSourceConfig(ALARM, SlotAction(temperature=TARGET))],
        presets,
        lambda: NOW,
    )


@pytest.mark.asyncio
async def test_a_source_deadline_is_anticipated_like_a_schedule_slot() -> None:
    from_schedule = await _use_case(_scheduler_reader()).calculate_anticipation_datas()
    from_source = await _use_case(_source_reader()).calculate_anticipation_datas()

    assert from_source["anticipated_start_time"] == from_schedule["anticipated_start_time"]
    assert from_source["anticipation_minutes"] == from_schedule["anticipation_minutes"]
    assert from_source["next_schedule_time"] == DEADLINE
    assert from_source["next_target_temperature"] == TARGET
    assert from_source["scheduler_entity"] == ALARM
    assert from_source["anticipated_start_time"] < DEADLINE
