"""Training data value object for ML model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .cycle_features import CycleFeatures
from .lagged_features import LaggedFeatures
from .multi_room_features import MultiRoomFeatures


@dataclass(frozen=True)
class TrainingExample:
    """A single training example for the ML model.
    
    Combines input features (X) with the target label (Y).
    Supports single-room (CycleFeatures or LaggedFeatures) and multi-room (MultiRoomFeatures) models.
    """
    
    features: Union[CycleFeatures, LaggedFeatures, MultiRoomFeatures]  # Input features (X)
    target_duration_minutes: float  # Target label (Y) - optimal preheat duration
    cycle_id: str  # Reference to the source heating cycle
    
    def __post_init__(self) -> None:
        """Validate training example."""
        if self.target_duration_minutes < 0:
            raise ValueError("target_duration_minutes cannot be negative")


@dataclass(frozen=True)
class TrainingDataset:
    """Collection of training examples for model training."""
    
    room_id: str  # Identifier for the room this dataset belongs to
    examples: list[TrainingExample]  # Training examples
    
    @property
    def size(self) -> int:
        """Get number of training examples."""
        return len(self.examples)
    
    def __post_init__(self) -> None:
        """Validate dataset."""
        if not self.examples:
            raise ValueError("Training dataset cannot be empty")
