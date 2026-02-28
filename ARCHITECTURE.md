# Architecture Documentation

## 📐 Domain-Driven Design (DDD) Architecture

Intelligent Heating Pilot follows **Domain-Driven Design** principles with a strict separation between business logic and infrastructure concerns. This architecture ensures maintainability, testability, and independence from Home Assistant implementation details.

## 🎯 Core Principles

1. **Domain Independence**: Core business logic has zero dependencies on Home Assistant
2. **Interface-Driven Design**: All external interactions happen through Abstract Base Classes (ABCs)
3. **Immutability**: Value objects are immutable to prevent unexpected state changes
4. **Test-First**: Business logic is developed using Test-Driven Development (TDD)
5. **Single Responsibility**: Each component has one clear, well-defined purpose

## 🏗️ Layer Architecture

```
┌─────────────────────────────────────────────────┐
│          Home Assistant Core                     │
│          (Coordinator, Config Flow)              │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────┐
│        Application Layer                         │
│  (Use Cases & Orchestration)                     │
│  • HeatingApplicationService                     │
│  • Coordinates domain and infrastructure         │
└────────────────┬────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
┌───────▼──────┐  ┌──────▼─────────────────┐
│ Domain Layer │  │ Infrastructure Layer    │
│ (Pure Logic) │  │ (HA Integration)        │
└──────────────┘  └────────────────────────┘

Domain Layer (NO HA dependencies):
├── value_objects/
│   ├── environment_state.py        # Immutable environmental data
│   ├── schedule_timeslot.py        # Immutable schedule data
│   ├── prediction_result.py        # Immutable prediction data
│   ├── heating_decision.py         # Immutable decision data
│   └── slope_data.py               # Immutable slope data
├── entities/
│   └── heating_pilot.py            # Aggregate root (future)
├── interfaces/
│   ├── scheduler_reader.py         # ABC: Read scheduler
│   ├── scheduler_commander.py      # ABC: Control scheduler
│   ├── climate_commander.py        # ABC: Control climate
│   ├── environment_reader.py       # ABC: Read environment
│   └── model_storage.py            # ABC: Persist learning data
└── services/
    ├── prediction_service.py       # Calculate anticipation
    └── lhs_calculation_service.py  # Calculate learned heating slope

Infrastructure Layer (HA-specific):
└── adapters/
    ├── scheduler_reader.py         # Implements ISchedulerReader
    ├── scheduler_commander.py      # Implements ISchedulerCommander
    ├── climate_commander.py        # Implements IClimateCommander
    ├── environment_reader.py       # Implements IEnvironmentReader
    └── model_storage.py            # Implements IModelStorage
```

## 🔁 Event Bridge Signal Pattern

The event bridge publishes a **uniform data structure** to keep things simple and predictable:

1. **Complete structure with None values**: `{ "anticipated_start_time": None, "next_schedule_time": None, ... }`
    - Published when anticipation data cannot be calculated (e.g., no scheduler configured, no timeslot available)
    - Contains all expected fields, with None values for unavailable data
    - Sensors receive the None values and clear their state to `unknown`
2. **Complete structure with data**: `{ "anticipated_start_time": "2026-02-21T14:30:00", "next_schedule_time": "...", ... }`
    - Published when full prediction data is available
    - All fields contain real values and can be used as-is
3. **No publish**: `None`
    - Used when no update is needed (no change from previous state)

This pattern keeps the infrastructure simple: **always publish the same structure**, with None values indicating missing data. Sensors handle the None values naturally and update their state as needed.

## 📦 Value Objects (Immutable Data Carriers)

Value objects are **immutable** data structures that carry information between layers without containing logic.

### EnvironmentState

Represents the current environmental conditions:

```python
@dataclass(frozen=True)
class EnvironmentState:
    """Current environmental conditions."""
    current_temp: float
    outdoor_temp: float | None
    humidity: float | None
    cloud_coverage: float | None
    timestamp: datetime
```

### ScheduleTimeslot

Represents a scheduled heating event:

```python
@dataclass(frozen=True)
class ScheduleTimeslot:
    """A scheduled heating timeslot."""
    start_time: datetime
    target_temp: float
    schedule_id: str
```

### PredictionResult

Result of the anticipation calculation:

```python
@dataclass(frozen=True)
class PredictionResult:
    """Result of heating anticipation prediction."""
    anticipated_start_time: datetime
    anticipation_duration_minutes: float
    confidence_level: float
    reasoning: str
```

### SlopeData

Timestamped heating slope observation:

```python
@dataclass(frozen=True)
class SlopeData:
    """A single heating slope observation."""
    slope_value: float  # °C/h
    timestamp: datetime
```

## 🔌 Interfaces (Contracts)

Interfaces define contracts between the domain and infrastructure layers. The domain depends on these abstractions, not on concrete implementations.

### ISchedulerReader

Read scheduled events from a scheduler:

```python
class ISchedulerReader(ABC):
    """Contract for reading scheduled events."""

    @abstractmethod
    async def get_next_timeslot(self) -> ScheduleTimeslot | None:
        """Get the next scheduled heating timeslot."""
        pass

    @abstractmethod
    async def has_active_schedule(self) -> bool:
        """Check if any schedule is currently active."""
        pass
```

### ISchedulerCommander

Control the scheduler to trigger heating:

```python
class ISchedulerCommander(ABC):
    """Contract for commanding scheduler actions."""

    @abstractmethod
    async def trigger_schedule_action(
        self,
        schedule_id: str,
        target_temp: float
    ) -> None:
        """Trigger a scheduled heating action."""
        pass
```

### IClimateCommander

Control the climate device (VTherm):

```python
class IClimateCommander(ABC):
    """Contract for climate control actions."""

    @abstractmethod
    async def set_temperature(self, temperature: float) -> None:
        """Set the target temperature."""
        pass

    @abstractmethod
    async def set_hvac_mode(self, mode: str) -> None:
        """Set the HVAC mode (heat, off, etc.)."""
        pass
```

### IEnvironmentReader

Read current environmental state:

```python
class IEnvironmentReader(ABC):
    """Contract for reading environmental data."""

    @abstractmethod
    async def get_current_state(self) -> EnvironmentState:
        """Get the current environmental state."""
        pass
```

### IModelStorage

Persist and retrieve learned heating slopes:

```python
class IModelStorage(ABC):
    """Contract for persisting learning data."""

    @abstractmethod
    async def save_slope(self, slope: SlopeData) -> None:
        """Save a single slope observation."""
        pass

    @abstractmethod
    async def get_recent_slopes(
        self,
        max_count: int = 100
    ) -> list[SlopeData]:
        """Retrieve recent slope observations."""
        pass

    @abstractmethod
    async def clear_all_slopes(self) -> None:
        """Clear all stored slope data (reset learning)."""
        pass
```

## 🧠 Domain Services

Domain services contain pure business logic and operate on value objects.

### PredictionService

Calculates when to start heating based on learned data:

```python
class PredictionService:
    """Calculate heating anticipation predictions."""

    def __init__(
        self,
        scheduler_reader: ISchedulerReader,
        environment_reader: IEnvironmentReader,
        storage: IModelStorage,
    ) -> None:
        self._scheduler = scheduler_reader
        self._environment = environment_reader
        self._storage = storage

    async def calculate_anticipation(self) -> PredictionResult | None:
        """Calculate when to start heating for the next schedule.

        Returns:
            PredictionResult with anticipated start time and details,
            or None if no valid prediction can be made.
        """
        # Get next scheduled event
        next_timeslot = await self._scheduler.get_next_timeslot()
        if not next_timeslot:
            return None

        # Get current environmental state
        environment = await self._environment.get_current_state()

        # Get learned heating slope (LHS)
        lhs_service = LHSCalculationService(self._storage)
        lhs = await lhs_service.calculate_lhs()

        # Calculate base anticipation time
        delta_temp = next_timeslot.target_temp - environment.current_temp
        if delta_temp <= 0:
            return None  # Already at or above target

        base_minutes = (delta_temp / lhs) * 60

        # Apply environmental corrections
        correction_factor = 1.0

        if environment.humidity and environment.humidity > 70:
            correction_factor *= 1.10  # +10% for high humidity

        if environment.cloud_coverage and environment.cloud_coverage > 80:
            correction_factor *= 1.05  # +5% for heavy clouds

        # Apply corrections and safety buffer
        adjusted_minutes = base_minutes * correction_factor + 5

        # Constrain to reasonable limits
        final_minutes = max(10, min(180, adjusted_minutes))

        # Calculate start time
        anticipated_start = next_timeslot.start_time - timedelta(
            minutes=final_minutes
        )

        return PredictionResult(
            anticipated_start_time=anticipated_start,
            anticipation_duration_minutes=final_minutes,
            confidence_level=0.8,  # TODO: Calculate based on data quality
            reasoning=f"Delta: {delta_temp:.1f}°C, LHS: {lhs:.2f}°C/h"
        )
```

### LHSCalculationService

Calculates the Learned Heating Slope using robust statistics:

```python
class LHSCalculationService:
    """Calculate Learned Heating Slope (LHS) from observations."""

    DEFAULT_LHS = 2.0  # °C/h (conservative cold start value)

    def __init__(self, storage: IModelStorage) -> None:
        self._storage = storage

    async def calculate_lhs(self) -> float:
        """Calculate LHS using trimmed mean (robust average).

        Returns:
            Learned heating slope in °C/h
        """
        slopes = await self._storage.get_recent_slopes(max_count=100)

        if not slopes:
            return self.DEFAULT_LHS

        # Extract slope values
        values = [s.slope_value for s in slopes if s.slope_value > 0]

        if len(values) < 3:
            return self.DEFAULT_LHS

        # Sort and trim outliers (10% from each end)
        sorted_values = sorted(values)
        trim_count = int(len(sorted_values) * 0.1)

        if trim_count > 0:
            trimmed = sorted_values[trim_count:-trim_count]
        else:
            trimmed = sorted_values

        # Calculate trimmed mean
        return sum(trimmed) / len(trimmed)
```

## 🔧 Infrastructure Adapters

Adapters implement domain interfaces using Home Assistant APIs. They are **thin translation layers** with no business logic.

### HASchedulerReader

Reads scheduler state from Home Assistant:

```python
class HASchedulerReader(ISchedulerReader):
    """Home Assistant implementation of ISchedulerReader."""

    def __init__(
        self,
        hass: HomeAssistant,
        scheduler_entity_ids: list[str],
        vtherm_entity_id: str,
    ) -> None:
        self._hass = hass
        self._scheduler_ids = scheduler_entity_ids
        self._vtherm_id = vtherm_entity_id

    async def get_next_timeslot(self) -> ScheduleTimeslot | None:
        """Read next timeslot from HA scheduler."""
        for entity_id in self._scheduler_ids:
            state = self._hass.states.get(entity_id)
            if not state:
                continue

            # Extract next_entries from attributes
            next_entries = state.attributes.get("next_entries", [])
            if not next_entries:
                continue

            # Get first entry
            entry = next_entries[0]

            # Parse timestamp
            start_time = dt_util.parse_datetime(entry["time"])
            if not start_time:
                continue

            # Resolve target temperature from VTherm preset
            target_temp = await self._resolve_target_temp(
                entry["actions"]
            )

            return ScheduleTimeslot(
                start_time=start_time,
                target_temp=target_temp,
                schedule_id=entity_id,
            )

        return None

    async def _resolve_target_temp(self, actions: list) -> float:
        """Resolve target temperature from scheduler actions."""
        # Implementation details...
        pass
```

### HAModelStorage

Persists learned slopes in Home Assistant's storage:

```python
class HAModelStorage(IModelStorage):
    """Home Assistant storage implementation."""

    def __init__(self, store: Store) -> None:
        self._store = store

    async def save_slope(self, slope: SlopeData) -> None:
        """Save slope to HA storage."""
        data = await self._store.async_load() or {"slopes": []}

        slopes = data.get("slopes", [])
        slopes.append({
            "value": slope.slope_value,
            "timestamp": slope.timestamp.isoformat(),
        })

        # Keep only last 100
        if len(slopes) > 100:
            slopes = slopes[-100:]

        data["slopes"] = slopes
        await self._store.async_save(data)

    async def get_recent_slopes(
        self,
        max_count: int = 100
    ) -> list[SlopeData]:
        """Load slopes from HA storage."""
        data = await self._store.async_load()
        if not data:
            return []

        slopes_data = data.get("slopes", [])
        return [
            SlopeData(
                slope_value=s["value"],
                timestamp=dt_util.parse_datetime(s["timestamp"]),
            )
            for s in slopes_data[-max_count:]
        ]
```

## 🎬 Application Layer

The application layer orchestrates domain services and infrastructure adapters to fulfill use cases.

### HeatingApplicationService

Main orchestration service:

```python
class HeatingApplicationService:
    """Orchestrates heating pilot operations."""

    def __init__(
        self,
        prediction_service: PredictionService,
        scheduler_commander: ISchedulerCommander,
        climate_commander: IClimateCommander,
        storage: IModelStorage,
    ) -> None:
        self._prediction = prediction_service
        self._scheduler_cmd = scheduler_commander
        self._climate_cmd = climate_commander
        self._storage = storage

    async def calculate_and_schedule_heating(self) -> PredictionResult | None:
        """Main use case: calculate anticipation and schedule heating."""
        # Calculate when to start
        prediction = await self._prediction.calculate_anticipation()

        if not prediction:
            _LOGGER.debug("No valid prediction available")
            return None

        _LOGGER.info(
            "Predicted anticipation: %s minutes, start at %s",
            prediction.anticipation_duration_minutes,
            prediction.anticipated_start_time,
        )

        # Schedule heating action (handled by coordinator timer)
        # The coordinator will call trigger_heating() at the right time

        return prediction

    async def trigger_heating(
        self,
        schedule_id: str,
        target_temp: float
    ) -> None:
        """Trigger heating at the anticipated time."""
        # Trigger scheduler action
        await self._scheduler_cmd.trigger_schedule_action(
            schedule_id=schedule_id,
            target_temp=target_temp,
        )

        # Ensure HVAC mode is heat
        await self._climate_cmd.set_hvac_mode("heat")

        _LOGGER.info("Heating triggered: %s -> %.1f°C", schedule_id, target_temp)

    async def record_slope_observation(self, slope_value: float) -> None:
        """Record a new heating slope observation."""
        if slope_value <= 0:
            return  # Ignore non-heating slopes

        slope = SlopeData(
            slope_value=slope_value,
            timestamp=datetime.now(),
        )

        await self._storage.save_slope(slope)
        _LOGGER.debug("Recorded slope: %.2f °C/h", slope_value)
```

## 🧪 Testing Strategy

### Domain Layer Tests

Domain tests must be **fast** (<1 second) and require **no Home Assistant**:

```python
# tests/unit/domain/test_prediction_service.py
from unittest.mock import AsyncMock, Mock
from domain.services.prediction_service import PredictionService
from domain.interfaces.scheduler_reader_interface import ISchedulerReader

def test_prediction_calculates_correct_anticipation():
    # GIVEN: Mocked dependencies
    mock_scheduler = AsyncMock(spec=ISchedulerReader)
    mock_scheduler.get_next_timeslot.return_value = ScheduleTimeslot(
        start_time=datetime(2025, 1, 1, 7, 0),
        target_temp=21.0,
        schedule_id="schedule.morning",
    )

    mock_environment = AsyncMock(spec=IEnvironmentReader)
    mock_environment.get_current_state.return_value = EnvironmentState(
        current_temp=18.0,
        outdoor_temp=5.0,
        humidity=65.0,
        cloud_coverage=50.0,
        timestamp=datetime(2025, 1, 1, 5, 0),
    )

    mock_storage = AsyncMock(spec=IModelStorage)
    mock_storage.get_recent_slopes.return_value = [
        SlopeData(slope_value=2.0, timestamp=datetime.now())
    ]

    # WHEN: Service calculates anticipation
    service = PredictionService(
        scheduler_reader=mock_scheduler,
        environment_reader=mock_environment,
        storage=mock_storage,
    )

    result = await service.calculate_anticipation()

    # THEN: Result is accurate
    assert result is not None
    assert result.anticipation_duration_minutes == pytest.approx(95, rel=0.1)
    assert result.anticipated_start_time == datetime(2025, 1, 1, 5, 25)
```

### Infrastructure Tests

Infrastructure tests verify adapters correctly translate between HA and domain:

```python
# tests/unit/infrastructure/adapters/test_scheduler_reader.py
async def test_ha_scheduler_reader_parses_next_timeslot():
    # GIVEN: Mock Home Assistant state
    mock_hass = Mock()
    mock_state = Mock()
    mock_state.attributes = {
        "next_entries": [
            {
                "time": "2025-01-01T07:00:00+00:00",
                "actions": [
                    {
                        "service": "climate.set_preset_mode",
                        "data": {"preset_mode": "comfort"},
                    }
                ],
            }
        ]
    }
    mock_hass.states.get.return_value = mock_state

    # WHEN: Adapter reads next timeslot
    adapter = HASchedulerReader(
        hass=mock_hass,
        scheduler_entity_ids=["switch.schedule_morning"],
        vtherm_entity_id="climate.vtherm",
    )

    timeslot = await adapter.get_next_timeslot()

    # THEN: Timeslot is correctly parsed
    assert timeslot is not None
    assert timeslot.start_time == datetime(2025, 1, 1, 7, 0, tzinfo=UTC)
    assert timeslot.target_temp == 21.0  # Resolved from comfort preset
```

## 📊 Data Flow Example

Here's how a complete heating anticipation cycle works:

```
1. Coordinator Timer Fires
   └─> HeatingApplicationService.calculate_and_schedule_heating()

2. Application Service Orchestrates
   └─> PredictionService.calculate_anticipation()
       ├─> ISchedulerReader.get_next_timeslot()
       │   └─> HASchedulerReader reads HA state
       │       └─> Returns ScheduleTimeslot (immutable)
       │
       ├─> IEnvironmentReader.get_current_state()
       │   └─> HAEnvironmentReader reads HA sensors
       │       └─> Returns EnvironmentState (immutable)
       │
       ├─> LHSCalculationService.calculate_lhs()
       │   └─> IModelStorage.get_recent_slopes()
       │       └─> HAModelStorage reads from HA storage
       │           └─> Returns list[SlopeData] (immutable)
       │
       └─> Returns PredictionResult (immutable)

3. Coordinator Schedules Timer
   └─> Waits until anticipated_start_time

4. Timer Fires at Anticipated Time
   └─> HeatingApplicationService.trigger_heating()
       ├─> ISchedulerCommander.trigger_schedule_action()
       │   └─> HASchedulerCommander calls HA service
       │
       └─> IClimateCommander.set_hvac_mode("heat")
           └─> HAClimateCommander calls HA service

5. VTherm Heats Room
   └─> Temperature rises

6. Slope Observation
   └─> HeatingApplicationService.record_slope_observation()
       └─> IModelStorage.save_slope()
           └─> HAModelStorage persists to HA storage
```

## 🔒 Key Architectural Benefits

### 1. **Testability**
- Domain logic tested without Home Assistant
- Fast unit tests (<1 second)
- Easy to mock dependencies via interfaces

### 2. **Maintainability**
- Clear separation of concerns
- Changes to HA API only affect infrastructure layer
- Business logic remains stable

### 3. **Flexibility**
- Easy to swap implementations (e.g., different storage)
- Domain can be reused in other contexts
- Simple to add new features

### 4. **Clarity**
- Explicit contracts via interfaces
- Immutable value objects prevent bugs
- Single responsibility per component

## 🚫 What NOT to Do

### ❌ Don't Mix Layers

```python
# BAD: Domain service directly accessing Home Assistant
class PredictionService:
    def calculate(self, hass: HomeAssistant):
        state = hass.states.get("climate.vtherm")  # NO!
```

### ❌ Don't Put Business Logic in Infrastructure

```python
# BAD: Business rule in adapter
class HASchedulerReader:
    async def get_next_timeslot(self):
        timeslot = ...  # Read from HA
        if timeslot.target_temp < 20:  # Business rule!
            return None
```

### ❌ Don't Make Value Objects Mutable

```python
# BAD: Mutable value object
@dataclass
class EnvironmentState:  # Missing frozen=True
    current_temp: float

# This allows bugs:
state.current_temp = 999  # Oops!
```

## ✅ Do This Instead

### ✅ Use Interfaces for All External Interactions

```python
# GOOD: Domain depends on abstraction
class PredictionService:
    def __init__(self, scheduler: ISchedulerReader):
        self._scheduler = scheduler  # Interface, not concrete class
```

### ✅ Keep Adapters Thin

```python
# GOOD: Adapter only translates
class HASchedulerReader:
    async def get_next_timeslot(self):
        state = self._hass.states.get(...)
        return ScheduleTimeslot(...)  # Just data translation
```

### ✅ Use Immutable Value Objects

```python
# GOOD: Immutable value object
@dataclass(frozen=True)
class EnvironmentState:
    current_temp: float

# This prevents bugs:
state.current_temp = 999  # Error: frozen dataclass!
```

## 📚 Further Reading

- [Domain-Driven Design (Eric Evans)](https://www.domainlanguage.com/ddd/)
- [Hexagonal Architecture (Ports and Adapters)](https://alistair.cockburn.us/hexagonal-architecture/)
- [Clean Architecture (Robert C. Martin)](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Test-Driven Development](https://martinfowler.com/bliki/TestDrivenDevelopment.html)
