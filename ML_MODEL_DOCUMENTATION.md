# Machine Learning Model Documentation

## Overview

The Intelligent Heating Pilot implements a **Continuous Learning Machine Learning (ML)** system to accurately predict optimal pre-heating durations for each room. This system uses **XGBoost Regressor** with lagged features to handle the thermal inertia of heating systems.

## Architecture

### Domain-Driven Design Principles

The ML system follows strict DDD architecture:

```
Domain Layer (Pure Python, No HA Dependencies)
├── Value Objects
│   ├── HeatingCycle - Represents a complete heating event
│   ├── LaggedFeatures - Time-series features for ML input
│   ├── TrainingExample - Single ML training sample
│   └── TrainingDataset - Collection of training examples
│
├── Interfaces (Contracts)
│   ├── IHistoricalDataReader - Read from HA database
│   └── IMLModelStorage - Persist ML models
│
└── Services (Business Logic)
    ├── FeatureEngineeringService - Create lagged features
    ├── MLPredictionService - XGBoost training & prediction
    └── CycleLabelingService - Calculate optimal durations

Infrastructure Layer (Home Assistant Integration)
├── HAMLModelStorage - Persist models in HA storage
└── HAHistoricalDataReader - Query HA database

Application Layer (Orchestration)
└── MLTrainingApplicationService - Coordinate training pipeline
```

## Key Concepts

### 1. Error-Driven Labeling

The system learns from past mistakes using **error-driven labeling**:

**Formula:**
```
optimal_duration = actual_duration - error
```

Where:
- `actual_duration`: How long heating actually took
- `error`: Time difference between when target was reached vs. when it should have been reached
  - Positive error = heating finished late
  - Negative error = heating finished early

**Example:**
```python
Scenario: Target 22°C at 7:00 AM
- Heating started: 6:00 AM
- Target reached: 7:15 AM (15 minutes LATE)
- Actual duration: 75 minutes
- Error: +15 minutes
- Optimal duration: 75 - 15 = 60 minutes

Result: Model learns it should have started at 6:00 AM for 60 minutes
```

### 2. Lagged Features (Thermal Inertia Encoding)

Heating systems have **thermal inertia** - past states affect current behavior. We encode this using lagged features:

**Temperature Lags:**
- `temp_lag_15min`: Temperature 15 minutes ago
- `temp_lag_30min`: Temperature 30 minutes ago
- `temp_lag_60min`: Temperature 60 minutes ago
- `temp_lag_90min`: Temperature 90 minutes ago

**Power State Lags:**
- `power_lag_15min`: Was heater on 15 minutes ago? (1=on, 0=off)
- `power_lag_30min`: Was heater on 30 minutes ago?
- `power_lag_60min`: Was heater on 60 minutes ago?
- `power_lag_90min`: Was heater on 90 minutes ago?

**Current Features:**
- `current_temp`: Current room temperature
- `target_temp`: Desired temperature
- `temp_delta`: `target_temp - current_temp`
- `outdoor_temp`: Outdoor temperature (if available)
- `humidity`: Indoor humidity (if available)
- `hour_sin`: Sine of hour (cyclic encoding)
- `hour_cos`: Cosine of hour (cyclic encoding)

### 3. Cyclic Time Encoding

Time of day is encoded as circular feature to avoid discontinuity at midnight:

```python
hour = 6.5  # 6:30 AM
angle = 2π × hour / 24
hour_sin = sin(angle)
hour_cos = cos(angle)
```

This ensures:
- 11:59 PM and 12:01 AM are close in feature space
- Daily patterns (morning warmup, evening cooldown) are captured

### 4. XGBoost Model

We use **XGBoost Regressor** for prediction:

**Advantages:**
- Excellent performance on small datasets
- Handles non-linear relationships
- Built-in feature importance
- Fast training and prediction

**Default Hyperparameters:**
```python
{
    "objective": "reg:squarederror",
    "max_depth": 4,
    "learning_rate": 0.1,
    "n_estimators": 100,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 2,
    "random_state": 42,
}
```

## Training Pipeline

### Initial Training

```
1. Extract Historical Data (6 months default)
   ↓
2. Reconstruct Heating Cycles
   ├─ Identify heating start times
   ├─ Identify when target was reached
   └─ Extract environmental data
   ↓
3. Filter Valid Cycles
   ├─ Remove cycles where target never reached
   ├─ Remove cycles with excessive error (>30 min)
   └─ Minimum 10 cycles required
   ↓
4. Engineer Features
   ├─ Calculate lagged temperature values
   ├─ Calculate lagged power states
   └─ Encode time-of-day cyclically
   ↓
5. Label Cycles
   └─ Apply error-driven labeling formula
   ↓
6. Train XGBoost Model
   ├─ Input: Lagged features (X)
   ├─ Target: Optimal duration in minutes (Y)
   └─ Evaluate RMSE and MAE
   ↓
7. Persist Model
   └─ Serialize with pickle and save to HA storage
```

### Continuous Learning

```
1. Observe New Heating Cycle
   ↓
2. Record Cycle Data
   ├─ Features at heating start
   └─ Actual outcome
   ↓
3. Calculate Optimal Label
   └─ Apply error-driven labeling
   ↓
4. Store Training Example
   └─ Add to "New Examples" collection
   ↓
5. Check Retraining Trigger
   ├─ Weekly schedule OR
   ├─ 20+ new examples OR
   └─ Manual trigger
   ↓
6. Retrain Model
   ├─ Load existing model
   ├─ Add new examples
   ├─ Retrain XGBoost
   ├─ Evaluate improvement
   └─ Save if RMSE decreases
```

## Data Requirements

### Minimum Requirements

- **10 heating cycles** minimum for initial training
- **6 months** of historical data recommended
- **Temperature sensor** with 5-minute resolution
- **Power state** tracking (heating on/off)

### Optional Enhancements

- Outdoor temperature sensor
- Indoor humidity sensor
- Multiple rooms for comparative learning

## Usage Example

### Domain Layer (Testable, No HA)

```python
from domain.services import (
    FeatureEngineeringService,
    MLPredictionService,
    CycleLabelingService,
)
from domain.value_objects import HeatingCycle, LaggedFeatures

# 1. Label a heating cycle
labeler = CycleLabelingService()
optimal_duration = labeler.label_heating_cycle(cycle)

# 2. Engineer features
engineer = FeatureEngineeringService()
features = engineer.create_lagged_features(
    current_temp=20.0,
    target_temp=22.0,
    current_time=datetime.now(),
    temp_history=[(t1, 19.5), (t2, 19.0), ...],
    power_history=[(t1, False), (t2, True), ...],
)

# 3. Train model
ml_service = MLPredictionService()
X_train = [features.to_feature_dict() for features in feature_list]
y_train = [optimal_durations]
metrics = ml_service.train_model(X_train, y_train)

# 4. Make prediction
predicted_minutes = ml_service.predict_duration(features)

# 5. Serialize model
model_bytes = ml_service.serialize_model()
```

### Application Layer (With HA)

```python
from application import MLTrainingApplicationService

# Initialize with HA adapters
training_service = MLTrainingApplicationService(
    historical_reader=ha_reader,
    model_storage=ha_storage,
)

# Train model for a room
results = await training_service.train_model_for_room(
    room_id="climate.bedroom",
    lookback_months=6,
    min_cycles=10,
)

# Retrain with new data
results = await training_service.retrain_model_with_new_data(
    room_id="climate.bedroom"
)
```

## Model Performance Metrics

### Training Metrics

- **RMSE (Root Mean Square Error)**: Average prediction error in minutes
- **MAE (Mean Absolute Error)**: Median prediction error in minutes
- **R² Score**: Percentage of variance explained (higher is better)

**Acceptable Performance:**
- RMSE < 10 minutes: Excellent
- RMSE 10-15 minutes: Good
- RMSE 15-20 minutes: Acceptable
- RMSE > 20 minutes: Needs more data or feature tuning

### Prediction Confidence

The system tracks confidence based on:
1. **Data quantity**: More training cycles = higher confidence
2. **Prediction consistency**: Similar recent predictions = higher confidence
3. **Feature completeness**: All sensors available = higher confidence

## Troubleshooting

### Issue: Model predictions are inaccurate

**Possible Causes:**
1. Insufficient training data (<10 cycles)
2. Highly variable heating patterns
3. Missing environmental sensors
4. Temperature sensor drift

**Solutions:**
1. Collect more data (wait for more heating cycles)
2. Filter outlier cycles during training
3. Add outdoor temperature and humidity sensors
4. Calibrate temperature sensors

### Issue: Model doesn't improve with retraining

**Possible Causes:**
1. New data is similar to existing data
2. System conditions have changed (different season)
3. Insufficient new examples (<5)

**Solutions:**
1. Wait for more diverse conditions
2. Retrain seasonally (fall, winter, spring)
3. Collect more new examples before retraining

## Future Enhancements

### Planned Features

1. **Multi-Room Learning**: Share knowledge between similar rooms
2. **Weather Integration**: Use forecast data for better predictions
3. **Occupancy Detection**: Adjust predictions based on presence
4. **Seasonal Models**: Separate models for different seasons
5. **Hyperparameter Tuning**: Automatic optimization of XGBoost parameters

### Advanced Features

1. **Transfer Learning**: Bootstrap new rooms with existing models
2. **Ensemble Models**: Combine multiple models for robustness
3. **Explainability**: Show why model made specific predictions
4. **A/B Testing**: Compare ML predictions vs. simple LHS

## Testing Strategy

### Domain Layer Tests (Fast, No HA)

```python
# Test feature engineering
def test_lagged_features():
    service = FeatureEngineeringService()
    features = service.create_lagged_features(...)
    assert features.temp_lag_15min is not None

# Test ML service
def test_model_training():
    service = MLPredictionService()
    metrics = service.train_model(X_train, y_train)
    assert metrics["rmse"] > 0

# Test cycle labeling
def test_error_driven_labeling():
    labeler = CycleLabelingService()
    optimal = labeler.calculate_optimal_duration(60.0, 15.0)
    assert optimal == 45.0  # 60 - 15
```

### Integration Tests (With Mock HA)

```python
async def test_training_pipeline():
    # Mock historical reader
    mock_reader = AsyncMock(spec=IHistoricalDataReader)
    mock_reader.get_heating_cycles.return_value = [cycle1, cycle2, ...]
    
    # Test training
    service = MLTrainingApplicationService(mock_reader, mock_storage)
    results = await service.train_model_for_room("room1")
    
    assert results["cycles_valid"] >= 10
```

## References

- [XGBoost Documentation](https://xgboost.readthedocs.io/)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
- [Time Series Feature Engineering](https://otexts.com/fpp3/)
- [Error-Driven Learning](https://en.wikipedia.org/wiki/Supervised_learning)

## Appendix: Database Schema

### HeatingCycle Table (Conceptual)

```sql
CREATE TABLE heating_cycles (
    cycle_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    heating_started_at TIMESTAMP NOT NULL,
    target_time TIMESTAMP NOT NULL,
    target_reached_at TIMESTAMP,
    initial_temp REAL NOT NULL,
    target_temp REAL NOT NULL,
    final_temp REAL NOT NULL,
    outdoor_temp REAL,
    humidity REAL,
    actual_duration_minutes REAL NOT NULL,
    error_minutes REAL NOT NULL
);
```

### TrainingExamples Table

```sql
CREATE TABLE training_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    features JSON NOT NULL,  -- Lagged features as JSON
    target REAL NOT NULL,    -- Optimal duration
    timestamp TIMESTAMP NOT NULL
);
```

### MLModels Table

```sql
CREATE TABLE ml_models (
    room_id TEXT PRIMARY KEY,
    model_data BLOB NOT NULL,  -- Pickled XGBoost model
    metadata JSON NOT NULL,    -- Training metrics, timestamp
    saved_at TIMESTAMP NOT NULL
);
```
