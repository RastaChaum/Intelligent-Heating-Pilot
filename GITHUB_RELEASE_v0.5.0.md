# Release v0.5.0 - Release Candidate

## 🧪 Release Candidate
Cette version est une **release candidate** destinée aux tests en production et aux beta-testeurs.

### Added
- **IHP Enable/Disable Switch** ([#77](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/77)) – New domain entity to toggle IHP preheating on/off per device while preserving learned data
  - Switch entity `switch.intelligent_heating_pilot_<device>_enable_preheating` for each configured IHP device
  - Full domain layer support with DDD-compliant abstraction
  - Comprehensive unit tests for switch functionality
  - Documented in user guides
- **Optional Scheduler Support** ([#75](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/75)) – Schedulers now optional; new service for dynamic calculations without scheduler binding
  - New service `calculate_anticipated_start_time` for on-demand calculations with custom parameters
  - Service accepts input parameters: `target_temperature`, `current_temperature`, `outdoor_temperature` (optional)
  - Service returns `anticipated_start_time` and `heating_slope_used` for transparency
  - Enables integration with other heating automation systems beyond Scheduler
- **RC workflow suite** – New GitHub Actions for release candidates (prepare, increment, promote) plus CLI helper `scripts/rc-helper.sh` and documentation to manage RC cycles safely in production.

### Changed
- **Release automation cleanup** – Legacy pre-release/release workflows removed in favor of the RC-based pipeline to avoid duplicate runs and align production releases with validated RCs.
- **Documentation maintenance** – Updated README badges and version, aligned docs index, and referenced open issues [#20](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/20) and [#66](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/66) for tracking.

### Fixed
---

## ⚠️ Important
Cette version est en phase de test. Veuillez remonter tout problème via les Issues GitHub.
