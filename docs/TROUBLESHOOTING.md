# Troubleshooting Guide - Intelligent Heating Pilot

## ❓ Quick Problem Finder

**What's your problem?** Find it below and jump to the solution:

| Issue | Go To |
|-------|-------|
| IHP doesn't appear in integrations | [Installation Issues](#installation-issues) |
| Can't complete configuration | [Configuration Issues](#configuration-issues) |
| Predictions are inaccurate | [Prediction Issues](#prediction-issues) |
| Sensors show no data | [Sensor Issues](#sensor-issues) |
| Heating never triggers | [Heating Not Triggering](#heating-not-triggering) |
| Something else? | [General Debugging](#general-debugging) |

---

## 🔧 Installation Issues

### IHP doesn't appear in integrations after restart

**Symptoms:**
- Integration not found in Settings → Devices & Services
- Can't search for "Intelligent Heating Pilot"

**Diagnosis:**

1. Check if folder is in correct location:
   ```
   config/custom_components/intelligent_heating_pilot/
   ├── __init__.py
   ├── config_flow.py
   └── ... other files
   ```

2. Check Home Assistant logs for Python errors:
   ```yaml
   logger:
     default: info
     logs:
       homeassistant.core: debug
       homeassistant.loader: debug
   ```

**Solutions:**

- ✅ **Clear browser cache** (Ctrl+Shift+Delete) and reload
- ✅ **Full restart** (Settings → System → Restart) - not just reload
- ✅ **Check file permissions** - Home Assistant user must read/execute
- ✅ **Verify folder name** - Must be exactly `intelligent_heating_pilot`
- ✅ **Check `manifest.json`** - Should be valid JSON, not corrupted

**If still not working:**
- Share error logs on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)

---

## ⚙️ Configuration Issues

### "VTherm entity not found" error

**Symptoms:**
- Configuration fails with entity lookup error
- Can't save configuration

**Solution:**

1. Find your VTherm entity:
   - Go to **Developer Tools** → **States**
   - Search for `climate.`
   - Find your thermostat entity (e.g., `climate.living_room`)

2. Copy the **exact entity name** (case-sensitive!)

3. Reconfigure IHP:
   - Settings → Devices & Services
   - Find Intelligent Heating Pilot
   - Click ⋮ → Reconfigure
   - Paste the exact entity name

### "No scheduler entities available" error

**Symptoms:**
- Configuration shows empty dropdown for scheduler
- "Please create a schedule first" message

**Solution:**

1. Verify HACS Scheduler is installed:
   - Go to HACS → Integrations
   - Search for "Scheduler"
   - Should be installed

2. Create a test schedule:
   - Go to Services → Scheduler (or through UI)
   - Create at least one schedule
   - Make sure it controls your VTherm

3. Verify scheduler entity exists:
   - Developer Tools → States
   - Search for `switch.` 
   - Should see `switch.schedule_*` entities

4. Reconfigure IHP and select the scheduler

### Configuration saves but integration doesn't load

**Symptoms:**
- Configuration successful
- But integration doesn't appear as active
- Or gives error immediately after setup

**Solution:**

1. Check integration errors:
   - Settings → Devices & Services
   - Find Intelligent Heating Pilot
   - Click on it to see full status

2. Check Home Assistant logs:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```

3. Try reconfiguring with minimal options:
   - Use **required fields only** (Name, VTherm, Scheduler)
   - Skip optional sensors first
   - Add them later if needed

4. If error persists:
   - Delete integration: Settings → Devices & Services → ⋮ → Delete
   - Restart Home Assistant
   - Reconfigure from scratch

---

## 📊 Sensor Issues

### Sensors showing "unknown" or "unavailable"

**Symptoms:**
- Learned Heating Slope: `unknown`
- Anticipation Time: `unavailable`
- Next Schedule: No data

**Possible Causes:**

1. **IHP just installed** - Wait 1-2 minutes for initialization
2. **No heating cycles yet** - Sensors need data to show values
3. **VTherm not heating** - Make sure your thermostat is actually controlling heat

**Solution:**

1. **Wait for first heating cycle:**
   - Manually trigger scheduler (or wait for scheduled time)
   - Watch temperature rise
   - Sensors should populate after heating stops

2. **Verify VTherm is working:**
   - Check VTherm entity in Developer Tools → States
   - Look for `temperature_slope` attribute
   - If empty/zero, VTherm may not be heating

3. **Check IHP is running:**
   - Settings → Devices & Services
   - Click Intelligent Heating Pilot
   - Should show "1 device" with status

### Sensors show data but it looks wrong

**Symptoms:**
- Learned Heating Slope shows 0.0 or 99.9
- Anticipation Time shows extreme values
- Confidence is always 0%

**Solution:**

See [Prediction Issues](#prediction-issues) below - likely a learning problem, not a sensor problem.

---

## 🔥 Heating Not Triggering

### Scheduler turns on but IHP never triggers it

**Symptoms:**
- Scheduler is configured and has upcoming events
- You wait for the scheduled time
- Heating never starts (or starts too late)

**Possible Causes:**

1. **Configuration issue** - IHP not linked to correct scheduler
2. **No learned slope** - IHP hasn't learned your heating yet
3. **Confidence too low** - IHP not confident enough to act
4. **Scheduler entity format wrong** - Entity name mismatch

**Solution:**

1. **Verify configuration:**
   - Settings → Devices & Services → Intelligent Heating Pilot
   - Click ⋮ → Device Details
   - Check "Scheduler entities" list
   - Should show your scheduler entity

2. **Check logs for errors:**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```
   Look for trigger-related messages

3. **Manually trigger heating:**
   - Manually turn ON your scheduler entity
   - Watch logs to see if IHP detects it
   - Temperatures should start rising

4. **Check permissions:**
   - Verify scheduler service can be called
   - Try calling scheduler manually: Developer Tools → Services

### Heating triggers too early

**Symptoms:**
- IHP starts heating 2+ hours before scheduled time
- Room reaches target well before the scheduled event

**Cause:**
- Learned slope is too low (IHP thinks heating is slower than it actually is)

**Solutions:**

- **Wait for learning phase:**
  - During first 5-10 cycles, IHP may overshoot
  - It learns and improves with each cycle
  - Confidence should increase over time

- **Speed up learning:**
  - Let several heating cycles complete
  - Check that VTherm `temperature_slope` is updating
  - Monitor the "Learned Heating Slope" sensor - should stabilize

- **Manual reset if something changed:**
  - If you replaced radiators or changed insulation:
  - Call service: `intelligent_heating_pilot.reset_learning`
  - IHP will start learning from scratch

### Heating triggers too late (room doesn't reach target)

**Symptoms:**
- IHP waits too long to trigger heating
- Room never reaches target temperature
- Always 1-2°C short when scheduled time arrives

**Cause:**
- Learned slope is too high (IHP thinks heating is faster than it actually is)

**Solutions:**

1. **Check heating system:**
   - Are radiators blocked or cold?
   - Is thermostat sensor reading correctly?
   - Try manual heating to verify it works

2. **Check environmental factors:**
   - Is humidity extremely high (>80%)?
   - Is it very cold outside (< -10°C)?
   - These affect heating efficiency

3. **Reset learning:**
   ```yaml
   service: intelligent_heating_pilot.reset_learning
   ```
   Then wait for 5-10 new cycles to rebuild slope

4. **Increase environmental adjustments:**
   - Add humidity/outdoor temp sensors if not already present
   - These help IHP account for real-world factors

---

## 📈 Prediction Issues

### Predictions are wildly inaccurate

**Symptoms:**
- Start time jumps around between cycles
- Sometimes 2 hours early, sometimes 30 minutes late
- No consistency

**Cause:**
- Insufficient learning history (high variability with few samples)

**Solution:**

- **Wait for stabilization:**
  - Let 10+ heating cycles complete
  - IHP needs data to average out variations
  - Consistency should improve significantly

- **Check for inconsistencies:**
  - Are heating cycles similar? (target temp, duration)
  - Or very different each time?
  - If different, IHP will naturally vary more
  - Variations in your schedule cause variations in slope

### Confidence never increases

**Symptoms:**
- Learned Heating Slope sensor stays near 0.0
- Confidence stays below 30%
- No improvement over many cycles

**Cause:**
- Learning data not being captured (cycle detection failing)

**Solution:**

1. **Check VTherm attribute:**
   - Developer Tools → States
   - Find your climate entity
   - Look for `temperature_slope` attribute
   - It should show values during heating (not 0)

2. **Verify heating cycles:**
   - Manually trigger heating
   - Watch logs for cycle detection messages
   - Should see messages like "Heating cycle detected"

3. **Check thermostat settings:**
   - VTherm must be in "heat" mode
   - Must have a target temperature set
   - Sensor must be actively reading temperature

4. **Enable debug logging:**
   ```yaml
   logger:
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```
   Share output if still failing

---

## 🐛 General Debugging

### Enable Debug Logging

To see what IHP is thinking:

**Add to configuration.yaml:**
```yaml
logger:
  default: info
  logs:
    custom_components.intelligent_heating_pilot: debug
```

**Or through UI:**
1. Developer Tools → Logs
2. Logger → Set log level
3. Filter: `custom_components.intelligent_heating_pilot`
4. Level: `DEBUG`

**Then:**
- Trigger heating manually
- Watch logs in real-time
- Look for calculation details, decisions, errors

### Checking System Health

**Verify all components are working:**

1. **VTherm is active:**
   - Should show current temperature
   - Should show target temperature
   - Should have `temperature_slope` attribute

2. **Scheduler is active:**
   - Scheduler entity should exist (`switch.schedule_*`)
   - Should toggle between ON/OFF
   - Should accept service calls

3. **Home Assistant logs are clean:**
   - No Python errors in logs
   - No repeated error messages
   - No "Integration not responding" warnings

### Testing Individual Components

**Test VTherm heating:**
```yaml
service: climate.turn_on
target:
  entity_id: climate.your_thermostat
data:
  temperature: 25  # High enough to trigger heating
```

**Test scheduler:**
```yaml
service: switch.turn_on
target:
  entity_id: switch.your_schedule
```

**Test IHP service:**
```yaml
service: intelligent_heating_pilot.reset_learning
```

---

## 📝 Reporting a Bug

If you've tried the above and still have problems:

1. **Gather information:**
   - Home Assistant version
   - IHP version
   - What did you do?
   - What happened?
   - What did you expect?

2. **Collect logs:**
   - Enable debug logging
   - Reproduce the issue
   - Copy relevant log lines

3. **Report on GitHub:**
   - Go to [Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
   - Click **New issue**
   - Use "Bug Report" template
   - Include all information above

---

## 💬 Getting Help

- **[GitHub Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)** - Ask questions, share experiences
- **[GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)** - Report bugs or request features
- **[Home Assistant Community](https://community.home-assistant.io/)** - General Home Assistant help

---

**Back to:** [User Guide](USER_GUIDE.md) | [Configuration](CONFIGURATION.md) | [How It Works](HOW_IT_WORKS.md)
