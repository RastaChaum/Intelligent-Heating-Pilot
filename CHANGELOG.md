# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2025-11-16

### Added
- Application: HeatingApplicationService orchestrating domain and infra
- Infrastructure: `HAClimateCommander`, `HAEnvironmentReader`
- Infrastructure: `HAEventBridge` publishes `intelligent_heating_pilot_anticipation_calculated`
- Infrastructure: `HASchedulerReader` resolves `climate.set_preset_mode` via VTherm attributes
- Sensors: HMS display companions for Anticipated Start and Next Schedule (HH:MM:SS)
- Sensors: LHS updates live from event payload and refreshes caches
- Domain: `domain/constants.py` to host business constants (DDD-compliant)

### Changed
- Coordinator fully refactored to a thin DDD-compliant orchestrator
- Initial anticipation calculation on setup to populate sensors
- Debugpy made optional (non-blocking if not installed)
- Prediction service now imports domain constants instead of infra `const`

### Fixed
- Event bridge now recalculates and publishes results so sensors update on entity changes
- After scheduler `run_action`, force HVAC to `heat` with target temperature to avoid unintended `off`

### Removed
- Legacy `calculator.py`

[0.2.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.1.0...v0.2.0
