# Contract: IWakeUpSourceReader

Domain port, `domain/interfaces/wake_up_source_reader_interface.py`. Implemented by `HAWakeUpSourceReader` (infrastructure). No business rule: it translates a state into a reading.

```python
class IWakeUpSourceReader(ABC):
    @abstractmethod
    def read(self, entity_id: str) -> WakeUpReading:
        """Read the point in time held by a source entity.

        Returns a reading whose value is an aware datetime, or None with the reason
        (unknown, unavailable, date-only or time-only, unparsable). Never raises for a bad
        value. The same issue on the same entity is logged once until the value changes.
        """
```

Accepted: `sensor` (device class timestamp), `datetime`, `input_datetime` with date and time. A naive value is taken in the Home Assistant time zone.
