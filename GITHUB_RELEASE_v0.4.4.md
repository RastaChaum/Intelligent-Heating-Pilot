# Release v0.4.4 - Configuration Bug Fixes

## 🐛 Important Bug Fixes

This release fixes critical issues that prevented IHP from starting or configuring properly, and improves the overall user experience.

---

## What's Fixed

### 1. ❌ Config Forms Not Consistent Between Add and Modify (#54)

**Problem:** When adding a new IHP device vs. modifying an existing one, the forms behaved differently:
- Adding a device used basic text fields (you had to type entity IDs manually)
- Modifying a device showed a nice dropdown with search functionality
- Optional sensors you selected when adding a device weren't saved
- Optional sensors couldn't be removed once added

**What we fixed:** Both forms now work the same way with entity search dropdowns. Your optional sensors (humidity, cloud cover) are properly saved and can be cleared when you don't need them anymore.

**Impact:**
- ✅ Search for entities by name when adding or modifying devices
- ✅ Same user-friendly experience everywhere
- ✅ Optional sensors work as expected
- ✅ Full control over your configuration

---

### 2. 📊 Cleaner Logs for Better Troubleshooting

**Problem:** The Home Assistant logs were cluttered with too many messages from IHP, making it hard to see what was actually happening with your heating.

**What we improved:** Logs now show what matters:
- Device names (like "Living Room Thermostat") instead of cryptic entity IDs
- Important events (heating started/stopped, decisions made) clearly visible
- Technical details hidden in DEBUG mode when you need them
- Less noise, more signal

**Impact:**
- ✅ Easier to understand what IHP is doing
- ✅ Faster troubleshooting when something's wrong
- ✅ See your device names in logs, not technical IDs
- ✅ Professional logging experience

---

### 3. ❌ Integration Failed to Start (#67)

**Problem:** IHP integration failed to load with a `TypeError` on startup for some users.

**Error message:**
```
TypeError: '>' not supported between instances of 'NoneType' and 'int'
```

**What we fixed:** The integration now properly handles cases where cycle split duration is not configured. Your IHP will start successfully even if you haven't set all advanced cycle detection parameters.

**Impact:** 
- ✅ Integration loads correctly on startup
- ✅ Works with default configuration without errors
- ✅ Compatible with Home Assistant 2026.1.0 beta

---

## 📦 How to Update

### Via HACS (Recommended)

1. Open HACS → Integrations
2. Find "Intelligent Heating Pilot"
3. Click "Update" to v0.4.4
4. Restart Home Assistant

### Manual Installation

```bash
cd /config/custom_components/
wget https://github.com/RastaChaum/Intelligent-Heating-Pilot/archive/refs/tags/v0.4.4.zip
unzip v0.4.4.zip -d intelligent_heating_pilot
rm v0.4.4.zip
# Restart Home Assistant
```

---

## ⬆️ Upgrading from v0.4.3

**No action required** - this is a drop-in replacement. Your existing configuration will continue to work.

**Optional:** After upgrading, you may want to review your optional sensor configuration and remove any sensors you're not using.

---

## 🔗 Links

- **Issues Fixed:** 
  - [#67 - Integration fails to start](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/67)
  - [#54 - Optional fields cannot be cleared](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/54)
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

## 🙏 Thank You

Thanks to all users who reported these issues and helped with testing!

Special thanks to @Benjamin45590 for the detailed bug report.

---

**Full Version:** v0.4.4  
**Release Date:** January 14, 2026  
**Status:** Stable
