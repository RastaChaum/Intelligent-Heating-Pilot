"""Tests for multi-room features value objects."""
from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CommonFeatures,
    CycleFeatures,
    MultiRoomFeatures,
    RoomFeatures,
)


def create_test_cycle_features(
    current_temp: float = 20.0,
    target_temp: float = 22.0,
    current_slope: float = 0.3,
    outdoor_temp: float = 5.0,
    outdoor_humidity: float = 80.0,
    humidity: float = 50.0,
    cloud_coverage: float = 40.0,
) -> CycleFeatures:
    """Helper to create test CycleFeatures."""
    return CycleFeatures(
        current_temp=current_temp,
        target_temp=target_temp,
        temp_delta=target_temp - current_temp,
        current_slope=current_slope,
        outdoor_temp=outdoor_temp,
        outdoor_humidity=outdoor_humidity,
        humidity=humidity,
        cloud_coverage=cloud_coverage,
    )


class TestCommonFeatures:
    """Test suite for CommonFeatures."""
    
    def test_create_common_features(self) -> None:
        """Test creating common features."""
        common = CommonFeatures(
            outdoor_temp=5.0,
            humidity=65.0,
            cloud_coverage=40.0,
            outdoor_temp_lag_15min=5.1,
            outdoor_temp_lag_30min=5.2,
            outdoor_temp_lag_60min=5.3,
            outdoor_temp_lag_90min=5.4,
            outdoor_temp_lag_120min=5.5,
            outdoor_temp_lag_180min=5.6,
            humidity_lag_15min=64.0,
            humidity_lag_30min=63.0,
            humidity_lag_60min=62.0,
            humidity_lag_90min=61.0,
            humidity_lag_120min=60.0,
            humidity_lag_180min=59.0,
            cloud_coverage_lag_15min=39.0,
            cloud_coverage_lag_30min=38.0,
            cloud_coverage_lag_60min=37.0,
            cloud_coverage_lag_90min=36.0,
            cloud_coverage_lag_120min=35.0,
            cloud_coverage_lag_180min=34.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        assert common.outdoor_temp == 5.0
        assert common.hour_sin == 0.5
    
    def test_common_features_to_dict(self) -> None:
        """Test converting common features to dictionary."""
        common = CommonFeatures(
            outdoor_temp=5.0,
            humidity=65.0,
            cloud_coverage=40.0,
            outdoor_temp_lag_15min=5.1,
            outdoor_temp_lag_30min=5.2,
            outdoor_temp_lag_60min=5.3,
            outdoor_temp_lag_90min=5.4,
            outdoor_temp_lag_120min=5.5,
            outdoor_temp_lag_180min=5.6,
            humidity_lag_15min=64.0,
            humidity_lag_30min=63.0,
            humidity_lag_60min=62.0,
            humidity_lag_90min=61.0,
            humidity_lag_120min=60.0,
            humidity_lag_180min=59.0,
            cloud_coverage_lag_15min=39.0,
            cloud_coverage_lag_30min=38.0,
            cloud_coverage_lag_60min=37.0,
            cloud_coverage_lag_90min=36.0,
            cloud_coverage_lag_120min=35.0,
            cloud_coverage_lag_180min=34.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        feature_dict = common.to_feature_dict()
        
        assert len(feature_dict) == 23  # All common features
        assert feature_dict["outdoor_temp"] == 5.0
        assert feature_dict["hour_sin"] == 0.5


class TestRoomFeatures:
    """Test suite for RoomFeatures."""
    
    def test_create_room_features(self) -> None:
        """Test creating room features."""
        from custom_components.intelligent_heating_pilot.domain.value_objects import CycleFeatures
        
        cycle_feats = CycleFeatures(
            current_temp=20.0,
            target_temp=22.0,
            temp_delta=2.0,
            current_slope=0.3,
            outdoor_temp=5.0,
            outdoor_humidity=80.0,
            humidity=50.0,
            cloud_coverage=40.0,
        )
        room = RoomFeatures(cycle_feats)
        
        assert room.cycle_features.current_temp == 20.0
        assert room.cycle_features.temp_delta == 2.0
    
    def test_room_features_to_dict_no_prefix(self) -> None:
        """Test converting room features to dictionary without prefix."""
        laggued = create_test_cycle_features()

        room = RoomFeatures(laggued)
        
        feature_dict = room.to_feature_dict()
        
        assert len(feature_dict) == 8  # All room features
        assert feature_dict["current_temp"] == 20.0
        assert feature_dict["temp_delta"] == 2.0
    
    def test_room_features_to_dict_with_prefix(self) -> None:
        """Test converting room features to dictionary with prefix."""
        laggued = create_test_cycle_features()
        
        room = RoomFeatures(laggued)
        
        feature_dict = room.to_feature_dict(prefix="bedroom_")
        
        assert len(feature_dict) == 8  # All room features with prefix
        assert feature_dict["bedroom_current_temp"] == 20.0
        assert feature_dict["bedroom_temp_delta"] == 2.0


class TestMultiRoomFeatures:
    """Test suite for MultiRoomFeatures."""
    
    def test_create_multi_room_features(self) -> None:
        """Test creating multi-room features."""
        common = CommonFeatures(
            outdoor_temp=5.0,
            humidity=65.0,
            cloud_coverage=40.0,
            outdoor_temp_lag_15min=5.0,
            outdoor_temp_lag_30min=5.0,
            outdoor_temp_lag_60min=5.0,
            outdoor_temp_lag_90min=5.0,
            outdoor_temp_lag_120min=5.0,
            outdoor_temp_lag_180min=5.0,
            humidity_lag_15min=65.0,
            humidity_lag_30min=65.0,
            humidity_lag_60min=65.0,
            humidity_lag_90min=65.0,
            humidity_lag_120min=65.0,
            humidity_lag_180min=65.0,
            cloud_coverage_lag_15min=40.0,
            cloud_coverage_lag_30min=40.0,
            cloud_coverage_lag_60min=40.0,
            cloud_coverage_lag_90min=40.0,
            cloud_coverage_lag_120min=40.0,
            cloud_coverage_lag_180min=40.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )

        laggued = create_test_cycle_features(current_temp=20.0, target_temp=22.0)

        target = RoomFeatures(laggued
        )
        
        laggued2 = create_test_cycle_features(current_temp=19.0, target_temp=21.0)

        adjacent_room = RoomFeatures(laggued2)
        
        multi = MultiRoomFeatures(
            common=common,
            target_room=target,
            adjacent_rooms={"bedroom": adjacent_room},
        )
        
        assert multi.common.outdoor_temp == 5.0
        assert multi.target_room.cycle_features.current_temp == 20.0
        assert "bedroom" in multi.adjacent_rooms
    
    def test_multi_room_to_dict(self) -> None:
        """Test converting multi-room features to dictionary."""
        common = CommonFeatures(
            outdoor_temp=5.0,
            humidity=65.0,
            cloud_coverage=40.0,
            outdoor_temp_lag_15min=5.0,
            outdoor_temp_lag_30min=5.0,
            outdoor_temp_lag_60min=5.0,
            outdoor_temp_lag_90min=5.0,
            outdoor_temp_lag_120min=5.0,
            outdoor_temp_lag_180min=5.0,
            humidity_lag_15min=65.0,
            humidity_lag_30min=65.0,
            humidity_lag_60min=65.0,
            humidity_lag_90min=65.0,
            humidity_lag_120min=65.0,
            humidity_lag_180min=65.0,
            cloud_coverage_lag_15min=40.0,
            cloud_coverage_lag_30min=40.0,
            cloud_coverage_lag_60min=40.0,
            cloud_coverage_lag_90min=40.0,
            cloud_coverage_lag_120min=40.0,
            cloud_coverage_lag_180min=40.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        laggued = create_test_cycle_features(current_temp=20.0, target_temp=22.0)

        target = RoomFeatures(laggued)
        
        laggued2 = create_test_cycle_features(current_temp=19.0, target_temp=21.0)
        
        adjacent_room = RoomFeatures(laggued2)

        multi = MultiRoomFeatures(
            common=common,
            target_room=target,
            adjacent_rooms={"bedroom": adjacent_room},
        )
        
        feature_dict = multi.to_feature_dict()
        
        # Target room (8) + Common (23) + 1 adjacent room (8) - 3 overlaps = 36 features
        # (outdoor_temp, humidity, cloud_coverage are in both Common and Room)
        assert len(feature_dict) == 36
        assert feature_dict["current_temp"] == 20.0  # Target room
        assert feature_dict["outdoor_temp"] == 5.0  # Common
        assert feature_dict["bedroom_current_temp"] == 19.0  # Adjacent room
    
    def test_multi_room_num_features(self) -> None:
        """Test calculating number of features."""
        common = CommonFeatures(
            outdoor_temp=5.0,
            humidity=65.0,
            cloud_coverage=40.0,
            outdoor_temp_lag_15min=5.0,
            outdoor_temp_lag_30min=5.0,
            outdoor_temp_lag_60min=5.0,
            outdoor_temp_lag_90min=5.0,
            outdoor_temp_lag_120min=5.0,
            outdoor_temp_lag_180min=5.0,
            humidity_lag_15min=65.0,
            humidity_lag_30min=65.0,
            humidity_lag_60min=65.0,
            humidity_lag_90min=65.0,
            humidity_lag_120min=65.0,
            humidity_lag_180min=65.0,
            cloud_coverage_lag_15min=40.0,
            cloud_coverage_lag_30min=40.0,
            cloud_coverage_lag_60min=40.0,
            cloud_coverage_lag_90min=40.0,
            cloud_coverage_lag_120min=40.0,
            cloud_coverage_lag_180min=40.0,
            hour_sin=0.5,
            hour_cos=0.866,
        )
        
        laggued = create_test_cycle_features()

        target = RoomFeatures(laggued)
        
        # No adjacent rooms: 8 + 23 = 31
        multi_0 = MultiRoomFeatures(common=common, target_room=target, adjacent_rooms={})
        assert multi_0.get_num_features() == 31  # 8 target + 23 common
        
        # 1 adjacent room: 8 + 23 + 8 = 39
        laggued1 = create_test_cycle_features()
        adjacent1 = RoomFeatures(laggued1)

        multi_1 = MultiRoomFeatures(
            common=common, target_room=target, adjacent_rooms={"bedroom": adjacent1}
        )
        assert multi_1.get_num_features() == 39  # 8 target + 23 common + 8 adj
        
        # 2 adjacent rooms: 8 + 23 + 16 = 47
        laggued2 = create_test_cycle_features()

        adjacent2 = RoomFeatures(laggued2)
        multi_2 = MultiRoomFeatures(
            common=common,
            target_room=target,
            adjacent_rooms={"bedroom": adjacent1, "living_room": adjacent2},
        )
        assert multi_2.get_num_features() == 47  # 8 target + 23 common + 16 adj (2 rooms)