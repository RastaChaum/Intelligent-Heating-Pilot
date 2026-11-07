"""pytest-bdd step definitions for outdoor conditions scenarios.

Covers the path from configuration to the environment seen by the prediction:
the configured outdoor sources are read through HADeviceConfigReader, then
HAEnvironmentReader turns sensor or weather entity states into an EnvironmentState.
Also covers the outdoor temperature recorded with each extracted heating cycle,
and that outdoor temperature no longer inflates the anticipation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import State
from pytest_bdd import given, parsers, scenarios, then, when

from custom_components.intelligent_heating_pilot.const import (
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_VTHERM_ENTITY,
)
from custom_components.intelligent_heating_pilot.domain.interfaces import (
    ILhsStorage,
    ISchedulerReader,
)
from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import (
    HeatingCycleService,
)
from custom_components.intelligent_heating_pilot.domain.services.simple_decision_strategy import (
    SimpleDecisionStrategy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HeatingAction,
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
    ScheduledTimeslot,
)
from custom_components.intelligent_heating_pilot.heating_application import HeatingApplication
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.environment_reader import (
    HAEnvironmentReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.outdoor_temperature_history_reader import (
    HAOutdoorTemperatureHistoryReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)

scenarios("outdoor_conditions.feature")

VTHERM_ENTITY_ID = "climate.living_room"
INDOOR_TEMPERATURE = 19.0
DAY = datetime(2026, 1, 15)
HEATING = {"hvac_action": "heating", "hvac_mode": "heat"}
IDLE = {"hvac_action": "idle", "hvac_mode": "heat"}


def _at(clock: str) -> datetime:
    hours, minutes = (int(part) for part in clock.split(":"))
    return DAY.replace(hour=hours, minute=minutes)


@pytest.fixture
def outdoor_context() -> dict:
    """Shared context: config entry data, HA states and results."""
    return {
        "data": {CONF_VTHERM_ENTITY: VTHERM_ENTITY_ID},
        "states": {
            VTHERM_ENTITY_ID: State(
                VTHERM_ENTITY_ID, "heat", {"current_temperature": INDOOR_TEMPERATURE}
            )
        },
    }


def _make_hass(outdoor_context: dict) -> Mock:
    hass = Mock()
    hass.states.get = Mock(side_effect=outdoor_context["states"].get)
    return hass


# ------------------------------------------------------------------
# Given
# ------------------------------------------------------------------


@given(parsers.parse('the outdoor temperature source is "{entity_id}"'))
def outdoor_temperature_source(outdoor_context: dict, entity_id: str) -> None:
    """GIVEN: The user configured an outdoor temperature source."""
    outdoor_context["data"][CONF_TEMPERATURE_OUT_ENTITY] = entity_id


@given(parsers.parse('the outdoor humidity source is "{entity_id}"'))
def outdoor_humidity_source(outdoor_context: dict, entity_id: str) -> None:
    """GIVEN: The user configured an outdoor humidity source."""
    outdoor_context["data"][CONF_HUMIDITY_OUT_ENTITY] = entity_id


@given(parsers.parse('the cloud coverage source is "{entity_id}"'))
def cloud_coverage_source(outdoor_context: dict, entity_id: str) -> None:
    """GIVEN: The user configured a cloud coverage source."""
    outdoor_context["data"][CONF_CLOUD_COVER_ENTITY] = entity_id


@given(parsers.parse('"{entity_id}" reports {value:f} "{unit}"'))
def sensor_reports(outdoor_context: dict, entity_id: str, value: float, unit: str) -> None:
    """GIVEN: A sensor reports a value in its unit."""
    outdoor_context["states"][entity_id] = State(
        entity_id, str(value), {"unit_of_measurement": unit}
    )


@given(
    parsers.parse(
        '"{entity_id}" is "{condition}" with temperature {temperature:f} "{unit}", '
        "humidity {humidity:d} and cloud coverage {cloud:d}"
    )
)
def weather_reports(
    outdoor_context: dict,
    entity_id: str,
    condition: str,
    temperature: float,
    unit: str,
    humidity: int,
    cloud: int,
) -> None:
    """GIVEN: A weather entity reports its condition and numeric attributes."""
    outdoor_context["states"][entity_id] = State(
        entity_id,
        condition,
        {
            "temperature": temperature,
            "temperature_unit": unit,
            "humidity": humidity,
            "cloud_coverage": cloud,
        },
    )


@given(parsers.parse('IHP monitors the outdoor source "{entity_id}"'))
def ihp_monitors(outdoor_context: dict, entity_id: str) -> None:
    """GIVEN: The event bridge listens to the outdoor source."""
    bridge = HAEventBridge(
        hass=Mock(),
        orchestrator=AsyncMock(),
        vtherm_entity_id=VTHERM_ENTITY_ID,
        scheduler_entity_ids=[],
        monitored_entity_ids=[entity_id],
    )
    bridge._request_recalculate = Mock()  # type: ignore[method-assign]
    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.event_bridge."
        "async_track_state_change_event"
    ) as track:
        bridge.setup_listeners()
    outdoor_context["bridge"] = bridge
    outdoor_context["listener"] = track.call_args.args[2]
    outdoor_context["monitored_entity_id"] = entity_id


@given(
    parsers.parse(
        "its history reads {first:f} °C from {first_at} then {second:f} °C from {second_at}"
    )
)
def outdoor_history(
    outdoor_context: dict, first: float, first_at: str, second: float, second_at: str
) -> None:
    """GIVEN: The outdoor source's recorded history."""
    entity_id = outdoor_context["data"][CONF_TEMPERATURE_OUT_ENTITY]
    outdoor_context["outdoor_history"] = [
        HistoricalMeasurement(_at(first_at), first, {"unit_of_measurement": "°C"}, entity_id),
        HistoricalMeasurement(_at(second_at), second, {"unit_of_measurement": "°C"}, entity_id),
    ]


@given(parsers.parse("the room heated from {start} to {end}"))
def room_heated(outdoor_context: dict, start: str, end: str) -> None:
    """GIVEN: The VTherm history shows one heating cycle between two times."""
    start_at, end_at = _at(start), _at(end)
    before, middle, after = (
        start_at - timedelta(minutes=10),
        start_at + (end_at - start_at) / 2,
        end_at + timedelta(minutes=10),
    )

    def m(when: datetime, value: object, **attributes: str) -> HistoricalMeasurement:
        return HistoricalMeasurement(when, value, attributes, VTHERM_ENTITY_ID)

    outdoor_context["climate_history"] = {
        HistoricalDataKey.INDOOR_TEMP: [
            m(before, 18.0),
            m(start_at, 19.0),
            m(middle, 19.2),
            m(end_at, 19.6),
            m(after, 20.1),
        ],
        HistoricalDataKey.TARGET_TEMP: [m(t, 20.0) for t in (before, start_at, middle, end_at)],
        HistoricalDataKey.HEATING_STATE: [
            m(before, False, hvac_action="off", hvac_mode="off"),
            m(start_at, True, **HEATING),
            m(middle, True, **HEATING),
            m(end_at, False, **HEATING),
            m(after, False, **IDLE),
        ],
    }
    outdoor_context["window"] = (before, after + timedelta(minutes=5))


@given(
    parsers.parse("the room is at {current:f} °C and must reach {target:f} °C in {hours:d} hours")
)
def room_must_reach(outdoor_context: dict, current: float, target: float, hours: int) -> None:
    """GIVEN: The next schedule and the current room temperature."""
    outdoor_context["now"] = DAY.replace(hour=5)
    outdoor_context["current_temp"] = current
    outdoor_context["timeslot"] = ScheduledTimeslot(
        target_time=outdoor_context["now"] + timedelta(hours=hours),
        target_temp=target,
        timeslot_id="morning",
    )


@given(parsers.parse("the learned heating slope is {slope:f} °C per hour"))
def learned_slope(outdoor_context: dict, slope: float) -> None:
    """GIVEN: The heating slope IHP learned for the room."""
    outdoor_context["slope"] = slope


# ------------------------------------------------------------------
# When
# ------------------------------------------------------------------


@when("IHP extracts the heating cycles")
def extract_cycles(outdoor_context: dict) -> None:
    """WHEN: Cycles are extracted from VTherm and outdoor history together."""
    reader = HAOutdoorTemperatureHistoryReader(
        Mock(), RecorderAccessQueue(), outdoor_context["data"][CONF_TEMPERATURE_OUT_ENTITY]
    )
    reader._reader.fetch_historical_data = AsyncMock(  # type: ignore[method-assign]
        return_value=HistoricalDataSet(
            data={HistoricalDataKey.OUTDOOR_TEMP: outdoor_context["outdoor_history"]}
        )
    )
    start, end = outdoor_context["window"]
    service = HeatingCycleService(
        temp_delta_threshold=0.5,
        cycle_split_duration_minutes=0,
        min_cycle_duration_minutes=5,
        max_cycle_duration_minutes=300,
    )

    async def _extract() -> list:
        outdoor = await reader.fetch_all_historical_data(VTHERM_ENTITY_ID, start, end)
        dataset = HistoricalDataSet(data={**outdoor_context["climate_history"], **outdoor.data})
        return await service.extract_heating_cycles(VTHERM_ENTITY_ID, dataset, start, end)

    outdoor_context["cycles"] = asyncio.run(_extract())


@when(parsers.parse("it is {outdoor:f} °C outside"))
def it_is_outside(outdoor_context: dict, outdoor: float) -> None:
    """WHEN: IHP decides what to do with this outdoor temperature."""
    scheduler_reader = AsyncMock(spec=ISchedulerReader)
    scheduler_reader.get_next_timeslot.return_value = outdoor_context["timeslot"]
    storage = AsyncMock(spec=ILhsStorage)
    storage.get_learned_heating_slope.return_value = outdoor_context["slope"]
    environment = EnvironmentState(
        indoor_temperature=outdoor_context["current_temp"],
        outdoor_temp=outdoor,
        indoor_humidity=50.0,
        cloud_coverage=100.0,
        timestamp=outdoor_context["now"],
    )
    strategy = SimpleDecisionStrategy(scheduler_reader=scheduler_reader, model_storage=storage)
    outdoor_context["decision"] = asyncio.run(strategy.decide_heating_action(environment))


@when("IHP reads the current environment")
def read_environment(outdoor_context: dict) -> None:
    """WHEN: IHP reads its configuration, then the current environment."""
    hass = _make_hass(outdoor_context)
    config_entry = Mock(entry_id="entry", data=outdoor_context["data"], options={})

    async def _read() -> object:
        config = await HADeviceConfigReader(hass, config_entry).get_device_config("entry")
        reader = HAEnvironmentReader(
            hass,
            config.vtherm_entity_id,
            outdoor_temp_entity_id=config.temperature_out_entity_id,
            humidity_out_entity_id=config.humidity_out_entity_id,
            cloud_cover_entity_id=config.cloud_cover_entity_id,
        )
        return await reader.get_current_environment()

    outdoor_context["environment"] = asyncio.run(_read())


@when("IHP starts monitoring its outdoor sources")
def start_monitoring(outdoor_context: dict) -> None:
    """WHEN: IHP reads its configuration and picks the sources to listen to."""
    hass = _make_hass(outdoor_context)
    config_entry = Mock(entry_id="entry", data=outdoor_context["data"], options={})
    config = asyncio.run(HADeviceConfigReader(hass, config_entry).get_device_config("entry"))
    application = HeatingApplication(hass, config)
    outdoor_context["listened"] = application._recalculation_trigger_entity_ids()


@when(
    parsers.parse(
        '"{entity_id}" goes from {before:f} °C to {after:f} °C '
        "with the same humidity and cloud coverage"
    )
)
def weather_cools(outdoor_context: dict, entity_id: str, before: float, after: float) -> None:
    """WHEN: The weather entity reports a colder temperature, nothing else moves."""
    attributes = {"temperature_unit": "°C", "humidity": 80, "cloud_coverage": 90}
    old_state = State(entity_id, "cloudy", {**attributes, "temperature": before})
    new_state = State(entity_id, "cloudy", {**attributes, "temperature": after})
    recalculate = outdoor_context["bridge"]._request_recalculate
    recalculate.reset_mock()
    event = Mock(data={"entity_id": entity_id, "old_state": old_state, "new_state": new_state})
    outdoor_context["listener"](event)
    outdoor_context["triggered"] = recalculate.called


# ------------------------------------------------------------------
# Then
# ------------------------------------------------------------------


@then(parsers.parse("the outdoor temperature is {expected:f} °C"))
def outdoor_temperature_is(outdoor_context: dict, expected: float) -> None:
    """THEN: The environment carries the outdoor temperature in Celsius."""
    assert outdoor_context["environment"].outdoor_temp == pytest.approx(expected)


@then("the outdoor temperature is unknown")
def outdoor_temperature_unknown(outdoor_context: dict) -> None:
    """THEN: No outdoor temperature reaches the prediction."""
    assert outdoor_context["environment"].outdoor_temp is None


@then(parsers.parse("the outdoor humidity is {expected:d}"))
def outdoor_humidity_is(outdoor_context: dict, expected: int) -> None:
    """THEN: The environment carries the outdoor humidity."""
    assert outdoor_context["environment"].outdoor_humidity == pytest.approx(expected)


@then(parsers.parse("the cloud coverage is {expected:d}"))
def cloud_coverage_is(outdoor_context: dict, expected: int) -> None:
    """THEN: The environment carries the cloud coverage."""
    assert outdoor_context["environment"].cloud_coverage == pytest.approx(expected)


@then(parsers.parse('IHP listens to "{entity_id}"'))
def listens_to(outdoor_context: dict, entity_id: str) -> None:
    """THEN: Changes of this source trigger a recalculation."""
    assert entity_id in outdoor_context["listened"]


@then(parsers.parse('IHP does not listen to "{entity_id}"'))
def does_not_listen_to(outdoor_context: dict, entity_id: str) -> None:
    """THEN: Changes of this source are not worth a recalculation."""
    assert entity_id not in outdoor_context["listened"]


@then("no recalculation is triggered")
def no_recalculation(outdoor_context: dict) -> None:
    """THEN: The anticipation is not rerun for a value it does not use."""
    assert outdoor_context["triggered"] is False


@then(parsers.parse("the cycle records an average outdoor temperature of {expected:f} °C"))
def cycle_records_outdoor(outdoor_context: dict, expected: float) -> None:
    """THEN: The extracted cycle carries the outdoor temperature it ran in."""
    cycles = outdoor_context["cycles"]
    assert len(cycles) == 1
    assert cycles[0].avg_outdoor_temp == pytest.approx(expected)


@then("IHP waits instead of starting to heat now")
def ihp_waits(outdoor_context: dict) -> None:
    """THEN: About 1.5 h of heating needed, 2 h left: heating does not start yet.

    The former fixed outdoor factor doubled the estimate at 0 °C, which started
    heating right away, half an hour too early.
    """
    decision = outdoor_context["decision"]
    assert decision.action == HeatingAction.NO_ACTION
    assert decision.reason.startswith("Wait until")
