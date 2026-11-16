# Contract: IScheduleSlotLookup

Domain port, `domain/interfaces/schedule_slot_lookup_interface.py`. A separate port from `ISchedulerReader` (interface segregation): only the combining reader needs it.

```python
class IScheduleSlotLookup(ABC):
    @abstractmethod
    async def get_slots_around(self, moment: datetime) -> SlotsAround:
        """Tell the schedule slots around a moment, over all configured schedulers.

        `following`: the first slot starting after the moment (earliest across schedulers).
        `in_effect`: the slot in effect at the moment, when a scheduler can say so.
        Absent means "cannot say", never "there is none".
        """
```

Per kind:

| Kind | `following` | `in_effect` |
| --- | --- | --- |
| Native schedule | from the weekly blocks | from the weekly blocks |
| HACS Scheduler | only when `next_trigger` is after the moment | never |
| Climate Scheduler | only when `next_trigger` is after the moment | never |

An excluded or disabled scheduler gives nothing. A scheduler that fails to read is skipped with a warning, as in the existing reader. The returned slots carry the preset-resolved temperature like any slot.
