# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.3.0] - 2025-11-19

### Added
- **Time-Windowed LHS Calculation**: Contextual learned heating slope calculation by time-of-day filtering ([#15](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/15))
  - New `LHSCalculationService` in domain layer for robust average calculation
  - UI configuration for `lhs_window_hours` (default: 6h) and `lhs_retention_days` per device
  - More accurate predictions based on time-context of historical data
- **VTherm v8.0.0 Compatibility Layer** ([#19](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/19), [#22](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/22))
  - New `vtherm_compat.py` adapter for backward-compatible attribute access
  - Support for `specific_states.*` nested structure in VTherm v8.0.0+
  - Support for new `preset_temperatures` dictionary format
  - Preset mode resolution (eco, boost, comfort) via `get_vtherm_attribute()`
  - Automatic handling of uninitialized presets (ignore 0 values at startup)
- **Storage Version Migration**: Async migration from v1 to v2 storage format
- **Domain Services**: New `domain/services/` layer for pure business logic
- Comprehensive documentation for contributors (CONTRIBUTING.md, ARCHITECTURE.md)
- GitHub issue templates for bug reports and feature requests
- Pull request template with architecture compliance checklist
- Release template and process documentation
- Documentation index (DOCS_INDEX.md) for easy navigation
- Documentation map (DOCUMENTATION_MAP.md) with visual structure
- GitHub Copilot agent instructions for documentation maintenance

### Changed
- **Scheduler Commander Initialization Simplified** ([#25](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/25))
  - Action methods now accept `entity_id` as parameter for better flexibility
  - Cleaner initialization without entity_id stored in constructor
- **LHS Calculation Moved to Domain**: Logic migrated from application/infrastructure to domain service (DDD compliance)
- **Logging Improvements**: Changed "No valid scheduler timeslot found" to DEBUG level to reduce noise
- **Deferred First Update**: Sensor `async_update()` now waits until HA is fully started to avoid false positives
- Documentation reorganized for clarity: user docs vs contributor docs
- All documentation translated to English for broader accessibility
- README simplified with focus on end-user experience
- Technical details moved from README to ARCHITECTURE.md

### Fixed
- **Issue #16**: Pre-heating revert on anticipated start time changes ([#25](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/25))
  - Added revert logic when anticipated start time changes significantly
  - Removed direct VTherm control to rely on scheduler actions only
  - Application service now handles revert scenarios properly
- **Issue #17**: Next target temperature and Scheduler entity attributes unvalued ([#21](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/21))
  - Fixed `next_target_temperature` attribute naming for consistency
  - Fixed scheduler entity attribute resolution
  - Fixed preset mode resolution when scheduler uses presets instead of temperature setpoints
  - Fixed attribute access for VTherm v8.0.0 nested structure
- **Issue #19**: VTherm v8.0.0+ compatibility ([#22](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/22))
  - Fixed attribute access for new `specific_states.*` structure
  - Fixed preset temperature resolution from `preset_temperatures` dictionary
- Storage version handling: Proper revert to v1 with async migration to v2
- State type hint: Allow `None` in `get_vtherm_attribute()` function
- Import paths: Updated test files to use `custom_components` directly

## [0.2.1] - 2025-11-16

### Changed
- Removed optional remote debugging code (debugpy) from integration entrypoint

## [0.2.0] - 2025-11-16

### Added
- Application layer: `HeatingApplicationService` orchestrating domain and infrastructure
- Infrastructure adapters: `HAClimateCommander`, `HAEnvironmentReader`
- Event bridge: `HAEventBridge` publishes `intelligent_heating_pilot_anticipation_calculated` events
- Scheduler integration: `HASchedulerReader` resolves `climate.set_preset_mode` via VTherm attributes
- Sensors: HMS (HH:MM:SS) display companions for Anticipated Start and Next Schedule
- Domain constants: `domain/constants.py` for business constants (DDD-compliant)

### Changed
- Coordinator fully refactored to thin DDD-compliant orchestrator
- Initial anticipation calculation now runs on setup to populate sensors immediately
- Debugpy made optional (non-blocking if not installed)
- Prediction service imports domain constants instead of infrastructure `const`
- LHS sensor now updates live from event payload with cache refresh

### Fixed
- Event bridge recalculates and publishes results when entities change
- Scheduler actions force HVAC mode to `heat` to prevent unintended `off` state
- Fixed sensor update timing issues

### Removed
- Legacy `calculator.py` module

## [0.1.0] - 2025-11-10

### Added
- Initial alpha release of Intelligent Heating Pilot
- Smart predictive pre-heating (Adaptive Start) feature
- Statistical learning from VTherm's thermal slope observations
- Multi-factor awareness (humidity, cloud coverage)
- Thermal slope aggregation using trimmed mean (robust statistics)
- Integration with Versatile Thermostat and HACS Scheduler
- Real-time sensors for monitoring:
  - Learned Heating Slope (LHS)
  - Anticipation Time
  - Next Schedule
- Configuration interface via Home Assistant UI
- Service: `intelligent_heating_pilot.reset_learning` to clear learned data
- Comprehensive README with usage examples and calculations

### Architecture
- Domain-Driven Design (DDD) architecture implemented
- Clean separation between domain, infrastructure, and application layers
- Interface-based design with Abstract Base Classes (ABCs)
- Test-Driven Development (TDD) with comprehensive unit tests

---

## Release Links

[Unreleased]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.1.0
