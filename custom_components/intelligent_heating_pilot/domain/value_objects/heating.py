"""Heating decision value object."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class HeatingAction(Enum):
    """Types of heating actions that can be taken."""
    
    START_HEATING = "start_heating"
    STOP_HEATING = "stop_heating"
    SET_TEMPERATURE = "set_temperature"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class HeatingDecision:
    """Represents a decision about heating control.
    
    This value object encapsulates what action should be taken and why.
    
    Attributes:
        action: The type of action to take
        target_temp: Target temperature if starting heating (None otherwise)
        reason: Human-readable explanation for the decision
    """
    
    action: HeatingAction
    target_temp: float | None = None
    reason: str = ""
    
    def __post_init__(self) -> None:
        """Validate the heating decision data."""
        if self.action == HeatingAction.START_HEATING and self.target_temp is None:
            raise ValueError("START_HEATING action requires a target temperature")

        if self.action == HeatingAction.SET_TEMPERATURE and self.target_temp is None:
            raise ValueError("SET_TEMPERATURE action requires a target temperature")


@dataclass(frozen=True)
class TariffPeriodDetail:
    """Represents energy consumption and cost details for a specific tariff period."""
    tariff_price_eur_per_kwh: float
    energy_kwh: float
    heating_duration_minutes: float
    cost_euro: float


@dataclass(frozen=True)
class HeatingCycle:
    """Represents a single heating cycle, encapsulating all its relevant data.
    
    This value object provides a complete and immutable snapshot of a heating period,
    including its duration, temperature changes, and energy consumption details.
    
    Attributes:
        start_time: The exact datetime when the heating cycle started.
        end_time: The exact datetime when the heating cycle ended.
        target_temp: The target temperature set for this heating cycle.
        end_temp: The actual temperature reached at the end of the heating cycle.
        start_temp: The temperature at the beginning of the heating cycle.
        tariff_details: A list of TariffDetail objects, breaking down energy, duration,
                        and cost by specific TariffPeriodDetail periods within the cycle.
    """
    
    device_id: str
    start_time: datetime
    end_time: datetime
    target_temp: float
    end_temp: float
    start_temp: float
    tariff_details: list[TariffPeriodDetail] | None = None

    @property
    def duration_minutes(self) -> float:
        """Calculates the total duration of the heating cycle in minutes."""
        return (self.end_time - self.start_time).total_seconds() / 60

    @property
    def temp_delta(self) -> float:
        """Calculates the difference between the target temperature and the end temperature."""
        return self.target_temp - self.end_temp

    @property
    def start_hour(self) -> int:
        """Returns the hour (0-23) when the heating cycle started."""
        return self.start_time.hour

    @property
    def end_hour(self) -> int:
        """Returns the hour (0-23) when the heating cycle ended."""
        return self.end_time.hour

    @property
    def start_weekday(self) -> int:
        """Returns the weekday (0=Monday, 6=Sunday) when the heating cycle started."""
        return self.start_time.weekday()

    @property
    def end_weekday(self) -> int:
        """Returns the weekday (0=Monday, 6=Sunday) when the heating cycle ended."""
        return self.end_time.weekday()

    @property
    def total_energy_kwh(self) -> float:
        """Calculates the total energy consumed during the cycle in kWh from tariff details."""
        return sum(detail.energy_kwh for detail in (self.tariff_details or []))

    @property
    def total_heating_duration_minutes(self) -> float:
        """Calculates the total heating duration in minutes from tariff details."""
        return sum(detail.heating_duration_minutes for detail in (self.tariff_details or []))

    @property
    def total_cost_euro(self) -> float:
        """Calculates the total cost in euros from tariff details."""
        return sum(detail.cost_euro for detail in (self.tariff_details or []))

    def __post_init__(self) -> None:
        """Validate the heating cycle data."""
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time for a heating cycle.")