# Installation Guide - Intelligent Heating Pilot

## Prerequisites

Before installing IHP, ensure you have:

- **Home Assistant** 2024.11 or higher
- **Versatile Thermostat (VTherm)** integration installed and configured: IHP only works with Versatile Thermostat entities
- **[HACS Scheduler](https://github.com/nielsfaber/scheduler-component)** installed, if you want IHP to start the heating. Native `schedule.*` helpers only get an anticipated start sensor (see [Supported Schedulers](CONFIGURATION.md#supported-schedulers))

## Installation Methods

### Option 1: Via HACS (Recommended)

HACS (Home Assistant Community Store) is the easiest way to install and manage updates.

**Steps:**

1. Open **HACS** in your Home Assistant sidebar (if not visible, install HACS first)
2. Click **Integrations** tab
3. Click the **⋮ (three dots)** menu in the top-right corner
4. Select **Custom repositories**
5. Paste this URL: `https://github.com/RastaChaum/Intelligent-Heating-Pilot`
6. Choose **Integration** as the category
7. Click **Create**
8. Search for **"Intelligent Heating Pilot"** (or "IHP")
9. Click **Download**
10. **Restart Home Assistant** (Settings → System → Restart)

### Option 2: Manual Installation

For advanced users or if HACS is not available:

**Steps:**

1. Download the latest release from [GitHub Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)
2. Extract the `intelligent_heating_pilot` folder
3. Copy it to: `<your-config-folder>/custom_components/`
4. **Restart Home Assistant**

Your folder structure should look like:
```
config/
├── custom_components/
│   ├── intelligent_heating_pilot/  ← Extracted folder here
│   │   ├── __init__.py
│   │   ├── config_flow.py
│   │   └── ...
│   └── ...
├── automations.yaml
└── ...
```

## Next Steps

After installation:

1. ✅ **Verify installation** - Check that Home Assistant restarted without errors (see logs)
2. 📋 **Configure IHP** - Follow the [Configuration Guide](CONFIGURATION.md)
3. 📖 **Learn how it works** - Read [How IHP Works](HOW_IT_WORKS.md)

## Updating IHP

Update through HACS (or replace the folder for a manual install), then restart Home Assistant. Read the [CHANGELOG](../../CHANGELOG.md) for steps a version may require.

> **Upgrading to 0.7.x:** call the `intelligent_heating_pilot.reset_learning` service once per device (Developer Tools → Actions), with any sensor of the device as `entity_id`. Data learned by earlier versions is skewed; learning restarts right away from the Home Assistant recorder history.

## Troubleshooting Installation

### IHP doesn't appear in integrations

**Solution:**
- Ensure Home Assistant fully restarted (check System → Restart)
- Clear browser cache (Ctrl+Shift+Delete)
- Check the Home Assistant logs for errors:
  ```yaml
  logger:
    default: info
    logs:
      homeassistant.core: debug
  ```

### "Integration not found" after restart

**Solution:**
- Verify the folder structure (see "Manual Installation" above)
- Check file permissions (folder should be readable by Home Assistant)
- Restart Home Assistant again

### Need help?

- 💬 [GitHub Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
- 🐛 [Report a Bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)

---

**Next:** Go to [Configuration Guide](CONFIGURATION.md)
