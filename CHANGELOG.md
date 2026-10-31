# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

> **After upgrading, call the `reset_learning` service once per device.** Data learned by earlier versions is skewed and would keep distorting preheating. Learning restarts right away from the Home Assistant recorder history.

### Fixed
- **Anticipation now falls back when a scheduler is blocked** (#64) – When several scheduler entities are configured (e.g. a vacation and a non-vacation calendar) and the earliest one's own conditions are not met, IHP now retries with the next applicable scheduler within the same cycle, instead of leaving the room cold until the blocked slot's time has elapsed. When every configured scheduler is blocked, this is now visible on the anticipation sensor's attributes, not only in the logs.
- **Learning history is no longer lost when the recorder is slow or Home Assistant restarts** (#187) – Days whose history could not be read (recorder timeout at startup, restart during an extraction) were skipped for good. They are now read again by the next daily refresh, so their heating cycles still feed the learned slope and dead time.
- **More accurate preheating** (#179, #183, #184, #185, #223) – Heating cycles are dated and measured correctly, each scheduled slot uses the slope learned for its own hour, and cycles that barely heated (safety mode, load shedding) are ignored. Preheating no longer starts hours too early or too late.
- **Learning changes apply without a restart** (#181) – `reset_learning` relearns from history immediately, and sensors show new values as soon as they are learned.
- **No more comfort/eco flapping before a slot** (#182) – A started preheat is kept until its slot, unless the slot is removed or moved.
- **Schedulers** (#188, #189) – Native `schedule.*` entities now get an anticipated start based on the VTherm comfort preset (IHP does not start the heating for them: use HACS Scheduler or an automation on the sensor), and one misconfigured HACS scheduler no longer blocks preheating for the others.
- **Sensors stay up to date** (#191, #226) – Attributes and prediction confidence refresh correctly, the contextual slope sensor shows *unknown* for hours not learned yet, and the device is no longer renamed.
- **Settings and services** (#186) – Changing the retention period no longer resets the device configuration, and services called during startup return a clear error.
- **Setup and options forms fully labelled** (#193) – Several settings showed a raw key (e.g. `auto_learning`) instead of a label, and submitting without a thermostat showed `required` instead of a message. Every setting now has a label and a help text in English and French, the services are translated, and the safety shutoff grace period shows its unit.
- **The Initial Dead Time setting is respected** (#224) – It was saved as if it had been learned from heating cycles: a later change of the setting could be ignored, and `reset_learning` did not keep the learned dead time cleared. Only a dead time measured on heating cycles is now saved, and restarts no longer log a dead time update for every device.
- **Dead time and heating slope measured where heating really starts** (#245) – A rise of exactly 0.2 °C was often missed, so each learned dead time was one sensor reading too long. The heating slope also counted the temperature gained during the dead time, overestimating it (for example 1.2 °C/h for a room heating at 1 °C/h). The slope now only counts the heating after the dead time, and a heating cycle ignored for the slope no longer feeds the dead time. With **Cycle Split Duration** enabled, sub-cycles now get the slope of the heating phase. Preheating can start a few minutes earlier than before.

### Added
- **Outdoor temperature** (#180, #190) – A sensor or a `weather.*` entity can be configured and is recorded with each heating cycle, for a future weather-aware adjustment. The fixed outdoor correction, which counted the cold twice, is removed.

### Maintenance
- CI and release tooling hardening (#194, #199).
- Type checking (#203) – Removed redundant `cast` calls, annotated the HA storage `Store`, and typed the optional `dt_util` import, so fewer mypy warnings are reported on every PR.

## [0.6.4] - 2026-10-24

### Added
- **Integration icon in Home Assistant 2026.3+** – Brand images are now shipped in the integration's `brand/` folder, where Home Assistant 2026.3 and later loads the icon of custom integrations (contributed by frenck).

### Changed
- **Development dependency updates** – Consolidated the pending Dependabot updates: pytest-bdd 8.1, pre-commit 4.7, ruff 0.17, bandit 1.9.4, pip 26.2, setuptools 84.2 and `actions/setup-python` v7. mypy stays on 1.x because mypy 2 forces a Home Assistant downgrade.
- **Security dependency updates** – `idna` 3.20 and `urllib3` 2.8.0 (development environment only).

### Fixed
- **Next timeslot not anticipated after a preheat** (#156) – The "preheating active" flag was only cleared when compared against the *next* timeslot, so a completed preheat could block anticipation of the following slot. A preheat is now marked complete as soon as its own target time has passed, without sending any command to the scheduler.
- **Anticipation timer surviving unload/reload** (#156) – Changing options or unloading the integration left the pending anticipation timer registered in Home Assistant, which could trigger the scheduler for a removed instance. The timer is now cancelled during cleanup (the thermostat setpoint is left untouched).
- **Indoor temperature used as outdoor temperature** (#158) – Without an outdoor temperature sensor (which cannot be configured yet), IHP substituted the indoor temperature and applied the outdoor correction `1 + (20 - indoor) × 0.05`, lengthening every anticipation by about 10–20%. The outdoor correction is now skipped when no outdoor temperature is available. Side effect: the confidence level no longer gets the +0.05 bonus for an outdoor sensor that does not exist.
- **Broken test environment** – Restored the `pycares<5` pin. pycares 5 is incompatible with the `aiodns` version required by Home Assistant and prevented the test suite from starting.
- **PR checks ignoring test failures** – The Code Quality workflow no longer swallows pytest failures (the job now fails and the PR comment reports the failing tests), and the Feature/Fix PR test comment reports the real test outcome instead of always claiming success. Dependabot PRs now skip the branch-naming and CHANGELOG checks, as well as the PR comments their read-only token cannot post, while still running the tests.
- **PR checks failing on fork PRs** – Pull requests opened from forks get a read-only token, so the PR comment steps failed with `Resource not accessible by integration` and turned the Code Quality and Feature/Fix PR checks red even when tests passed. Comment steps are now skipped for fork PRs; the checks report the real lint/test outcome.
- **Release workflows corrupting the CHANGELOG** – The `[Unreleased]` header pattern was not anchored to the start of the line, so the release promotion stamped the version inside a 0.6.3 entry that quoted the header, and release-note extraction could pick up text from older sections. All workflows and helper scripts now only match the header on its own line. The damaged 0.6.3 entry is repaired.
- **Lint cleanup** – Applied ruff 0.17 fixes across the codebase (`datetime.UTC`, `TimeoutError`, `collections.abc` imports, explicit `zip(strict=True)`). No behavior change.

## [0.6.3] - 2026-04-04

### Changed
- **Migration from agent workflow to speckit workflow** – Agents now follow the speckit workflow for feature development, replacing the legacy role-based agent workflow
- **CI/CD Workflow fixes** – Fixed code quality workflow to properly handle exit codes from linting and test tools
  - Use `set +e`/`set -e` to safely capture exit codes from mypy, pylint and pytest
  - Fixed pylint exit code capture and coverage percentage extraction in `code-quality.yml`
- **CI/CD Enforcement Gaps** – Converted previously warn-only workflow checks into hard-failing guards to prevent accidental incomplete releases.
  - Feature/fix PRs now fail immediately when the `[Unreleased]` section of CHANGELOG.md has not been updated (two-pass diff against `origin/integration`)
  - Integration → main PRs are blocked when the source branch is not `integration` or when no validated RC pre-release (`vX.Y.Z-rcN`) exists for the current version
  - The release promotion workflow now fails fast when no matching RC pre-release is found before attempting to create a final release

### Fixed
- **Reset Learning Service** – Fixed the `intelligent_heating_pilot.reset_learning` service which was crashing with a `TypeError` when triggered from Developer Tools or automations. The service now also accepts an `entity_id` parameter so users with multiple IHP devices can choose which device's learning data to reset, consistent with the `calculate_anticipated_start_time` service.
- **Integration PR CHANGELOG check** – Fixed the `awk` range pattern in `integration-pr.yml` that caused the `[Unreleased]` section extraction to terminate immediately because the `[Unreleased]` header matched both the start and end selectors. Now uses a flag-based approach with `^## \[[0-9]` as the end guard.
- **Integration PR RC detection** – Fixed the RC pre-release check to find any RC newer than the current main release, rather than filtering by the version in `manifest.json`. This correctly handles the case where the RC is tagged with the *next* version (e.g. `v0.6.3-rc2`) while `manifest.json` on `integration` still reports the *current* version (`0.6.2`). Updated `scripts/test-rc-check.sh` with five scenarios covering the new version-agnostic logic.

## [0.6.2] - 2026-03-25

### Added
- **Native Home Assistant Schedule Support** ([#122](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/122)) – IHP can now use native `schedule.*` entities (from the Home Assistant Scheduler integration) directly as schedulers, in addition to the existing `switch.*` scheduler entities.
  - `schedule.*` entities are automatically discovered and listed in the scheduler selector
  - Native schedule entities are always treated as enabled (no on/off state check needed)
  - Target temperature is read from the active VTherm climate entity when using a native schedule
  - Next event time is derived from `next_trigger` / `next_event` attributes of the schedule entity
- **Configurable Preheating Revert Time Delta** – Added a new integration option to control when active preheating can be canceled and rescheduled during anticipation recalculation.
  - New option: `anticipation_recalc_tolerance_minutes` (default: 15, range: 1–60)
  - Exposed in both initial setup and options flow
  - Prevents spurious preheating cancellations caused by minor recalculation jitter

### Changed
- **CI/CD Workflow overhaul** – Eliminated duplicate quality checks, standardized Poetry install, and corrected branch naming convention
  - Quality checks no longer run twice when a PR is open on a feature branch
  - Branch naming validation now enforces the documented `feature/issue-XXX` slash format
  - All workflows now use `snok/install-poetry@v1` with dependency caching for faster runs
  - RC pre-release detection uses the GitHub Releases API instead of git tags (ground truth)
  - Fixed `-beta` vs `-rcN` inconsistency: integration PR check and release promotion now correctly target RC releases
  - RC release notes are generated on-the-fly — no `GITHUB_RELEASE_*.md` files committed to the repository
  - New workflow: GitHub pre-release (dev or RC) is automatically created and updated on every merge to `integration`, keeping it in sync with the CHANGELOG `[Unreleased]` section
- **Agent workflow documentation** – All agent files and workflow docs now explicitly require feature branches to be created from `integration`, not `main`

### Fixed
- **Dead Time Startup Hydration** ([#124](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/124)) – Fixed an issue where IHP would fall back to the configured default dead time (0 s) right after a Home Assistant restart, before any heating cycles had been extracted from the Recorder.
  - When `auto_learning` is enabled and no cycles are available yet, the use case now falls back to the last persisted learned dead time from storage
  - Dead time learned from actual cycles always takes precedence; configured default is only used when both cycle data and stored value are unavailable
- **Prevent Anticipation Revert Loop** ([#121](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/121)) – Fixed a loop where IHP would repeatedly cancel and reschedule preheating when the predicted LHS (Learning Heating Slope) was unchanged between recalculations.
  - Preheating is now only reverted when the anticipated start time has actually shifted by more than the configured tolerance
- **Config Flow Scheduler Discovery** – Fixed a runtime crash in the scheduler entity selector caused by passing a list of domains to `async_all()`, which only accepts a single domain string or no argument.
  - Both the initial setup flow and options flow now call `async_all()` without arguments and filter by domain in Python

## [0.6.1] - 2026-03-16

### Fixed
- **Dead Time Thresholds for Floor Heating** – Corrected two default parameters in `_calculate_dead_time_cycle()` that caused all dead time measurements to be silently discarded on floor heating systems:
  - `temp_change_threshold`: `0.1°C` → `0.2°C` to avoid false positives from sensor noise
  - `max_dead_time_minutes`: `60 min` → `180 min` to correctly capture cold-start delays inherent to floor heating (realistic range: 60–120 min)
  - Systems affected were falling back to the configured default dead time on every cycle instead of learning from historical data

## [0.6.0] - 2026-03-13

### Added
- **Dead Time Learning** ([#62](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/62)) – Enhanced prediction accuracy with automatic dead time calculation
  - Formula now includes dead time constant: `time_needed = dead_time + (temperature_delta / learned_slope) * 60`
  - Dead time is automatically learned from historical heating cycles
  - New sensor `sensor.intelligent_heating_pilot_<device>_dead_time` shows the learned dead time in seconds
- **Zero-Retention Mode for Learning History** – New configuration option to disable LHS (Learning Heating Slope) data retention
  - Set `lhs_retention_days=0` to disable historical data storage (useful for testing or minimal deployments)
  - When disabled, system uses default LHS value (2.0°C/h) without attempting to persist or retrieve learning data
  - No storage overhead when retention is disabled
- **Integration Logo** ([#68](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/68)) – Added official logo icons (`icon.png` / `icon@2x.png`) for the Home Assistant integrations page

### Changed
- **Contextual LHS Lazy Loading at Startup** ([#103](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/103)) – Refactored `LhsLifecycleManager` to use lazy loading for contextual LHS, reducing startup I/O and memory overhead
  - At startup, only the current hour's contextual LHS is loaded (instead of all 24 hours)
  - Other hours are loaded on-demand via `get_contextual_lhs()` or `ensure_contextual_lhs_populated()` when first requested
  - Replaced `calculate_all_contextual_lhs()` with `calculate_contextual_lhs_for_hour()` for per-hour on-demand computation
  - Bulk updates (`on_retention_change()`, `on_24h_timer()`) still recalculate and cache all 24 hours as before
- **Coordinator Architecture Refactoring** – Improved code organization and DDD compliance
  - Extracted `IntelligentHeatingPilotCoordinator` from `__init__.py` into dedicated `coordinator.py` module for better maintainability
  - Consolidated `_as_bool()` utility function into `utils/config_helpers.py` to eliminate code duplication
  - Added explicit type annotations for better IDE support and type safety
  - Improved separation of concerns between domain, infrastructure, and application layers
- **Timer-Based Anticipation Triggering** ([#84](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/84), [#70](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/70)) – Improved the reliability of the preheating system by replacing event-driven triggering with timer-based triggering, ensuring IHP always wakes up at the anticipated time even when no sensor events occur in the window between calculation and target time.

### Fixed
- **Home Assistant Recorder Saturation** – Fixed HA restarts triggered by the supervisor when multiple IHP devices were configured with high retention periods (e.g. 30 days)
  - Extraction tasks now cover configurable periods (default: 7 days) instead of a single day, reducing the number of Recorder queries by up to 7×
  - Added a 10-second pause between extraction tasks to let the Recorder breathe and prevent query queue overflow
  - Eliminated redundant SQL queries caused by fetching each historical data key separately: all keys are now retrieved in a single `get_significant_states` call per entity per period
- **Fixed Configuration Values Being Ignored When Falsy** ([#91](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/91), [#85](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/85)) – Configuration values like `0` (false/disabled) are now properly read and applied
  - `lhs_retention_days=0`, `cycle_split_duration_minutes=0`, `auto_learning=False` now correctly persist and are respected by the system
  - Parameters `cycle_split_duration_minutes`, `min_cycle_duration_minutes`, `max_cycle_duration_minutes` are now properly read from config options instead of always using defaults
  - `ihp_enabled=False` is now correctly persisted across Home Assistant restarts — the IHP Enable/Disable Switch state is reliably restored after a restart
  - Centralized boolean parsing ensures consistent handling of stringified config values across the integration
- **No-scheduler KeyError spam** ([#81](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/81))
  - Fixed `KeyError: 'anticipated_start_time'` when IHP runs without a scheduler configured
  - Event bridge now distinguishes between clear-values signals and full data payloads
  - Users without scheduler configuration no longer see repeated errors; sensors stay `unknown` as expected
- **IHP Enable/Disable Switch State Ignored in Event-Driven Updates** ([#90](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/90)) – Fixed a race condition in `HAEventBridge` where event-driven recalculations (triggered by entity state changes) did not pass the `ihp_enabled` parameter, causing it to default to `True`
  - When IHP was disabled via the switch, preheating was still triggered by sensor events
  - `HAEventBridge` now always passes the current enabled state from the coordinator when recalculating
- **Startup Performance Improvements** – Optimizations to prevent HA watchdog timeout and reduce startup memory consumption
  - Async incremental recorder loading prevents blocking HA startup
  - FIFO RecorderAccessQueue serializes recorder access across multiple IHP instances to prevent OOM at startup
  - Smart event filtering eliminates log flood and unnecessary HA state writes
  - Contextual LHS lazy loading (see "Changed" section) further reduces I/O overhead

## [0.5.0] - 2026-01-25

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


## [0.4.4] - 2026-01-14

### Fixed
- **Config Flow Consistency** - Fixed inconsistent behavior between add and modify device forms
  - Add device form now uses entity selectors with search functionality (same as modify form)
  - Entity search/autocomplete works in both add and modify forms
  - Optional entities (humidity sensors, cloud cover) are properly saved during device creation
  - Optional entities can now be cleared and stay cleared (no longer reappear after removal)
  - Consistent user experience between adding and modifying IHP devices
- **Integration Failed to Start** ([#67](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/67))
  - Fixed `TypeError: '>' not supported between instances of 'NoneType' and 'int'` when `cycle_split_duration_minutes` is not configured
  - Integration now properly handles cases where cycle split duration is not set
  - Ensures compatibility with Home Assistant 2026.1.0 beta
- **Optional Fields Persistence in Options Flow** ([#54](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/54), [#65](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/65))
  - Fixed inability to clear optional entity fields (indoor humidity, outdoor humidity, cloud cover) in configuration UI
  - Optional fields now use `suggested_value` pattern to allow proper clearing
  - Implemented explicit `None` value for deleted optional fields to override data from initial creation
  - Added validation for required fields (VTherm and Schedulers) with clear error messages
  - Improved options merging to handle cleared values correctly

### Changed
- **Logging Improvements** ([#59](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/59))
  - Method entry/exit logging moved to DEBUG level for cleaner INFO logs
  - INFO level now reserved for state changes and important events
  - Device logs now include friendly names instead of entity IDs for better readability
  - Improved log structure for easier troubleshooting

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

[Unreleased]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.6.3...HEAD
[0.6.3]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.6.3
[0.6.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.4...v0.5.0
[0.4.3]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.1.0
