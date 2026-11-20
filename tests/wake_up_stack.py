"""End-to-end test stack for wake-up sources (#66).

Same shape as ``tests/native_stack.py`` (real use cases, orchestrator, routing, direct actuator,
native schedule reader and combined reader; a simulated thermostat and record store), with wake-up
sources whose values the test sets, and an optional native schedule.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from custom_components.intelligent_heating_pilot.application.actuators import (
    DirectPreheatActuator,
    RoutingPreheatActuator,
)
from custom_components.intelligent_heating_pilot.application.orchestrator import HeatingOrchestrator
from custom_components.intelligent_heating_pilot.application.slot_sources import (
    CombinedTimeslotReader,
)
from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    IPresetTemperatureResolver,
    ISchedulerOwnershipResolver,
    IWakeUpSourceReader,
)
from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ReadingIssue,
    SchedulerKind,
    WakeUpReading,
    WakeUpSourceConfig,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters import HAClimateCommander
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_scheduler_reader import (
    HAClimateSchedulerReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader import (
    HANativeScheduleReader,
    NativeScheduleSettings,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.schedule_slot_lookup import (
    HAScheduleSlotLookup,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
)
from tests.native_stack import (
    CLIMATE_ID,
    DUE_MINUTES,
    EFFECT_TIMEOUT_SECONDS,
    MONDAY_NOON,
    PRESET_TEMPERATURES,
    SCHEDULE_ID,
    WEEKDAYS,
    NativeStack,
    _FakeCalculateAnticipation,
)
from tests.unit.application.actuators.fakes import FakeClimate, FakeStore

__all__ = ["WakeUpStack", "MONDAY_NOON", "SCHEDULE_ID", "CLIMATE_ID", "DUE_MINUTES"]


class _SourceValues(IWakeUpSourceReader):
    """Gives the value the test set for each source entity."""

    def __init__(self) -> None:
        self.values: dict[str, datetime | None] = {}

    def read(self, entity_id: str) -> WakeUpReading:
        value = self.values.get(entity_id)
        return WakeUpReading(value=value) if value else WakeUpReading(issue=ReadingIssue.UNKNOWN)


class _Presets(IPresetTemperatureResolver):
    def resolve(self, preset: str) -> float | None:
        return PRESET_TEMPERATURES.get(f"{preset}_temp")


class _Resolver(ISchedulerOwnershipResolver):
    def __init__(self, sources: set[str], schedule: str | None) -> None:
        self._sources = sources
        self._schedule = schedule

    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        if scheduler_entity_id in self._sources:
            return SchedulerKind.TIMESTAMP
        if scheduler_entity_id == self._schedule:
            return SchedulerKind.NATIVE
        return SchedulerKind.UNKNOWN


class WakeUpStack(NativeStack):
    """The preheating stack over wake-up sources, with or without a native schedule."""

    def __init__(
        self,
        climate: FakeClimate,
        sources: list[WakeUpSourceConfig],
        with_schedule: bool = True,
        now: datetime = MONDAY_NOON,
        store: FakeStore | None = None,
    ) -> None:
        self.sources = sources
        self.with_schedule = with_schedule
        self.source_values = _SourceValues()
        self.timers: list[tuple[datetime, object]] = []
        super().__init__(climate, drive=True, now=now, store=store)

    def set_source(self, entity_id: str, value: datetime | None) -> None:
        """Set what a wake-up source holds; None makes it unknown."""
        self.source_values.values[entity_id] = value

    def advance(self, delta: timedelta) -> None:
        """Move the clock forward."""
        self.now = self.now + delta

    def fire_due_timers(self) -> None:
        """Run the timers that are due at the stack's current time (the end of a hold)."""
        due = [timer for timer in self.timers if timer[0] <= self.now]
        self.timers = [timer for timer in self.timers if timer not in due]
        with patch("homeassistant.util.dt.now", return_value=self.now):
            for _when, callback in due:
                asyncio.run(callback())  # type: ignore[operator]

    def restart(self) -> None:
        """Build new components over the same thermostat, schedule, sources and record."""
        self.hass = self._build_hass()
        schedulers = [self.scheduler_id] if self.with_schedule else []
        resolver = _Resolver({s.entity_id for s in self.sources}, self.scheduler_id)
        schedule_reader = HASchedulerReader(
            self.hass,
            schedulers,
            climate_entity_id=CLIMATE_ID,
            native_settings=NativeScheduleSettings(drive_enabled=True),
            ownership_resolver=resolver,
        )
        self.reader = CombinedTimeslotReader(
            scheduler_reader=schedule_reader,
            source_reader=self.source_values,
            sources=self.sources,
            preset_resolver=_Presets(),
            now=lambda: self.now,
            slot_lookup=HAScheduleSlotLookup(
                self.hass,
                schedulers,
                resolver,
                HANativeScheduleReader(self.hass, NativeScheduleSettings(drive_enabled=False)),
                HAClimateSchedulerReader(CLIMATE_ID),
                _Presets(),
            ),
            climate_reader=self.climate,  # type: ignore[arg-type]
            record_store=self.store,
        )
        direct = DirectPreheatActuator(
            commander=HAClimateCommander(self.hass, CLIMATE_ID),
            climate_reader=self.climate,  # type: ignore[arg-type]
            record_store=self.store,
            policy=PreheatSessionPolicy(),
            now=lambda: self.now,
            effect_timeout_seconds=EFFECT_TIMEOUT_SECONDS,
        )
        routes = {SchedulerKind.NATIVE: direct, SchedulerKind.TIMESTAMP: direct}
        self.control = ControlPreheatingUseCase(RoutingPreheatActuator(resolver, routes))
        timer = Mock()
        timer.schedule_timer = Mock(
            side_effect=lambda when, callback, *a, **k: (
                self.timers.append((when, callback)) or (lambda: None)
            )
        )
        action = ScheduleAnticipationActionUseCase(
            scheduler_reader=self.reader,
            timer_scheduler=timer,
            control_preheating_use_case=self.control,
        )
        self.orchestrator = HeatingOrchestrator(
            calculate_anticipation=_FakeCalculateAnticipation(self),  # type: ignore[arg-type]
            control_preheating=self.control,
            schedule_anticipation_action=action,
            update_cache=Mock(),
        )

    def recalculate(self) -> dict:
        """Run one calculate-then-schedule cycle at the stack's current time."""
        with patch("homeassistant.util.dt.now", return_value=self.now):
            return asyncio.run(self.orchestrator.calculate_and_schedule_anticipation(True))

    def _build_hass(self) -> Mock:
        hass = super()._build_hass()
        # Sources are not read through hass here, but the schedule block data is
        _ = WEEKDAYS
        return hass
