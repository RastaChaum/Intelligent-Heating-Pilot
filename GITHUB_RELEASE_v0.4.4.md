# Release v0.4.4 - Configuration Bug Fixes

## 🐛 Important Bug Fixes

This release fixes two critical issues that prevented IHP from starting or configuring properly.

---

## What's Fixed

### 1. ❌ Integration Failed to Start (#67)

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

### 2. ❌ Optional Entities Couldn't Be Removed (#54)

**Problem:** When you tried to remove optional sensors (indoor humidity, outdoor humidity, cloud cover) using the clear button (×) in the configuration dialog, they would reappear after saving.

**What we fixed:** You can now properly clear optional entity fields. When you click the × button to remove a sensor, it stays removed after saving and reopening the configuration.

**Impact:**
- ✅ Clear button now works correctly
- ✅ Optional sensors stay cleared after saving
- ✅ You have full control over which sensors to use

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
- **Pull Request:** [#65](https://github.com/RastaChaum/Intelligent-Heating-Pilot/pull/65)
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
**Release Date:** January 4, 2026  
**Status:** Stable
