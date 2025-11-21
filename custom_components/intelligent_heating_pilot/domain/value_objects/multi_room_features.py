"""Multi-room features for ML model with thermal coupling."""
from __future__ import annotations

from dataclasses import dataclass

from domain.value_objects.lagged_features import LaggedFeatures

from .common_features import CommonFeatures
from .room_features import RoomFeatures


@dataclass(frozen=True)
class MultiRoomFeatures:
    """Features for multi-room heating prediction.
    
    Captures thermal coupling between rooms by including features from
    adjacent rooms while avoiding duplication of common environmental data.
    
    This allows the ML model to learn how heating one room affects adjacent
    rooms and vice versa, improving prediction accuracy for thermally-coupled
    spaces.
    """
    
    common: CommonFeatures  # Shared environmental and time features
    target_room: RoomFeatures  # Features for the room being predicted
    adjacent_rooms: dict[str, RoomFeatures]  # Features from neighboring rooms
    
    def to_feature_dict(self) -> dict[str, float]:
        """Convert to dictionary for ML model input.
        
        Combines common features (once), target room features, and adjacent
        room features (with prefixes) into a single flat dictionary.
        
        Returns:
            Dictionary with all feature names as keys and values as floats.
        """
        # Start with common features (no prefix, shared by all)
        features = self.common.to_feature_dict()
        
        # Add target room features (no prefix, this is the main room)
        features.update(self.target_room.to_feature_dict(prefix=""))
        
        # Add adjacent room features (with room-specific prefixes)
        for room_id, room_features in self.adjacent_rooms.items():
            # Use room_id as prefix to distinguish adjacent rooms
            features.update(room_features.to_feature_dict(prefix=f"{room_id}_"))
        
        return features
    
    @staticmethod
    def get_feature_names(adjacent_room_ids: list[str] | None = None) -> list[str]:
        """Get ordered list of feature names for multi-room model.
        
        Args:
            adjacent_room_ids: List of adjacent room IDs to include.
                              If None, returns only target room + common features.
        
        Returns:
            List of feature names in consistent order.
        """
        # Start with target room features
        features = RoomFeatures.get_feature_names(prefix="")
        
        # Add common features
        features.extend(CommonFeatures.get_feature_names())
        
        # Add adjacent room features if specified
        if adjacent_room_ids:
            for room_id in sorted(adjacent_room_ids):  # Sort for consistency
                features.extend(RoomFeatures.get_feature_names(prefix=f"{room_id}_"))
        
        return features
    
    def get_num_features(self) -> int:
        """Get total number of features in this multi-room configuration.
        
        Returns:
            Total feature count.
        """
        # Target room: 16 features
        # Common: 23 features
        # Each adjacent room: 16 features
        return 16 + 23 + (16 * len(self.adjacent_rooms))
