"""Wake-up source configuration value object."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .slot_action import SlotAction

DEFAULT_HORIZON = timedelta(hours=24)


@dataclass(frozen=True)
class WakeUpSourceConfig:
    """One wake-up source of an IHP: an entity holding a point in time to anticipate.

    The entity can be a phone's next alarm, a date-time helper or any entity that says when
    the room must be ready. A source is one more candidate deadline next to the schedulers'
    slots; the earliest valid deadline wins.

    Attributes:
        entity_id: The entity holding the point in time.
        fixed_target: The preset or temperature to reach, when the user gave one.
        target_from_schedule: Take the target from the schedule, the fixed target being the
            fallback. Needs a scheduler on the same IHP, otherwise the fixed target is used.
        horizon: Deadlines further away than this are ignored, to prevent accidental triggers.
        hold: How long after the deadline IHP puts the thermostat back in its earlier state;
            None leaves the thermostat as it is after the deadline.
    """

    entity_id: str
    fixed_target: SlotAction | None = None
    target_from_schedule: bool = False
    horizon: timedelta = DEFAULT_HORIZON
    hold: timedelta | None = None

    def __post_init__(self) -> None:
        """Validate the configuration.

        Raises:
            ValueError: If the entity is blank, there is no way to know the target, or a
                duration is not positive.
        """
        if not self.entity_id or not self.entity_id.strip():
            raise ValueError("A wake-up source needs an entity id")
        if self.fixed_target is None and not self.target_from_schedule:
            raise ValueError("A wake-up source needs a fixed target or a target from the schedule")
        if self.horizon <= timedelta(0):
            raise ValueError("A wake-up source horizon must be positive")
        if self.hold is not None and self.hold <= timedelta(0):
            raise ValueError("A wake-up source hold must be positive when set")
