# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive documentation for contributors (CONTRIBUTING.md, ARCHITECTURE.md)
- GitHub issue templates for bug reports and feature requests
- Pull request template with architecture compliance checklist
- Release template and process documentation

### Changed
- Documentation reorganized for clarity: user docs vs contributor docs
- All documentation translated to English for broader accessibility

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

[Unreleased]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.1.0
