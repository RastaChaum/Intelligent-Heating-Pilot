# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.4.4] - 2026-01-04

### Fixed
- **Integration Failed to Start** ([#67](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/67))
  - Fixed `TypeError: '>' not supported between instances of 'NoneType' and 'int'` when `cycle_split_duration_minutes` is not configured
  - Integration now properly handles cases where cycle split duration is not set
  - Ensures compatibility with Home Assistant 2026.1.0 beta
- **Optional Fields Persistence in Options Flow** ([#54](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/54), [#65](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/65))
  - Fixed inability to clear optional entity fields (indoor humidity, outdoor humidity, cloud cover) in configuration UI
  - Replaced `default=value` with `description={'suggested_value': value}` for optional entity selectors to allow proper clearing
  - Implemented explicit deletion logic to remove cleared optional fields from saved options
  - Added validation for required fields (VTherm and Schedulers) with clear error messages
  - Improved options merging to handle cleared values correctly

## [0.4.3] - 2025-12-23

### Added
- **Configurable Heating Cycle Detection Parameters** - New UI configuration options to fine-tune cycle detection and Learning Heating Slope (LHS) calculation for different heating systems
  - **Temperature Detection Threshold** (default: 0.2°C): Sensitivity for cycle start/end detection. Lower values increase detection sensitivity for heating systems with subtle temperature changes
  - **Cycle Split Duration** (default: None/disabled): Optional splitting of long heating cycles into sub-cycles for ML training data augmentation
  - **Minimum Cycle Duration** (default: 5 min): Filters out short micro-cycles caused by heating system switching noise
  - **Maximum Cycle Duration** (default: 300 min / 5h): Filters out abnormally long cycles that may indicate sensor malfunctions or system errors
  - All parameters configurable via integration UI (both initial setup and options flow)
  - Full English and French translations
  - Backward compatible with sensible defaults

### Changed
- **HeatingCycleService** now accepts configuration parameters instead of using hardcoded values, enabling per-installation customization
- **REST API** for cycle extraction now uses configured parameters from the coordinator instead of hardcoded defaults
- **Documentation Updates**:
  - Updated CONFIGURATION.md with new advanced configuration section for cycle detection parameters
  - Updated USER_GUIDE.md with guidance on tuning parameters for different heating systems
  - Improved consistency across all user-facing documentation

### Fixed
- Heating cycle detection now adaptable to different heating system characteristics (intermittent heating, micro-cutoffs, etc.)
- **Cycle Split Duration** parameter now uses 0 as default value to indicate "disabled" (instead of leaving field empty which caused validation errors)

## [0.4.2] - 2025-12-19

### Added
- **Incremental Cycle Cache for LHS Calculation** - New cache system to store heating cycles incrementally, drastically reducing Home Assistant recorder queries and enabling longer retention periods than HA's native history
  - New `CycleCacheData` value object to store cycles with metadata
  - New `ICycleCache` interface for cache operations  
  - New `HACycleCache` adapter using HA Store for JSON persistence
  - Automatic deduplication and retention-based pruning
  - Graceful degradation to direct recorder queries if cache unavailable
  - Comprehensive unit and integration tests (28 tests total)

### Changed
- **README Overhaul** - Complete redesign for better clarity and user experience
  - Reduced from ~300 to ~120 lines (60% reduction)
  - Eliminated redundancies with dedicated documentation
  - Improved visual flow and natural chapter progression
  - Updated version references to 0.4.1 (removed outdated 0.3.0 mentions)
  - Clearer Quick Start with concrete example
  - Simplified navigation with documentation table

## [0.4.1] - 2025-12-18

### Changed
- Introduced/clarified a 24-hour TTL cache for both **global LHS** and **contextual LHS (per hour)**. During anticipation, stale or missing contextual entries trigger a recomputation from recent heating cycles (lookback window), updating both caches. If no cycles are available, IHP reuses a fresh cached global LHS or falls back to the persisted value.

### Added

### Changed

### Fixed

## [0.4.0] - 2025-12-18

### Added
- Heating cycle extraction service with REST endpoint and historical data adapters to build cycle lists suitable for learning ([#44](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/44), [#23](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/23)).
- New user documentation set (Installation, Configuration, Troubleshooting, User Guide) and updated "How It Works" flow.

### Changed
- Learned Heating Slope now comes solely from detected heating cycles, using start/end temperatures and a delta threshold to ignore maintenance phases (addresses [#44](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/44) and [#23](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/23)).
- Documentation refreshed with clearer LHS computation and cycle detection rules; README badge bumped to 0.4.0.

### Fixed
- Hardened adapters, decision strategies, and model storage with expanded unit/integration tests to improve stability.

## [0.3.1] - 2025-11-23

### Fixed
- **Pre-heating State Reset** ([f938cdd](https://github.com/RastaChaum/Intelligent-Heating-Pilot/commit/f938cdd))
  - Disabled pre-heating if schedulers are disabled
  - Fixed pre-heating status not resetting when scheduler updates anticipated start time
  - Ensures `_is_preheating_active` flag is properly cleared on schedule changes
  - Prevents incorrect pre-heating state persistence across scheduling updates

### Changed
- **Documentation Restructuring** ([#41](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/41))
  - Applied DRY (Don't Repeat Yourself) principle to all documentation
  - Removed ~1,400 lines of redundant and obsolete documentation
  - Achieved 100% English consistency across all documents
  - Merged Git branching strategy into `CONTRIBUTING.md` (single source of truth)
  - Consolidated documentation index (removed `DOCUMENTATION_MAP.md` duplicate)
  - Optimized agent documentation to focus on quick start vs detailed guides
  - Improved cross-referencing between documents

### Removed
- `.github/GIT_REALIGNMENT_GUIDE.md` - Obsolete contextual guide
- `.github/BRANCHING_STRATEGY.md` - Merged into `CONTRIBUTING.md`
- `.github/pull_request_template_feature.md` - Unused French template
- `.github/pull_request_template_release.md` - Unused French template
- `DOCUMENTATION_MAP.md` - Duplicate of `DOCS_INDEX.md`

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

[Unreleased]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.2...HEAD
[0.4.3]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.1.0
