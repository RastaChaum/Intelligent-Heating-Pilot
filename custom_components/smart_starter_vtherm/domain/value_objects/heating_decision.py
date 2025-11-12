"""Heating decision value object."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HeatingAction(Enum):
    """Types of heating actions that can be taken."""
    
    START_HEATING = "start_heating"
    STOP_HEATING = "stop_heating"
    NO_ACTION = "no_action"
    MONITOR = "monitor"


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
