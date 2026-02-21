# Development Standards - Intelligent Heating Pilot

**Quick reference for IHP contributors.** For architectural principles, testing strategy, and code examples, see [copilot-instructions.md](./copilot-instructions.md).

---

## 📝 Code Style

### Type Hints (Required)

```python
# ✅ Always complete type hints
async def calculate_and_schedule(
    environment: EnvironmentState,
    next_event: ScheduleEvent,
    ihp_enabled: bool
) -> PreheatingDecision:
    """Make heating decision based on environment and schedule."""
```

### Docstrings (Google Style)

```python
def compute_slope(temps: list[float], durations: list[int]) -> float:
    """Calculate heating slope from temperature sequence.

    Args:
        temps: Ordered temperature readings in Celsius.
        durations: Duration between readings in seconds.

    Returns:
        Slope in degrees per minute.

    Raises:
        ValueError: If lists are empty or different lengths.
    """
```

### Naming Conventions

| What | Pattern | Example |
|------|---------|---------|
| Domain classes | CamelCase | `PilotController`, `EnvironmentState` |
| Domain methods | snake_case, verb first | `calculate_slope()`, `decide_heating_action()` |
| Constants | UPPER_SNAKE_CASE | `DEFAULT_THERMAL_MASS_KWH = 2.5` |
| Private methods | `_leading_underscore` | `_validate_inputs()` |

---

## 📊 Logging Standards


### Levels

| Level | Use for | Example | Layer |
|-------|---------|---------|-------|
| **DEBUG** | Method entry/exit, parameters, return values | `logger.debug("Received temps: %s", temps)` | domain + infra |
| **INFO** | State changes, business results | `logger.info("Heating started (target: %.1f°C)", target)` | infra only |
| **WARNING** | Recoverable issues | `logger.warning("Outdoor sensor missing, using default")` | infra |
| **ERROR** | Unrecoverable failures | `logger.error("Invalid configuration")` | infra |

### Device Names in Logs

Always use `friendly_name` (user-friendly) instead of entity ID:

```python
# ✅ Good
friendly_name = self.hass.states.get(self.entity_id).attributes.get("friendly_name")
logger.info("Started heating on '%s'", friendly_name)

# ❌ Bad
logger.info("Started heating on %s", self.entity_id)  # Shows "climate.living_room"

---

## ✅ Pull Request Checklist

Before merging, verify:

- [ ] **Domain**: No `homeassistant.*` imports
- [ ] **Type hints**: All functions/methods complete
- [ ] **Docstrings**: All public classes and methods documented
- [ ] **Tests**: BDD feature + unit tests FAILED before GREEN
- [ ] **Coverage**: >80% of domain logic
- [ ] **Logging**: DEBUG on entry/exit, INFO on state changes
- [ ] **Naming**: Follows conventions above
- [ ] **Peer review**: Discussed with Software Architect and QA Engineer

---

## 📚 Quick References

- **Home Assistant Standards**: https://developers.home-assistant.io/docs/development_standards
- **PyR Checklist

Before submitting:

- [ ] **DDD boundaries respected** (no HA imports in domain)
- [ ] **All functions typed** (`-> ReturnType`)
- [ ] **All public methods documented** (Google-style docstrings)
- [ ] **Tests pass** (BDD + unit, >80% domain coverage)
- [ ] **Logging complete** (DEBUG on entry/exit, INFO on state change)
- [ ] **Names follow conventions** (CamelCase classes, snake_case methods)

---

## 📚 References

| Topic | Link |
|-------|------|
| **Architecture** | [copilot-instructions.md](./copilot-instructions.md) → DDD, layers, domain purity |
| **Testing** | [copilot-instructions.md](./copilot-instructions.md) → TDD, BDD, test structure |
| **Workflows** | [agents/README.md](./agents/README.md) → How agents work together |
| **HA Standards** | https://developers.home-assistant.io/docs/development_standards |
| **Python PEP 8** | https://pep8.org/ |
| **DDD** | https://martinfowler.com/bliki/DomainDrivenDesign.html |

---

**Maintained by**: Software Architect
