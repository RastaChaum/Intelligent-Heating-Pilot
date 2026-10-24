---
name: Documentation Audit Fixes - v0.6.0
description: Critical documentation errors found in code audit and fixed
type: project
---

## Documentation Fixes Applied (March 2026)

### Bug 1: HOW_IT_WORKS.md - Prediction Formula (CRITICAL)
**Status**: Fixed ✓

- Changed formula from seconds to minutes: `Anticipation Time (minutes) = Dead Time + (Temperature Difference / Learned Slope) × 60`
- Updated example to use 1.5 minutes dead time instead of 90 seconds
- Added correct environmental correction formulas with actual code values:
  - Outdoor: `1.0 + (20 - outdoor_temp) × 0.05` (at 0°C: factor = 2.0)
  - Humidity: `1.0 + (humidity - 50) × 0.002` (at 80%: factor = 1.06)
  - Solar: `1.0 - (100 - cloud_coverage) × 0.001` (at 0% cloud: factor = 0.9)
- Corrected safety bounds: minimum 10 minutes (was 5), maximum 360 minutes (was 240)

### Bug 2: HOW_IT_WORKS.md - Safety Shutoff Grace Period
**Status**: Fixed ✓

- Added grace period explanation: 10-minute window for brief safety/frost interruptions
- Explained why it exists: prevents 100,000+ °C/h slopes from micro-cycles
- Updated cycle detection table with grace period scenarios
- Added grace period is configurable (0-30 min, default 10 min)

### Bug 3: HOW_IT_WORKS.md - LHS Section Improvements
**Status**: Fixed ✓

Added comprehensive LHS documentation:
- **Two types of LHS**: Global (average of all cycles) vs Contextual (per-hour-of-day)
- IHP uses contextual when available, falls back to global
- **Filters applied before LHS**:
  - Non-positive slope filter: discards cycles where temp didn't rise
  - Minimum effective duration filter: rejects cycles < 5 min effective (after dead time)
- **Dead time affects slope calculation**: effective_duration = total_duration - dead_time
- Explained why filters are critical: prevents extreme slopes from short cycles

### Bug 4: HOW_IT_WORKS.md - Cycle Cache Section
**Status**: Fixed ✓

Updated cache description from outdated single-extraction to modern progressive batching:
- Extraction split into `task_range_days` batches (default 7 days)
- RecorderAccessQueue serialization prevents multi-instance conflicts
- Lazy loading: current hour loaded at startup, others on-demand
- Startup staggering with deterministic jitter
- Processing time: 1-2 minutes per week of history
- Removed obsolete "check recorder's purge_keep_days" advice

### Bug 5: CONFIGURATION.md - Removed Quick Start Duplication
**Status**: Fixed ✓

- Changed header from "Quick Setup (5 minutes)" to "Device Setup"
- Kept actual setup steps, removed redundant "Quick Start" framing
- Prevents conflict with USER_GUIDE.md's "Quick Start (15 minutes)"

### Bug 6: CONFIGURATION.md - Added 4 Missing Configuration Options
**Status**: Fixed ✓

Added to Advanced Configuration section:

1. **Initial Dead Time** (0-60 min, default 0)
   - Seed value for learning phase
   - Helps if system has known startup lag

2. **Automatic Learning** (enabled by default)
   - Toggle for freezing parameters during testing

3. **Recorder Extraction Period** (1-30 days, default 7)
   - Controls batch size for initial extraction
   - Affects DB load per batch vs. total time

4. **Safety Shutoff Grace Period** (0-30 min, default 10)
   - Configurable grace window for brief interruptions
   - Guidance for low-power vs. high-latency systems

### Bug 7: CONFIGURATION.md - Updated Data Retention Section
**Status**: Fixed ✓

- Replaced "up to 5 minutes" with accurate 1-2 min/week estimate
- Described progressive batched extraction instead of single heavy operation
- Added RecorderAccessQueue serialization details
- Removed outdated recorder purge_keep_days tuning advice
- Added Recorder Extraction Period as key tuning lever

### Bug 8: CONFIGURATION.md - Fixed Configuration Checklist
**Status**: Fixed ✓

- Changed "At least one scheduler entity selected" to "(optional — required for automatic preheating)"
- Accurate now since scheduler is optional since v0.5.0

### Bug 9: USER_GUIDE.md - Fixed Version Footer
**Status**: Fixed ✓

- Changed from "v0.4.3 - December 2025"
- To: "v0.6.0 - March 2026"

## Files Modified
1. `/docs/HOW_IT_WORKS.md` — Critical algorithm and learning mechanism updates
2. `/docs/CONFIGURATION.md` — Added 4 missing options, fixed duplication, updated descriptions
3. `/docs/USER_GUIDE.md` — Version footer update

## Code References Verified
- `prediction_service.py` lines 80-127: formula in minutes (dead_time_minutes + (temp_delta / learned_slope) * 60.0)
- `constants.py`: MIN_ANTICIPATION_TIME = 10, MAX_ANTICIPATION_TIME = 360
- Environmental factors: OUTDOOR_TEMP_FACTOR = 0.05, HUMIDITY_FACTOR = 0.002, CLOUD_COVERAGE_FACTOR = 0.001
- `heating_cycle_service.py` lines 52-72, 135-226: grace period (safety_shutoff_grace_minutes default 10)
- `contextual_lhs_calculator_service.py`: per-hour grouping and averaging
- `global_lhs_calculator_service.py`: simple average of all positive-slope cycles
- `value_objects/heating.py` lines 72-120: min_effective_duration_minutes filter, dead_time_cycle_minutes impact

## Key Terminology (for future documentation)
- **Contextual LHS**: Per-hour-of-day learned heating slope
- **Global LHS**: Overall average learned heating slope
- **Effective duration**: Total cycle duration minus dead time
- **Safety shutoff grace period**: 10-minute grace for brief interruptions (configurable)
- **RecorderAccessQueue**: Global serializer for multi-instance recorder access
