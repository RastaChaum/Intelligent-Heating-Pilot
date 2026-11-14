"""End-to-end test stack for direct control of a native schedule or a Climate Scheduler switch.

Real: the native schedule reader, the scheduling and preheating use cases, the orchestrator, the
routing and direct actuators, the preset policy and the climate commander. Faked: Home Assistant's
service layer, the thermostat (``FakeClimate``) and the record storage (``FakeStore``).

The scheduler's blocks and the clock can change between recalculations, and ``restart`` builds a
fresh set of components over the same thermostat and record, like a Home Assistant restart.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from custom_components.intelligent_heating_pilot.application.actuators import (
    DirectPreheatActuator,
    RoutingPreheatActuator,
)
from custom_components.intelligent_heating_pilot.application.orchestrator import HeatingOrchestrator
from custom_components.intelligent_heating_pilot.application.use_cases import (
    ControlPreheatingUseCase,
    ScheduleAnticipationActionUseCase,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ISchedulerOwnershipResolver,
)
from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    SchedulerKind,
    SlotAction,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
    HAClimateCommander,
    HacsRunActionActuator,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.native_schedule_reader import (
    NativeScheduleSettings,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_reader import (
    HASchedulerReader,
)
from tests.unit.application.actuators.fakes import FakeClimate, FakeStore

SCHEDULE_ID = "schedule.heating"
CLIMATE_ID = "climate.living_room"
PARIS = ZoneInfo("Europe/Paris")
MONDAY_NOON = datetime(2026, 11, 16, 12, 0, tzinfo=PARIS)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# What VTherm publishes for its presets, so that a preset slot can be anticipated
PRESET_TEMPERATURES = {"eco_temp": 18.0, "comfort_temp": 21.0, "boost_temp": 23.0}
DUE_MINUTES = 5  # the anticipated start is always this long past: the preheat is due
EFFECT_TIMEOUT_SECONDS = 0.05


class _KindResolver(ISchedulerOwnershipResolver):
    """Gives the scheduler under test its kind; any other entity is unknown."""

    def __init__(self, scheduler_id: str, kind: SchedulerKind) -> None:
        self._scheduler_id = scheduler_id
        self._kind = kind

    def resolve(self, scheduler_entity_id: str) -> SchedulerKind:
        return self._kind if scheduler_entity_id == self._scheduler_id else SchedulerKind.UNKNOWN


def block(start: str, end: str, data: dict | None = None) -> dict:
    """Build one schedule block the way ``schedule.get_schedule`` returns it."""
    result = {"from": f"{start}:00", "to": f"{end}:00"}
    if data is not None:
        result["data"] = data
    return result


class _FakeCalculateAnticipation:
    """Stands in for the learning calculation: the next slot, with its preheat always due."""

    def __init__(self, stack: NativeStack) -> None:
        self._stack = stack

    async def calculate_anticipation_datas(self, exclude_entity_ids=frozenset(), **_kwargs) -> dict:
        stack = self._stack
        timeslot = await stack.reader.get_next_timeslot(exclude_entity_ids=exclude_entity_ids)
        keys = [
            "anticipated_start_time",
            "next_schedule_time",
            "next_target_temperature",
            "anticipation_minutes",
            "current_temp",
            "learned_heating_slope",
            "confidence_level",
            "timeslot_id",
            "scheduler_entity",
            "next_slot_action",
            "dead_time",
            "humidity",
            "cloud_coverage",
        ]
        data: dict = dict.fromkeys(keys)
        if timeslot is None:
            return data
        data.update(
            anticipated_start_time=stack.now - timedelta(minutes=DUE_MINUTES),
            next_schedule_time=timeslot.target_time,
            next_target_temperature=timeslot.target_temp,
            anticipation_minutes=45,
            current_temp=17.0,
            learned_heating_slope=2.0,
            timeslot_id=timeslot.timeslot_id,
            scheduler_entity=timeslot.scheduler_entity,
            next_slot_action=timeslot.action,
        )
        return data


class NativeStack:
    """The whole preheating stack over a native schedule and a simulated thermostat."""

    def __init__(
        self,
        climate: FakeClimate,
        drive: bool = True,
        now: datetime = MONDAY_NOON,
        store: FakeStore | None = None,
        scheduler_id: str = SCHEDULE_ID,
        kind: SchedulerKind = SchedulerKind.NATIVE,
    ) -> None:
        self.climate = climate
        self.scheduler_id = scheduler_id
        self.kind = kind
        self.scheduler_attributes: dict = {}
        self.drive = drive
        self.now = now
        self.store = store or FakeStore([])
        self.blocks: list[dict] = []
        self.schedule_state = "off"
        self.service_calls: list[tuple[str, str, dict | None]] = []
        self.restart()

    def restart(self) -> None:
        """Build new components over the same thermostat, schedule and record."""
        self.hass = self._build_hass()
        settings = NativeScheduleSettings(drive_enabled=self.drive)
        resolver = _KindResolver(self.scheduler_id, self.kind)
        self.reader = HASchedulerReader(
            self.hass,
            [self.scheduler_id],
            vtherm_entity_id=CLIMATE_ID,
            native_settings=settings,
            ownership_resolver=resolver,
        )
        routes = {SchedulerKind.HACS: HacsRunActionActuator(self.hass)}
        # A native schedule is driven only on opt-in; Climate Scheduler is always driven
        if self.drive or self.kind is not SchedulerKind.NATIVE:
            routes[self.kind] = DirectPreheatActuator(
                commander=HAClimateCommander(self.hass, CLIMATE_ID),
                climate_reader=self.climate,  # type: ignore[arg-type]
                record_store=self.store,
                policy=PreheatSessionPolicy(),
                now=lambda: self.now,
                effect_timeout_seconds=EFFECT_TIMEOUT_SECONDS,
            )
        self.control = ControlPreheatingUseCase(RoutingPreheatActuator(resolver, routes))
        timer = Mock()
        timer.schedule_timer = Mock(return_value=lambda: None)
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

    def commands(self, service: str) -> list[dict | None]:
        """Return the data of every call to the given climate service so far."""
        return [data for _domain, name, data in self.service_calls if name == service]

    def _build_hass(self) -> Mock:
        hass = Mock()
        hass.is_running = True
        states = {
            self.scheduler_id: Mock(
                entity_id=self.scheduler_id,
                state=self.schedule_state,
                attributes=self.scheduler_attributes,
            ),
            CLIMATE_ID: Mock(
                entity_id=CLIMATE_ID,
                state="heat",
                attributes={"preset_temperatures": PRESET_TEMPERATURES},
            ),
        }
        hass.states.get.side_effect = states.get

        async def async_call(domain: str, service: str, data: dict | None = None, **_kwargs):
            if domain == "schedule":
                return {SCHEDULE_ID: {day: list(self.blocks) for day in WEEKDAYS}}
            self.service_calls.append((domain, service, data))
            if service == "set_preset_mode" and data:
                self.climate._take(SlotAction(preset=data["preset_mode"]))
            elif service == "set_temperature" and data:
                self.climate._take(SlotAction(temperature=data["temperature"]))
            return None

        hass.services.async_call = async_call
        return hass
