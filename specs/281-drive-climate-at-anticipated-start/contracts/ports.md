# Port Contracts: Drive the climate at the anticipated start

Signatures only. Method bodies are stubs. All ports are abstract base classes in
`domain/interfaces/`, fully typed, with Google-style docstrings in the real files.

```python
class IPreheatActuator(ABC):
    """Starts, cancels and recovers a preheat for a slot (replaces ISchedulerCommander)."""

    @abstractmethod
    async def start(self, timeslot: ScheduledTimeslot) -> ActuationResult: ...

    @abstractmethod
    async def cancel(self, timeslot: ScheduledTimeslot, reason: CancelReason) -> None: ...

    @abstractmethod
    async def recover(self, next_timeslot_of: NextTimeslotOf) -> PreheatRecovery:
        """Reconcile a persisted preheat after a start or reload.

        The recorded slot is compared with the next slot of its OWN scheduler (given by
        ``next_timeslot_of``). NOTHING / RESUMED (with the slot) / RELEASED / DEFERRED: DEFERRED
        keeps the record because the scheduler could not answer, and the caller asks again."""


class ISchedulerOwnershipResolver(ABC):
    @abstractmethod
    def resolve(self, scheduler_entity_id: str) -> SchedulerKind: ...


class IClimateCommander(ABC):
    @abstractmethod
    async def apply(self, action: SlotAction) -> None: ...

    @abstractmethod
    async def restore(self, fields: RestoreFields) -> None:
        """Restore only the given fields; the HVAC mode is never written."""


class IPreheatRecordStore(ABC):
    @abstractmethod
    async def load(self) -> PreheatRecord | None: ...

    @abstractmethod
    async def save(self, record: PreheatRecord) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...
```

Additions to existing ports:

```python
class IClimateDataReader(ABC):
    @abstractmethod
    def read_climate_snapshot(self) -> ClimateSnapshot | None:
        """Requested state now; None when the climate is unavailable."""


class ISchedulerReader(ABC):
    @abstractmethod
    async def get_next_timeslot_of(self, scheduler_entity_id: str) -> ScheduledTimeslot | None: ...
```

`CancelReason` (enum): `SLOT_CHANGED`, `SCHEDULER_DISABLED`, `IHP_DISABLED`, `POSTPONED`,
`SLOT_REACHED`.

Behavior contracts:

- `start` never raises for an unsupported scheduler; it returns `UNSUPPORTED`.
- `start` returns `SKIPPED` when a guard stops it (climate off) and `NOT_APPLIED` when the
  climate did not take the action.
- `start` is serialized per instance: two concurrent calls for one slot record and apply once.
- `start` in direct mode saves the record before the first command and never overwrites an
  existing record for the same `timeslot_id`.
- Every command carries a context with a parent (adapter responsibility).
- `cancel` in direct mode restores only on `RESTORE`; the record is cleared in every case.
- HACS `cancel` calls `run_action` at the current time, as today.
- `recover` is idempotent and never decides on a missing answer.
- A record whose climate was changed by someone else is kept, marked claimed, until its slot, and
  `start` for that slot returns `SKIPPED`: a change by someone else is final for the slot.
