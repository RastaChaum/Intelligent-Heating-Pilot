# Release v0.4.4-rc.1 - Configuration & Logging Improvements

## 🐛 Bug Fixes & Improvements

This pre-release fixes critical configuration issues and improves logging for better debugging.

---

## What's Fixed

### 1. ❌ Config Flow: Inconsistent Behavior Between Add and Modify (#Issue TBD)

**Problem:** The "Add Device" and "Modify Device" forms had different user experiences:
- Add form used plain text fields (no entity search/autocomplete)
- Modify form used entity selectors with search functionality
- Optional entities weren't saved during device creation
- Optional entities couldn't be removed once added

**What we fixed:** 
- Add and Modify forms now use identical entity selectors
- Entity search/autocomplete works in both forms
- Optional entities (humidity sensors, cloud cover) are properly saved
- Optional entities can be cleared and stay cleared

**Impact:** 
- ✅ Consistent user experience between Add and Modify
- ✅ Entity search works everywhere
- ✅ Optional entities properly saved and removable
- ✅ Better validation with clear error messages

---

### 2. 📊 Logging Improvements (#59)

**Problem:** Logs were cluttered with too many INFO messages, making it hard to track actual device actions.

**What we improved:**
- Method entry/exit now logged at DEBUG level
- INFO level reserved for actual state changes and important events
- Device logs now include friendly names instead of entity IDs
- Better structured logging for troubleshooting

**Impact:**
- ✅ Cleaner INFO logs showing only important events
- ✅ More readable device identification in logs
- ✅ Easier debugging with DEBUG level details
- ✅ Better log organization

---

### 3. ❌ Integration Failed to Start (Previous fix)

**Problem:** IHP integration failed to load with a `TypeError` on startup for some users.

**Error message:**
```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```

**What we fixed:** The integration now properly handles cases where cycle split duration is not configured.

**Impact:** 
- ✅ Integration loads correctly on startup
- ✅ Works with default configuration without errors

---

## 📦 How to Test This Pre-Release

### Via Git (For Testing)

```bash
cd /config/custom_components/intelligent_heating_pilot
git fetch
git checkout v0.4.4-rc.1
# Restart Home Assistant
```

### Manual Installation

```bash
cd /config/custom_components/
wget https://github.com/RastaChaum/Intelligent-Heating-Pilot/archive/refs/tags/v0.4.4-rc.1.zip
unzip v0.4.4-rc.1.zip -d intelligent_heating_pilot
rm v0.4.4-rc.1.zip
# Restart Home Assistant
```

---

## ⬆️ Upgrading from v0.4.3

**Recommended testing:**
1. Test creating a new IHP device with optional entities
2. Test modifying existing device configuration
3. Test removing optional entities
4. Check that logs are cleaner and more readable

---

## 🔗 Links

- **Pull Requests:** 
  - [#65 - Optional fields persistence](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/65)
  - [#59 - Logging improvements](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/59)
- **Full Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **Documentation:** [Configuration Guide](docs/CONFIGURATION.md)

---

## 📊 Compatibility

- **Home Assistant:** >= 2024.1.0 (including 2026.1.0 beta)
- **Python:** >= 3.12
- **Versatile Thermostat:** Required

---

## ⚠️ Pre-Release Notice

This is a **release candidate** for testing. Please report any issues before we publish the stable v0.4.4 release.

---

**Full Version:** v0.4.4-rc.1  
**Release Date:** January 14, 2026  
**Status:** Pre-release (Release Candidate)
