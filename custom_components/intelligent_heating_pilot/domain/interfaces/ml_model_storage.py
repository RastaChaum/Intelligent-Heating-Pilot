"""Interface for ML model persistence."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class IMLModelStorage(ABC):
    """Contract for persisting and loading ML models.
    
    Implementations handle serialization/deserialization of trained
    XGBoost models and associated metadata.
    """
    
    @abstractmethod
    async def save_model(
        self,
        climate_entity_id: str,
        model_data: bytes,
        metadata: dict[str, Any],
    ) -> None:
        """Save a trained ML model for a room.
        
        Args:
            climate_entity_id: Identifier for the climate entity
            model_data: Serialized model bytes (e.g., from model.save_raw())
            metadata: Model metadata (training date, metrics, etc.)
        """
        pass
    
    @abstractmethod
    async def load_model(
        self,
        climate_entity_id: str,
    ) -> tuple[bytes, dict[str, Any]] | None:
        """Load a trained ML model for a room.
        
        Args:
            climate_entity_id: Identifier for the climate entity
            
        Returns:
            Tuple of (model_data, metadata) if model exists, None otherwise.
        """
        pass
    
    @abstractmethod
    async def model_exists(self, climate_entity_id: str) -> bool:
        """Check if a trained model exists for a room.
        
        Args:
            climate_entity_id: Identifier for the climate entity
            
        Returns:
            True if model exists, False otherwise.
        """
        pass
    
    @abstractmethod
    async def get_model_metadata(self, climate_entity_id: str) -> dict[str, Any] | None:
        """Get metadata for a trained model.
        
        Args:
            climate_entity_id: Identifier for the climate entity
            
        Returns:
            Model metadata dict if model exists, None otherwise.
        """
        pass
    
    @abstractmethod
    async def save_training_example(
        self,
        room_id: str,
        cycle_id: str,
        features: dict[str, float],
        target: float,
        timestamp: datetime,
    ) -> None:
        """Save a new training example for continuous learning.
        
        Args:
            room_id: Identifier for the room
            cycle_id: Unique cycle identifier
            features: Feature dictionary (X)
            target: Target value (Y) in minutes
            timestamp: When the example was recorded
        """
        pass
    
    @abstractmethod
    async def get_new_training_examples(
        self,
        climate_entity_id: str,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get new training examples collected since last training.
        
        Args:
            climate_entity_id: Identifier for the climate entity
            since: Only get examples after this timestamp
            
        Returns:
            List of training example dicts with 'features', 'target', 'timestamp'.
        """
        pass
    
    @abstractmethod
    async def clear_training_examples(self, climate_entity_id: str) -> None:
        """Clear collected training examples after model retraining.
        
        Args:
            climate_entity_id: Identifier for the climate entity
        """
        pass
