"""Home Assistant implementation of ML model storage."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.helpers.storage import Store

from ...domain.interfaces import IMLModelStorage

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "intelligent_heating_pilot.ml_models"


class HAMLModelStorage(IMLModelStorage):
    """Home Assistant storage implementation for ML models.
    
    Stores trained XGBoost models and training examples in HA's storage system.
    Each room has its own model and training example collection.
    """
    
    def __init__(self, store: Store) -> None:
        """Initialize the storage adapter.
        
        Args:
            store: Home Assistant Store instance
        """
        self._store = store
    
    async def save_model(
        self,
        room_id: str,
        model_data: bytes,
        metadata: dict[str, Any],
    ) -> None:
        """Save a trained ML model for a room."""
        data = await self._store.async_load() or {}
        
        if "models" not in data:
            data["models"] = {}
        
        # Store model as base64 to be JSON-serializable
        import base64
        model_b64 = base64.b64encode(model_data).decode("utf-8")
        
        data["models"][room_id] = {
            "model_data": model_b64,
            "metadata": metadata,
            "saved_at": datetime.now().isoformat(),
        }
        
        await self._store.async_save(data)
        
        _LOGGER.info("Saved ML model for room %s", room_id)
    
    async def load_model(
        self,
        room_id: str,
    ) -> tuple[bytes, dict[str, Any]] | None:
        """Load a trained ML model for a room."""
        data = await self._store.async_load()
        if not data or "models" not in data:
            return None
        
        if room_id not in data["models"]:
            return None
        
        model_entry = data["models"][room_id]
        
        # Decode from base64
        import base64
        model_data = base64.b64decode(model_entry["model_data"])
        metadata = model_entry["metadata"]
        
        _LOGGER.debug("Loaded ML model for room %s", room_id)
        
        return model_data, metadata
    
    async def model_exists(self, room_id: str) -> bool:
        """Check if a trained model exists for a room."""
        data = await self._store.async_load()
        if not data or "models" not in data:
            return False
        
        return room_id in data["models"]
    
    async def get_model_metadata(self, room_id: str) -> dict[str, Any] | None:
        """Get metadata for a trained model."""
        data = await self._store.async_load()
        if not data or "models" not in data:
            return None
        
        if room_id not in data["models"]:
            return None
        
        return data["models"][room_id]["metadata"]
    
    async def save_training_example(
        self,
        room_id: str,
        cycle_id: str,
        features: dict[str, float],
        target: float,
        timestamp: datetime,
    ) -> None:
        """Save a new training example for continuous learning."""
        data = await self._store.async_load() or {}
        
        if "training_examples" not in data:
            data["training_examples"] = {}
        
        if room_id not in data["training_examples"]:
            data["training_examples"][room_id] = []
        
        example = {
            "cycle_id": cycle_id,
            "features": features,
            "target": target,
            "timestamp": timestamp.isoformat(),
        }
        
        data["training_examples"][room_id].append(example)
        
        # Keep only last 500 examples per room
        if len(data["training_examples"][room_id]) > 500:
            data["training_examples"][room_id] = data["training_examples"][room_id][-500:]
        
        await self._store.async_save(data)
        
        _LOGGER.debug(
            "Saved training example for room %s (cycle %s)",
            room_id,
            cycle_id,
        )
    
    async def get_new_training_examples(
        self,
        room_id: str,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get new training examples collected since last training."""
        data = await self._store.async_load()
        if not data or "training_examples" not in data:
            return []
        
        if room_id not in data["training_examples"]:
            return []
        
        examples = data["training_examples"][room_id]
        
        if since is None:
            return examples
        
        # Filter by timestamp
        filtered = [
            ex for ex in examples
            if datetime.fromisoformat(ex["timestamp"]) > since
        ]
        
        return filtered
    
    async def clear_training_examples(self, room_id: str) -> None:
        """Clear collected training examples after model retraining."""
        data = await self._store.async_load()
        if not data or "training_examples" not in data:
            return
        
        if room_id in data["training_examples"]:
            data["training_examples"][room_id] = []
            await self._store.async_save(data)
            
            _LOGGER.info("Cleared training examples for room %s", room_id)
