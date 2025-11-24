"""Room-specific features for ML model."""
from __future__ import annotations

from dataclasses import dataclass

from .cycle_features import CycleFeatures


@dataclass(frozen=True)
class RoomFeatures:
    """Room-specific thermal features.
    
    These features are unique to each individual room and capture
    its specific thermal behavior and state at the start of a heating cycle.
    """
    
    cycle_features: CycleFeatures  # Cycle features for the specific room 
        
    def to_feature_dict(self, prefix: str = "") -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Args:
            prefix: Optional prefix for feature names (e.g., "room1_" for adjacent rooms)
        
        Returns:
            Dictionary with feature names as keys and values as floats.
            None values are replaced with 0.0.
        """
        # Get base features from cycle_features
        base_dict = self.cycle_features.to_feature_dict()
        
        # Add prefix if needed
        if prefix:
            return {f"{prefix}{key}": value for key, value in base_dict.items()}
        return base_dict
    
    @staticmethod
    def get_feature_names(prefix: str = "") -> list[str]:
        """Get ordered list of room feature names.
        
        Args:
            prefix: Optional prefix for feature names
        
        Returns:
            List of feature names in consistent order.
        """
        # Get base feature names from CycleFeatures
        base_names = CycleFeatures.get_feature_names()
        
        # Add prefix if needed
        if prefix:
            return [f"{prefix}{name}" for name in base_names]
        return base_names
