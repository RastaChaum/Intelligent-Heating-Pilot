"""Build a small real home: a Versatile Thermostat, a scheduler and IHP, in the test ``hass``.

Only the physical devices (room and outdoor sensors, the heater switch) are simulated. The
thermostat, the schedulers and IHP are the real integrations, so a scenario exercises service
calls, entity attributes and timers exactly as they behave in a live Home Assistant.

A scenario reads like the user story: build a ``Home``, ``install`` a scheduler with blocks,
``start_ihp``, then move the clock and look at the thermostat.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from custom_components.versatile_thermostat.const import (
    CONF_CYCLE_MIN,
    CONF_DEVICE_POWER,
    CONF_EXTERNAL_TEMP_SENSOR,
    CONF_NAME,
    CONF_PROP_FUNCTION,
    CONF_STEP_TEMPERATURE,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_SENSOR,
    CONF_THERMOSTAT_SWITCH,
    CONF_THERMOSTAT_TYPE,
    CONF_TPI_COEF_EXT,
    CONF_TPI_COEF_INT,
    CONF_UNDERLYING_LIST,
    CONF_USE_MAIN_CENTRAL_CONFIG,
    PROPORTIONAL_FUNCTION_TPI,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import Event, HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.intelligent_heating_pilot.const import (
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DOMAIN,
)

PARIS = "Europe/Paris"
# Half a second past the hour on purpose: HACS Scheduler only accepts a manual run of a slot when
# "now" is strictly after its start, which the live clock's microseconds always satisfy but a
# clock on a round second does not. The test clock then only ever moves by whole seconds.
MONDAY_5AM = "2026-11-16 05:00:00.500000+01:00"
ROOM_SENSOR = "sensor.room_temperature"
OUTDOOR_SENSOR = "sensor.outdoor_temperature"
HEATER_SWITCH = "switch.heater"
THERMOSTAT = "climate.room"
PRESET_NUMBER = "number.room_preset_{preset}_temp"
ANTICIPATED_START = "sensor.intelligent_heating_pilot_anticipated_start_time"
IHP_SWITCH = "switch.intelligent_heating_pilot_ihp_preheating"
NEXT_DEADLINE = "sensor.intelligent_heating_pilot_next_schedule_time"
THERMOSTAT_MIN_C = 15
THERMOSTAT_MAX_C = 30
THERMOSTAT_STEP_C = 0.5
TPI_COEF_INT = 0.3
TPI_COEF_EXT = 0.1
CYCLE_MINUTES = 5
ECO_C = 17.0
COMFORT_C = 21.0
BOOST_C = 23.0
COLD_ROOM_C = 18.0
YIELDS_PER_STEP = 30
MAX_CLOCK_STEP_SECONDS = 60
STARTUP_SETTLE = timedelta(minutes=2)
PAST_DUE = timedelta(minutes=1)
# A live room sensor never stays silent: it reports now and then, and IHP recalculates on it
SENSOR_REPORT_INTERVAL = timedelta(minutes=10)
SENSOR_JITTER_C = 0.1
MAX_START_REALIGNMENTS = 5


def vtherm_entry_data(
    name: str, room_sensor: str, outdoor_sensor: str, heater: str
) -> dict[str, Any]:
    """The configuration of a Versatile Thermostat over one switch, TPI-regulated."""
    return {
        CONF_NAME: name,
        CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_SWITCH,
        CONF_TEMP_SENSOR: room_sensor,
        CONF_EXTERNAL_TEMP_SENSOR: outdoor_sensor,
        CONF_CYCLE_MIN: CYCLE_MINUTES,
        CONF_DEVICE_POWER: 1,
        CONF_USE_MAIN_CENTRAL_CONFIG: False,
        CONF_UNDERLYING_LIST: [heater],
        CONF_PROP_FUNCTION: PROPORTIONAL_FUNCTION_TPI,
        CONF_TPI_COEF_INT: TPI_COEF_INT,
        CONF_TPI_COEF_EXT: TPI_COEF_EXT,
        CONF_TEMP_MIN: THERMOSTAT_MIN_C,
        CONF_TEMP_MAX: THERMOSTAT_MAX_C,
        CONF_STEP_TEMPERATURE: THERMOSTAT_STEP_C,
    }


@dataclass(frozen=True)
class Block:
    """One slot of a heating plan: from ``time`` on, the thermostat takes this action."""

    time: str
    preset: str | None = None
    temperature: float | None = None
    data: Mapping[str, Any] | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Command:
    """A ``climate`` service call seen on the bus, whoever sent it."""

    service: str
    data: Mapping[str, Any]


def _seconds_to_next_timer(hass: HomeAssistant) -> float | None:
    """How long until the event loop's next timer is due, or None when there is none."""
    now = hass.loop.time()
    # The scheduled handles are asyncio's own bookkeeping; there is no public way to ask
    due = [h.when() - now for h in getattr(hass.loop, "_scheduled", ()) if not h.cancelled()]
    return min(due) if due else None


def _next_step(hass: HomeAssistant, left: timedelta) -> timedelta:
    """Up to the next due timer, in whole seconds so the clock keeps its sub-second offset."""
    until_timer = _seconds_to_next_timer(hass)
    seconds = MAX_CLOCK_STEP_SECONDS if until_timer is None else math.ceil(until_timer)
    return min(left, timedelta(seconds=min(max(seconds, 1), MAX_CLOCK_STEP_SECONDS)))


async def advance(hass: HomeAssistant, clock: FrozenDateTimeFactory, by: timedelta) -> None:
    """Move the frozen clock forward from timer to timer, letting what is due run at each one.

    Components wait with ``asyncio.sleep`` and with timeouts, which only elapse when the clock
    is advanced and the due timers are fired. One big jump would skip the waits that sit
    between two actions (a component that sleeps before acting would never get to act), so each
    step stops at the next timer that is due.
    """
    left = by
    while left > timedelta():
        step = _next_step(hass, left)
        clock.tick(step)
        left -= step
        async_fire_time_changed(hass)
        for _ in range(YIELDS_PER_STEP):
            await asyncio.sleep(0)


class Home:
    """A home with one cold room heated by a real Versatile Thermostat."""

    def __init__(self, hass: HomeAssistant, clock: FrozenDateTimeFactory) -> None:
        self.hass = hass
        self.clock = clock
        self.commands: list[Command] = []
        self.ihp_entry: MockConfigEntry | None = None
        self._ihp_entities: list[str] = []
        self._ihp_options: dict[str, Any] = {}
        self._room_c = COLD_ROOM_C
        self._sensor_high = False

    @classmethod
    async def build(
        cls,
        hass: HomeAssistant,
        clock: FrozenDateTimeFactory,
        room_c: float = COLD_ROOM_C,
        outdoor_c: float = 5.0,
    ) -> Home:
        """A Monday at 05:00 in Paris, the room cold and resting in its eco preset."""
        await hass.config.async_set_time_zone(PARIS)
        clock.move_to(MONDAY_5AM)
        home = cls(hass, clock)
        home._room_c = room_c
        await home._add_thermostat(room_c, outdoor_c)
        await home.user_selects_hvac_mode("heat")
        await home.set_preset_temperatures(comfort=COMFORT_C, eco=ECO_C, boost=BOOST_C)
        # Versatile Thermostat publishes a preset's temperature in its attributes only once that
        # preset has been selected, so the user goes through each one before the room rests.
        for preset in ("boost", "comfort", "eco"):
            await home.user_selects_preset(preset)
        home._record_commands()
        return home

    # --- the room -----------------------------------------------------------------------

    async def _add_thermostat(self, room_c: float, outdoor_c: float) -> None:
        hass = self.hass
        hass.states.async_set(ROOM_SENSOR, str(room_c))
        hass.states.async_set(OUTDOOR_SENSOR, str(outdoor_c))
        hass.states.async_set(HEATER_SWITCH, "off")
        async_mock_service(hass, "switch", "turn_on")
        async_mock_service(hass, "switch", "turn_off")
        entry = MockConfigEntry(
            domain="versatile_thermostat",
            title="Room",
            data=vtherm_entry_data("Room", ROOM_SENSOR, OUTDOOR_SENSOR, HEATER_SWITCH),
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    def set_room_temperature(self, celsius: float) -> None:
        """The room is now this warm; the sensor keeps reporting around it."""
        self._room_c = celsius
        self.hass.states.async_set(ROOM_SENSOR, str(celsius))

    async def set_preset_temperatures(self, **celsius_by_preset: float) -> None:
        """Give the thermostat presets their temperature, the way a user does in the UI."""
        for preset, celsius in celsius_by_preset.items():
            await self.hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": PRESET_NUMBER.format(preset=preset), "value": celsius},
                blocking=True,
            )
            await self.hass.async_block_till_done()

    def _record_commands(self) -> None:
        def _on_call(event: Event) -> None:
            if event.data["domain"] == "climate":
                self.commands.append(Command(event.data["service"], event.data["service_data"]))

        self.hass.bus.async_listen("call_service", _on_call)

    def forget_commands(self) -> None:
        """Start counting commands from here."""
        self.commands.clear()

    def commands_to_thermostat(self) -> list[Command]:
        """The ``climate`` commands that targeted the thermostat since the last reset."""
        return [c for c in self.commands if _targets(c, THERMOSTAT)]

    @property
    def preset(self) -> str:
        return str(self.hass.states.get(THERMOSTAT).attributes["preset_mode"])

    @property
    def target(self) -> float:
        return float(self.hass.states.get(THERMOSTAT).attributes["temperature"])

    async def user_selects_preset(self, preset: str) -> None:
        """Somebody picks a preset on the thermostat (no parent context: a real manual change)."""
        await self.hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": THERMOSTAT, "preset_mode": preset},
            blocking=True,
        )

    async def user_sets_temperature(self, celsius: float) -> None:
        """Somebody sets a target by hand, which leaves any preset."""
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": THERMOSTAT, "temperature": celsius},
            blocking=True,
        )

    async def user_selects_hvac_mode(self, mode: str) -> None:
        await self.hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": THERMOSTAT, "hvac_mode": mode}, blocking=True
        )

    # --- IHP ----------------------------------------------------------------------------

    async def start_ihp(
        self, scheduler_entities: list[str] | None = None, **options: Any
    ) -> MockConfigEntry:
        """Set up IHP on the thermostat, watching the given scheduler entities."""
        self._ihp_entities = list(scheduler_entities or [])
        self._ihp_options = dict(options)
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="IHP",
            data={CONF_VTHERM_ENTITY: THERMOSTAT, CONF_SCHEDULER_ENTITIES: self._ihp_entities},
            options=self._ihp_options,
        )
        entry.add_to_hass(self.hass)
        assert await self.hass.config_entries.async_setup(entry.entry_id)
        await self.hass.async_block_till_done()
        self.ihp_entry = entry
        return entry

    async def restart_ihp(self) -> None:
        """Unload and set IHP up again: what Home Assistant does on a restart."""
        assert self.ihp_entry is not None
        await self.hass.config_entries.async_unload(self.ihp_entry.entry_id)
        assert await self.hass.config_entries.async_setup(self.ihp_entry.entry_id)
        await self.hass.async_block_till_done()

    async def turn_ihp_off(self) -> None:
        """Flip IHP's own preheating switch."""
        await self.hass.services.async_call(
            "switch", "turn_off", {"entity_id": IHP_SWITCH}, blocking=True
        )

    # --- time ---------------------------------------------------------------------------

    @property
    def now(self) -> datetime:
        return dt_util.now()

    def at(self, clock_time: str, day_offset: int = 0) -> datetime:
        """A local time of the current day (or another), such as ``"07:00"``."""
        hour, minute = (int(part) for part in clock_time.split(":"))
        day = self.now + timedelta(days=day_offset)
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    async def advance(self, by: timedelta) -> None:
        """Move the clock, with the room sensor reporting a slightly different value regularly."""
        remaining = by
        while remaining > timedelta():
            chunk = min(SENSOR_REPORT_INTERVAL, remaining)
            await advance(self.hass, self.clock, chunk)
            remaining -= chunk
            if chunk == SENSOR_REPORT_INTERVAL:
                self._report_room_temperature()

    def _report_room_temperature(self) -> None:
        self._sensor_high = not self._sensor_high
        base = self._room_c
        self.hass.states.async_set(
            ROOM_SENSOR, str(base + (SENSOR_JITTER_C if self._sensor_high else 0))
        )

    async def advance_to(self, when: datetime) -> None:
        """Move the clock to a point in time, which must not be in the past."""
        await self.advance(when - self.now)

    async def settle(self) -> None:
        """Let IHP run its first recalculation after a start."""
        await self.advance(STARTUP_SETTLE)

    @property
    def anticipated_start(self) -> datetime | None:
        state = self.hass.states.get(ANTICIPATED_START)
        parsed = dt_util.parse_datetime(state.state) if state is not None else None
        return dt_util.as_local(parsed) if parsed is not None else None

    @property
    def next_deadline(self) -> datetime | None:
        """The next moment IHP preheats for: a schedule slot or a wake-up source."""
        state = self.hass.states.get(NEXT_DEADLINE)
        parsed = dt_util.parse_datetime(state.state) if state is not None else None
        return dt_util.as_local(parsed) if parsed is not None else None

    async def reach_anticipated_start(self) -> datetime:
        """Move just past the anticipated start and return it.

        The sensor keeps reporting, so IHP may move its start by a few minutes on the way: the
        clock follows it until it is behind us.
        """
        anticipated = self.anticipated_start
        assert anticipated is not None, "IHP has not anticipated any start"
        for _ in range(MAX_START_REALIGNMENTS):
            await self.advance_to(max(self.now, anticipated + PAST_DUE))
            latest = self.anticipated_start
            if latest is None or latest + PAST_DUE <= self.now:
                break
            anticipated = latest
        return anticipated


def _targets(command: Command, entity_id: str) -> bool:
    target = command.data.get("entity_id")
    return target == entity_id or (isinstance(target, list) and entity_id in target)
