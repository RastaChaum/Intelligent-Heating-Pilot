"""Multi-room features for ML model with thermal coupling."""
from __future__ import annotations

from dataclasses import dataclass

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
    
    @classmethod
    def from_lagged_features(
        cls,
        lagged_features: "LaggedFeatures",
        adjacent_rooms: dict[str, RoomFeatures] | None = None,
    ) -> MultiRoomFeatures:
        """Create MultiRoomFeatures from a LaggedFeatures object.
        
        Helper method for backward compatibility with existing LaggedFeatures.
        Splits the features into common and room-specific components.
        
        Args:
            lagged_features: Original LaggedFeatures object
            adjacent_rooms: Optional dict of adjacent room features
            
        Returns:
            MultiRoomFeatures with split architecture.
        """
        # Import here to avoid circular dependency
        from .lagged_features import LaggedFeatures
        
        # Extract common features
        common = CommonFeatures(
            outdoor_temp=lagged_features.outdoor_temp,
            humidity=lagged_features.humidity,
            cloud_coverage=lagged_features.cloud_coverage,
            outdoor_temp_lag_15min=lagged_features.outdoor_temp_lag_15min,
            outdoor_temp_lag_30min=lagged_features.outdoor_temp_lag_30min,
            outdoor_temp_lag_60min=lagged_features.outdoor_temp_lag_60min,
            outdoor_temp_lag_90min=lagged_features.outdoor_temp_lag_90min,
            outdoor_temp_lag_120min=lagged_features.outdoor_temp_lag_120min,
            outdoor_temp_lag_180min=lagged_features.outdoor_temp_lag_180min,
            humidity_lag_15min=lagged_features.humidity_lag_15min,
            humidity_lag_30min=lagged_features.humidity_lag_30min,
            humidity_lag_60min=lagged_features.humidity_lag_60min,
            humidity_lag_90min=lagged_features.humidity_lag_90min,
            humidity_lag_120min=lagged_features.humidity_lag_120min,
            humidity_lag_180min=lagged_features.humidity_lag_180min,
            cloud_coverage_lag_15min=lagged_features.cloud_coverage_lag_15min,
            cloud_coverage_lag_30min=lagged_features.cloud_coverage_lag_30min,
            cloud_coverage_lag_60min=lagged_features.cloud_coverage_lag_60min,
            cloud_coverage_lag_90min=lagged_features.cloud_coverage_lag_90min,
            cloud_coverage_lag_120min=lagged_features.cloud_coverage_lag_120min,
            cloud_coverage_lag_180min=lagged_features.cloud_coverage_lag_180min,
            hour_sin=lagged_features.hour_sin,
            hour_cos=lagged_features.hour_cos,
        )
        
        # Extract target room features
        target_room = RoomFeatures(
            current_temp=lagged_features.current_temp,
            target_temp=lagged_features.target_temp,
            current_slope=lagged_features.current_slope,
            temp_lag_15min=lagged_features.temp_lag_15min,
            temp_lag_30min=lagged_features.temp_lag_30min,
            temp_lag_60min=lagged_features.temp_lag_60min,
            temp_lag_90min=lagged_features.temp_lag_90min,
            temp_lag_120min=lagged_features.temp_lag_120min,
            temp_lag_180min=lagged_features.temp_lag_180min,
            power_lag_15min=lagged_features.power_lag_15min,
            power_lag_30min=lagged_features.power_lag_30min,
            power_lag_60min=lagged_features.power_lag_60min,
            power_lag_90min=lagged_features.power_lag_90min,
            power_lag_120min=lagged_features.power_lag_120min,
            power_lag_180min=lagged_features.power_lag_180min,
            temp_delta=lagged_features.temp_delta,
        )
        
        return cls(
            common=common,
            target_room=target_room,
            adjacent_rooms=adjacent_rooms or {},
        )
