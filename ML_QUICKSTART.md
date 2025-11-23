# ML Model Quick Start Guide

## What is this?

The Intelligent Heating Pilot now includes a **Machine Learning (ML) prediction system** that learns from your heating history to accurately predict when to start pre-heating each room.

### How It Works

1. **📊 Collects Data**: Monitors your heating cycles (temperature, timing, weather)
2. **🧠 Learns Patterns**: Trains an XGBoost model on your specific room's thermal behavior
3. **🎯 Predicts Timing**: Calculates exactly when to start heating to reach target at scheduled time
4. **🔄 Improves Continuously**: Retrains weekly with new observations

## Installation

### Prerequisites

```bash
pip install xgboost>=2.1 pandas>=2.2 numpy>=1.26 scikit-learn>=1.5
```

Or add to your Home Assistant's `requirements.txt`:

```
xgboost>=2.1
pandas>=2.2
numpy>=1.26
scikit-learn>=1.5
```

### Verify Installation

Check that XGBoost is available:

```python
python3 -c "import xgboost; print(xgboost.__version__)"
```

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│           Historical Data                    │
│  (6 months of heating cycles)                │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      Feature Engineering                     │
│  • Temperature lags (15/30/60/90 min)        │
│  • Power state lags                          │
│  • Time-of-day (cyclic encoding)             │
│  • Environmental data (outdoor temp, etc.)   │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      Error-Driven Labeling                   │
│  optimal_duration = actual - error           │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      XGBoost Training                        │
│  • Predicts: Optimal duration (minutes)      │
│  • Input: 15 engineered features             │
│  • Output: When to start heating             │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      Continuous Learning                     │
│  • Logs each heating cycle                   │
│  • Retrains weekly                           │
│  • Improves with every cycle                 │
└─────────────────────────────────────────────┘
```

## Quick Example

### 1. Basic Usage

```python
from custom_components.intelligent_heating_pilot.domain.services import (
    MLPredictionService,
    FeatureEngineeringService,
)

# Create services
ml_service = MLPredictionService()
engineer = FeatureEngineeringService()

# Train model (simplified)
X_train = [...]  # Your historical features
y_train = [...]  # Optimal durations in minutes
metrics = ml_service.train_model(X_train, y_train)

print(f"Model trained! RMSE: {metrics['rmse']:.2f} minutes")

# Make prediction
features = engineer.create_lagged_features(
    current_temp=20.0,
    target_temp=22.0,
    current_time=datetime.now(),
    temp_history=[...],
    power_history=[...],
)

predicted_minutes = ml_service.predict_duration(features)
print(f"Start heating {predicted_minutes:.1f} minutes before target time")
```

### 2. Training Pipeline

```python
from custom_components.intelligent_heating_pilot.application import (
    MLTrainingApplicationService
)

# Initialize with Home Assistant adapters
training_service = MLTrainingApplicationService(
    historical_reader=ha_historical_reader,
    model_storage=ha_model_storage,
)

# Train for a specific room
results = await training_service.train_model_for_room(
    room_id="climate.bedroom",
    lookback_months=6,  # Use 6 months of data
    min_cycles=10,      # Need at least 10 cycles
)

print(f"Training complete!")
print(f"Cycles extracted: {results['cycles_extracted']}")
print(f"Valid cycles: {results['cycles_valid']}")
```

### 3. Make Predictions

```python
# Create features from current state
features = engineer.create_lagged_features(
    current_temp=18.5,
    target_temp=22.0,
    current_time=datetime(2025, 1, 15, 6, 30),
    temp_history=[
        (datetime(2025, 1, 15, 6, 15), 18.3),
        (datetime(2025, 1, 15, 6, 0), 18.0),
        (datetime(2025, 1, 15, 5, 30), 17.8),
        (datetime(2025, 1, 15, 5, 0), 17.5),
    ],
    power_history=[
        (datetime(2025, 1, 15, 6, 0), False),
        (datetime(2025, 1, 15, 5, 30), False),
    ],
    outdoor_temp=5.0,
    humidity=65.0,
)

# Get prediction
duration = ml_service.predict_duration(features)
start_time = datetime(2025, 1, 15, 7, 0) - timedelta(minutes=duration)

print(f"To reach 22°C at 7:00 AM:")
print(f"  Start heating at: {start_time.strftime('%H:%M')}")
print(f"  Duration: {duration:.1f} minutes")
```

## Key Features

### ✅ Implemented

- **Value Objects**: HeatingCycle, LaggedFeatures, TrainingData
- **Domain Services**: FeatureEngineering, MLPrediction, CycleLabeling
- **Interfaces**: IHistoricalDataReader, IMLModelStorage
- **ML Model**: XGBoost Regressor with optimized hyperparameters
- **Feature Engineering**: 15 features including lagged temp/power, time-of-day
- **Error-Driven Learning**: Automatic label calculation from observed errors
- **Model Persistence**: Pickle serialization for XGBoost models
- **Continuous Learning**: Training example collection and retraining pipeline

### 🚧 In Progress

- **Historical Data Reader**: Database extraction for Home Assistant
- **Retraining Scheduler**: Automatic weekly/monthly retraining
- **UI Integration**: Home Assistant dashboard for model status

### 🔮 Future Enhancements

- **Multi-Room Learning**: Transfer knowledge between similar rooms
- **Weather Integration**: Use forecast for better predictions
- **Seasonal Models**: Different models for winter vs. summer
- **A/B Testing**: Compare ML vs. simple slope predictions

## Configuration

### Minimal Configuration

```yaml
# configuration.yaml
intelligent_heating_pilot:
  rooms:
    - room_id: climate.bedroom
      ml_enabled: true
      min_training_cycles: 10
      lookback_months: 6
```

### Advanced Configuration

```yaml
intelligent_heating_pilot:
  rooms:
    - room_id: climate.bedroom
      ml_enabled: true
      min_training_cycles: 10
      lookback_months: 6
      
      # XGBoost hyperparameters (optional)
      model_params:
        max_depth: 4
        learning_rate: 0.1
        n_estimators: 100
        
      # Retraining settings
      retrain_schedule: weekly
      min_new_examples: 20
      
      # Feature engineering
      lag_intervals: [15, 30, 60, 90]  # minutes
```

## Performance Expectations

### Training Data Requirements

| Training Cycles | Expected RMSE | Quality |
|----------------|---------------|---------|
| 10-20 cycles   | 15-20 min     | Basic   |
| 20-50 cycles   | 10-15 min     | Good    |
| 50-100 cycles  | 5-10 min      | Excellent |
| 100+ cycles    | <5 min        | Expert  |

### Prediction Accuracy

With good training data (50+ cycles):
- **Average error**: 5-10 minutes
- **95th percentile**: <15 minutes
- **Cold start**: Uses default LHS until 10 cycles collected

## Troubleshooting

### Problem: "Insufficient training data"

**Solution**: Wait for more heating cycles. You need at least 10 valid cycles before training.

```python
# Check current cycle count
results = await training_service.train_model_for_room("climate.bedroom")
print(f"Valid cycles: {results['cycles_valid']}/10 minimum")
```

### Problem: High prediction error (RMSE > 20 min)

**Possible causes:**
1. Inconsistent heating behavior
2. Missing sensors (outdoor temp, humidity)
3. Temperature sensor drift

**Solutions:**
1. Filter outlier cycles with `max_error_minutes`
2. Add environmental sensors
3. Recalibrate temperature sensors

### Problem: Model not improving with retraining

**Possible causes:**
1. Not enough new data (<5 examples)
2. Similar conditions (same season, same patterns)

**Solutions:**
1. Collect more diverse examples
2. Wait for seasonal change
3. Manually trigger retraining after 20+ new cycles

## API Reference

### MLPredictionService

```python
class MLPredictionService:
    def train_model(self, X_train: list[list[float]], y_train: list[float]) -> dict
    def predict_duration(self, features: LaggedFeatures) -> float | None
    def serialize_model(self) -> bytes | None
    def deserialize_model(self, model_bytes: bytes) -> None
    def is_trained(self) -> bool
    def get_feature_importance(self) -> dict[str, float] | None
```

### FeatureEngineeringService

```python
class FeatureEngineeringService:
    def create_lagged_features(
        self,
        current_temp: float,
        target_temp: float,
        current_time: datetime,
        temp_history: list[tuple[datetime, float]],
        power_history: list[tuple[datetime, bool]],
        outdoor_temp: float | None = None,
        humidity: float | None = None,
    ) -> LaggedFeatures
```

### CycleLabelingService

```python
class CycleLabelingService:
    def label_heating_cycle(self, cycle: HeatingCycle) -> float
    def is_cycle_valid_for_training(self, cycle: HeatingCycle) -> bool
```

## Testing

Run the test suite:

```bash
# All ML tests
pytest tests/unit/domain/test_ml_prediction_service.py -v
pytest tests/unit/domain/test_feature_engineering.py -v

# Specific test
pytest tests/unit/domain/test_ml_prediction_service.py::TestMLPredictionService::test_train_and_predict_basic -v
```

## Resources

- **Full Documentation**: See `ML_MODEL_DOCUMENTATION.md`
- **Architecture**: See `ARCHITECTURE.md`
- **Domain Layer**: `custom_components/intelligent_heating_pilot/domain/`
- **Tests**: `tests/unit/domain/`

## Support

For issues or questions:
1. Check `ML_MODEL_DOCUMENTATION.md` for detailed explanations
2. Review test examples in `tests/unit/domain/`
3. Open an issue on GitHub with:
   - Error message
   - Number of training cycles
   - RMSE/MAE metrics
   - Sensor configuration

## License

Same as parent project (MIT License)
