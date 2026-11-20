# Port Contracts: Configuration menus and central default configuration

Signatures only. Method bodies are stubs. Ports are abstract base classes in
`domain/interfaces/`, fully typed, with Google-style docstrings in the real files.

```python
class SettingScope(Enum):
    DEVICE = "device"
    SHAREABLE = "shareable"


class SettingTheme(Enum):
    THERMOSTAT_SCHEDULERS = "thermostat_schedulers"
    NATIVE_SCHEDULE = "native_schedule"
    WAKE_UP_SOURCES = "wake_up_sources"
    ENVIRONMENT = "environment"
    LEARNING = "learning"
    CYCLE_DETECTION = "cycle_detection"
    ANTICIPATION = "anticipation"


@dataclass(frozen=True)
class SettingDefinition:
    key: str
    theme: SettingTheme
    scope: SettingScope
    default: object | None
    optional: bool = False


class SettingSource(Enum):
    OVERRIDE = "override"
    CENTRAL = "central"
    DEFAULT = "default"


@dataclass(frozen=True)
class ResolvedSetting:
    key: str
    value: object | None
    source: SettingSource


class SettingsCatalog:
    """The declared settings. Stateless: a fixed tuple of definitions."""

    def all(self) -> tuple[SettingDefinition, ...]: ...

    def of_theme(self, theme: SettingTheme) -> tuple[SettingDefinition, ...]: ...

    def shareable(self) -> tuple[SettingDefinition, ...]: ...

    def get(self, key: str) -> SettingDefinition:
        """Raise KeyError for an undeclared key."""


class SettingsResolver:
    """Pure resolution rule: override, else central, else default."""

    def resolve(
        self,
        catalog: SettingsCatalog,
        device_values: Mapping[str, object | None],
        central_values: Mapping[str, object | None],
    ) -> Mapping[str, ResolvedSetting]: ...


class ICentralConfigReader(ABC):
    """Reads the central values (shareable settings only)."""

    @abstractmethod
    def read_central_values(self) -> Mapping[str, object | None]:
        """Return the stored central values, or an empty mapping when no central entry exists."""
```

## Infrastructure contracts (no domain port, Home Assistant specific)

```python
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_CENTRAL = "central"
CENTRAL_UNIQUE_ID = "central_configuration"


def is_central_entry(entry: ConfigEntry) -> bool: ...


async def ensure_central_entry(hass: HomeAssistant) -> None:
    """Start the import flow that creates the central entry; a no-op when it exists."""


def devices_to_reload(
    device_entries: Sequence[ConfigEntry], changed_keys: Collection[str]
) -> list[ConfigEntry]:
    """Device entries that hold none of the changed keys (they inherit them)."""
```

## Behaviors the tests pin

- `resolve` never reads a `DEVICE` setting from `central_values`.
- `resolve` treats a key present with value `None` as `OVERRIDE`.
- `read_central_values` returns an empty mapping when the central entry was removed.
- `devices_to_reload` returns no device when every changed key is overridden.
- `ensure_central_entry` called twice creates one entry.
