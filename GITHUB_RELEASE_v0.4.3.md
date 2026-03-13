# Release v0.4.3 - Configurable Heating Cycle Detection

## 🎉 What's New in v0.4.3

This release gives you **full control** over how IHP detects heating cycles and calculates the Learning Heating Slope (LHS). You can now tune detection parameters directly from the integration UI to match your specific heating system—no more one-size-fits-all!

Perfect for users with intermittent heating, micro-cutoffs, or unique system characteristics.

---

## ✨ New Features

### Configurable Heating Cycle Detection Parameters

IHP now exposes 4 new configuration parameters in the UI to fine-tune cycle detection:

#### 1️⃣ **Temperature Detection Threshold** (default: 0.2°C)
- **What it does**: Sets the temperature difference required to detect cycle start/end
- **When to adjust**:
  - 🔻 **Lower (0.1°C)**: For heating systems with subtle temperature changes
  - 🔺 **Higher (0.3-0.5°C)**: For systems with frequent micro-cutoffs or intermittent heating
- **Impact**: More sensitive detection captures short cycles; less sensitive avoids noise

#### 2️⃣ **Minimum Cycle Duration** (default: 5 minutes)
- **What it does**: Filters out heating cycles shorter than this duration
- **When to adjust**:
  - 🔻 **Lower (1-3 min)**: For fast-response systems (electric radiators, heat pumps)
  - 🔺 **Higher (10-15 min)**: For systems with frequent switching noise
- **Impact**: Prevents micro-cycles from polluting learning data

#### 3️⃣ **Maximum Cycle Duration** (default: 300 min / 5h)
- **What it does**: Filters out abnormally long heating cycles
- **When to adjust**:
  - 🔻 **Lower (120-180 min)**: For well-insulated homes or powerful heating
  - 🔺 **Higher (360-720 min)**: For poorly insulated spaces or weak heating systems
- **Impact**: Excludes sensor malfunctions and abnormal system behavior

#### 4️⃣ **Cycle Split Duration** (default: None/disabled)
- **What it does**: Splits long heating cycles into sub-cycles for ML training augmentation
- **When to enable**: Planning to use ML mode (future feature) or have very long cycles (>2 hours)
- **Recommended**: 30-60 minutes when enabled
- **Impact**: Increases training data samples for better ML predictions

### Full UI Integration

- ✅ Configurable during initial setup
- ✅ Modifiable via Options Flow after installation
- ✅ Complete English and French translations
- ✅ Helpful tooltips and descriptions in UI
- ✅ Backward compatible with sensible defaults

---

## 🔧 Improvements

### HeatingCycleService Parameterization
- **Before**: HeatingCycleService used hardcoded detection parameters (0.2°C threshold, 5 min, 300 min)
- **After**: Accepts configuration from coordinator, enabling per-installation customization
- **Benefit**: Adapts to different heating system characteristics automatically

### REST API Configuration Awareness
- REST API for manual cycle extraction now uses configured parameters from the coordinator
- No more hardcoded defaults in API calls
- Consistent behavior between automated and manual extraction

---

## 📝 Documentation

### Updated Guides

- **CONFIGURATION.md**: New "Heating Cycle Detection Parameters" section with:
  - Detailed parameter descriptions
  - When and how to adjust each setting
  - Warning indicators for edge cases
  - Step-by-step modification instructions

- **USER_GUIDE.md**: Updated with guidance on:
  - Understanding cycle detection
  - Troubleshooting detection issues
  - Tuning for specific heating systems

### Consistency Improvements
- Verified all version references are up-to-date (0.4.3)
- Improved cross-referencing between documentation
- Clearer navigation for configuration options

---

## 🐛 Bug Fixes

### Adaptable Cycle Detection
- **Fixed**: Heating cycle detection now adapts to different heating system characteristics
- **Impact**: Users with intermittent heating, micro-cutoffs, or unique systems can now tune detection to work correctly
- **Before**: Some systems had cycles incorrectly detected or missed
- **After**: Configurable thresholds accommodate diverse heating behaviors

### Optional Cycle Split Duration
- **Fixed**: Cycle Split Duration parameter now uses 0 to indicate "disabled"
- **Impact**: Set to 0 (default) to disable cycle splitting, or any value >0 to enable
- **Before**: UI validation error when trying to leave field empty
- **After**: 0 = disabled, values 15-120 = enabled with split duration in minutes

---

## 🎯 Use Cases

This release is perfect for:

### ❄️ Intermittent Heating Systems
**Problem**: Heating turns on/off frequently, creating many short "cycles"
**Solution**: Increase `temp_delta_threshold` to 0.3-0.5°C and `min_cycle_duration` to 10-15 min

### ⚡ Fast-Response Systems (Heat Pumps, Electric Radiators)
**Problem**: Very short but legitimate heating cycles are ignored
**Solution**: Lower `min_cycle_duration` to 1-3 minutes

### 🏠 Poorly Insulated Spaces
**Problem**: Very long heating cycles (>5 hours) are excluded
**Solution**: Increase `max_cycle_duration` to 360-720 minutes

### 🤖 ML Training Preparation
**Problem**: Need more granular data for future ML features
**Solution**: Enable `cycle_split_duration` at 30-60 minutes

---

## 📦 Technical Details

### Architecture
- Domain layer: `HeatingCycleService` parameterized constructor
- Infrastructure layer: Coordinator reads config and injects parameters
- Application layer: `HeatingApplicationService` passes parameters to service
- REST API: Reads parameters from coordinator instead of hardcoded values

### Backward Compatibility
- All parameters optional with sensible defaults
- Existing installations continue working unchanged
- New parameters only applied after reconfiguration

---

## 🔗 Full Changelog

See [CHANGELOG.md](CHANGELOG.md#043---2025-12-23) for complete details.

---

## 📥 Installation

### Via HACS (Recommended)
1. Open HACS → Integrations
2. Search for "Intelligent Heating Pilot"
3. Click **Update** to v0.4.3

### Manual Installation
1. Download `intelligent_heating_pilot.zip` from this release
2. Extract to `custom_components/intelligent_heating_pilot/`
3. Restart Home Assistant

---

## 🙏 Thank You

This release focuses on **user empowerment** — giving you the tools to tune IHP for your specific heating system. We hope these configuration options make IHP work better for everyone!

As always, feedback and issue reports are welcome in the [Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues) section.

Happy heating! 🔥
