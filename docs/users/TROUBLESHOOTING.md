# Troubleshooting Guide - Intelligent Heating Pilot

## ❓ Quick Problem Finder

**What's your problem?** Find it below and jump to the solution:

| Issue | Go To |
|-------|-------|
| IHP doesn't appear in integrations | [Installation Issues](#installation-issues) |
| Can't complete configuration | [Configuration Issues](#configuration-issues) |
| Home Assistant slow after IHP setup | [Home Assistant slow or unresponsive after IHP configuration](#home-assistant-slow-or-unresponsive-after-ihp-configuration) |
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

### My thermostat is not in the list

**Symptoms:**
- The VTherm field does not offer your thermostat
- Or "This integration is already configured" when you submit

**Solution:**

1. Only **Versatile Thermostat** entities are offered. A thermostat from another integration cannot be used with IHP
2. "This integration is already configured" means another IHP device already has this **Name**: choose another name

### Home Assistant slow or unresponsive after IHP configuration

**Symptoms:**
- Configuration saves successfully
- But UI becomes slow to load
- Features take several minutes to respond
- May last up to 5 minutes after configuration

**Cause:**
- IHP is performing initial extraction of heating cycles from recorder history
- With high **Slope Data Retention** settings (>30 days) or high recorder `purge_keep_days` (>10 days), this can take several minutes

**Expected behavior:**
- ⏱️ **Processing time**: 2-5 minutes depending on retention settings
- 📊 **Example**: With 60-day retention and `purge_keep_days=60`, initial extraction takes ~3 minutes
- ✅ **This only happens once**: After initial extraction, updates are incremental and fast
- 📱 **UI may be temporarily slow**: This is normal during initial processing

**Solution:**

1. **Wait for initial extraction to complete:**
   - Allow 5-10 minutes for first-time processing
   - Check logs to confirm extraction is in progress
   - UI responsiveness will return once complete

2. **If slowness persists beyond 10 minutes:**
   - Check Home Assistant logs for errors:
     ```yaml
     logger:
       logs:
         custom_components.intelligent_heating_pilot: debug
     ```
   - Look for messages about heating cycle extraction

3. **Reduce Slope Data Retention if needed:**
   - Settings → Devices & Services
   - Open Intelligent Heating Pilot
   - Click **Configure** on the device
   - Lower **Slope Data Retention** to 30 or less
   - This reduces initial processing time

4. **Check your recorder configuration:**
   - High `purge_keep_days` in recorder increases processing time
   - Consider reducing recorder retention if performance is critical
   - See Home Assistant recorder documentation

**Prevention:**
- Use default **Slope Data Retention** (30 days) initially
- Increase retention gradually after IHP is stable
- Be aware that higher retention = longer initial processing

### My scheduler is not in the list

**Symptoms:**
- The scheduler field does not offer your scheduler

**Solution:**

IHP only supports HACS Scheduler switches and native `schedule.*` helpers (see [Supported Schedulers](CONFIGURATION.md#supported-schedulers)). Automations, calendars and other scheduler integrations cannot be selected.


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

4. Open the IHP device's **Configure** form and select the scheduler

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
   - Use **required fields only** (Name, VTherm)
   - Skip optional sensors first
   - Add them later if needed

4. If error persists:
   - Delete the device: Settings → Devices & Services → Intelligent Heating Pilot → ⋮ → Delete
   - Restart Home Assistant
   - Add the device again from scratch

---

## 📊 Sensor Issues

### Sensors showing "unknown" or "unavailable"

**Symptoms:**
- Contextual Learned Heating Slope: `unknown`
- Anticipated Start Time: `unknown`
- Next Schedule Time: No data

**Possible Causes:**

1. **IHP just installed** - Wait a few minutes for initialization and the history extraction
2. **No cycle learned for this hour** - The Contextual Learned Heating Slope stays `unknown` until a cycle is learned for the next slot's hour (the global slope is used meanwhile)
3. **No supported scheduler, or no slot IHP can read** - See [Supported Schedulers](CONFIGURATION.md#supported-schedulers)
4. **Scheduler switched off** - If a HACS Scheduler's state is "off", its slots are ignored (this is normal)
5. **Native schedule ON** - While a `schedule.*` helper is ON, its next block is not known yet

**Solution:**

1. **Check if scheduler is enabled:**
   - Developer Tools → States
   - Find your scheduler entity (e.g., `switch.schedule_heating`)
   - State should NOT be "off"
   - If "off", this is expected behavior (IHP is inactive)

2. **Check the next slot:**
   - Its action must be `climate.set_temperature` or `climate.set_preset_mode`
   - For a preset, the VTherm must expose that preset's temperature

3. **Verify VTherm is working:**
   - Check VTherm entity in Developer Tools → States
   - It must report a current temperature and a target temperature

4. **Check IHP is running:**
   - Settings → Devices & Services
   - Click Intelligent Heating Pilot
   - Each device should be listed without error

### IHP configured without a scheduler

**What you see:**
- Anticipation-related sensors show `unknown`
- No errors in logs

**Expected behavior:**
- Without a scheduler, IHP cannot compute upcoming targets, so sensors remain `unknown`
- This is normal and does not indicate a failure

**How to enable scheduler-based predictions:**
- Configure a scheduler in the IHP device's **Configure** form
- See [Supported Schedulers](CONFIGURATION.md#supported-schedulers) for what IHP can read

### Sensors show data but it looks wrong

**Symptoms:**
- Global Learned Heating Slope stays at exactly 2.0 °C/h (the default)
- Anticipated Start Time is 6 hours before the slot (the maximum)
- Prediction Confidence is 0%

**Solution:**

See [Prediction Issues](#prediction-issues) below - likely a learning problem, not a sensor problem.

---

## 🔥 Heating Not Triggering

### Scheduler turns on but IHP never triggers it

**Symptoms:**
- Scheduler is configured and has upcoming events
- You wait for the scheduled time
- Heating never starts early (it starts at the slot's time)

**Possible Causes:**

1. **Native `schedule.*` helper** - IHP never starts the heating for it: it only computes the anticipated start (see [Supported Schedulers](CONFIGURATION.md#supported-schedulers))
2. **IHP Preheating switch is off** - IHP keeps calculating but does not trigger anything
3. **Unsupported slot action** - The slot does not use `climate.set_temperature` or `climate.set_preset_mode`, so IHP has no target to anticipate
4. **Scheduler conditions not met** - The scheduler refused the slot; when every scheduler is blocked, the anticipation sensor lists them in its `blocked_schedulers` attribute
5. **The schedule controls another thermostat** - IHP waits for its own VTherm to take the slot's temperature; otherwise it treats the scheduler as blocked
6. **No heating needed** - The room is already at the slot's target

**Solution:**

1. **Verify configuration:**
   - Settings → Devices & Services → Intelligent Heating Pilot
   - Click **Configure** on the device
   - Check the scheduler entities
   - Should show your HACS Scheduler switch

2. **Check logs for errors:**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```
   Look for trigger-related messages

3. **Check the scheduler service:**
   - Call `scheduler.run_action` manually: Developer Tools → Actions
   - The VTherm should take the slot's temperature

### Heating triggers too early

**Symptoms:**
- IHP starts heating 2+ hours before scheduled time
- Room reaches target well before the scheduled event

**Cause:**
- Learned slope is too low (IHP thinks heating is slower than it actually is)

**Solutions:**

- **Check the learned values:**
  - Monitor the "Global Learned Heating Slope" and "Contextual Learned Heating Slope" sensors
  - A contextual slope learned for the slot's hour is used before the global one

- **Manual reset if something changed:**
  - If you replaced radiators or changed insulation, or after upgrading from an earlier version
  - Call the `intelligent_heating_pilot.reset_learning` service with any sensor of the device as `entity_id`
  - IHP clears its learned values and relearns them from the recorder history

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

2. **Check the limits:**
   - IHP never starts more than 6 hours before a slot
   - A heating cycle longer than **Maximum Cycle Duration** (5 hours by default) is not learned: raise it for slow underfloor heating

3. **Check the weather:**
   - A sudden cold spell slows the room down before new cycles are learned
   - IHP does not use the outdoor temperature in the prediction yet

4. **Reset learning:**
   ```yaml
   action: intelligent_heating_pilot.reset_learning
   data:
     entity_id: sensor.living_room_anticipated_start_time
   ```
   IHP relearns the slope from the recorder history

---

## 🏖️ Vacation Mode & Scheduler Conditions

### IHP still triggers heating when on vacation

**Symptoms:**
- You disabled scheduler or set vacation mode
- But heating still triggers

**Diagnosis:**

A native `schedule.*` helper never makes IHP start the heating: if heating starts, it comes from your own automation or the schedule itself. The steps below are for HACS Scheduler.

1. **Check scheduler state:**
   - Developer Tools → States
   - Find your scheduler entity
   - State should be "off" if disabled

2. **Check scheduler conditions:**
   - If using conditions (e.g., `input_boolean.vacation`)
   - Verify the condition entity state
   - Scheduler should skip actions when conditions fail

**Solution:**

1. **Disable scheduler properly:**
   - Turn OFF the scheduler switch entity
   - State should change to "off"
   - IHP should show `unknown` for anticipation sensors

2. **Verify vacation mode automation:**
   ```yaml
   # Example automation to disable scheduler
   automation:
     - alias: "Vacation Mode - Disable Heating Scheduler"
       trigger:
         - platform: state
           entity_id: input_boolean.vacation_mode
           to: 'on'
       action:
         - action: switch.turn_off
           target:
             entity_id: switch.schedule_heating
   ```

3. **Check logs for trigger attempts:**
   ```yaml
   logger:
     logs:
       custom_components.intelligent_heating_pilot: debug
   ```
   Look for "run_action" calls

### Sensors show "unknown" but I'm not on vacation

**Symptoms:**
- Anticipation sensors show `unknown`
- Scheduler is enabled (state is NOT "off")
- You expect heating to occur

**Cause:**
- No valid upcoming timeslots detected
- Scheduler might have no schedules configured
- Or all schedules are in the past

**Solution:**

1. **Verify scheduler has active schedules:**
   - Open Scheduler UI
   - Check if any schedules exist
   - Check if schedules are for future times

2. **Check scheduler entity attributes:**
   - Developer Tools → States
   - Find your scheduler entity
   - Look for `next_trigger` attribute
   - Should show next scheduled time
   - Check that the next slot's action is `climate.set_temperature` or `climate.set_preset_mode`

3. **Check the IHP device's schedulers:**
   - Settings → Devices & Services
   - Open Intelligent Heating Pilot
   - Click **Configure** on the device
   - Verify scheduler entity is correct

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
  - Each slot's hour needs a few learned preheats
  - IHP averages the cycles, so a few unusual ones weigh less over time

- **Check for inconsistencies:**
  - Are heating cycles similar? (target temp, duration)
  - Or very different each time?
  - If different, IHP will naturally vary more
  - Variations in your schedule cause variations in slope

### Nothing seems to be learned

**Symptoms:**
- Global Learned Heating Slope stays at exactly 2.0 °C/h (the default)
- Dead Time stays at the **Initial Dead Time** setting
- No improvement over many days

Prediction Confidence is not a sign of learning: it only depends on the slope used and on the humidity sensor (see [Confidence Levels](HOW_IT_WORKS.md#-confidence-levels)).

**Cause:**
- No heating cycle is detected or kept in the recorder history

**Solution:**

1. **Check the recorder:**
   - The VTherm's history must be recorded (not excluded from the recorder)
   - IHP learns from the current temperature, target temperature, `hvac_mode` and `hvac_action` history

2. **Verify heating cycles:**
   - Cycles disturbed by load shedding or safety mode are not learned
   - Cycles longer than **Maximum Cycle Duration** are not learned
   - Enable debug logging and look for heating cycle extraction messages

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
1. Settings → Devices & Services
2. Open Intelligent Heating Pilot
3. Click ⋮ → **Enable debug logging**
4. Disable it again later to download the log file

**Then:**
- Trigger heating manually
- Watch logs in real-time
- Look for calculation details, decisions, errors

### Checking System Health

**Verify all components are working:**

1. **VTherm is active:**
   - Should show current temperature
   - Should show target temperature

2. **Scheduler is active:**
   - HACS Scheduler entity should exist (`switch.schedule_*`) and not be "off"
   - Should have a `next_trigger` attribute
   - Should accept `scheduler.run_action` calls

3. **Home Assistant logs are clean:**
   - No Python errors in logs
   - No repeated error messages
   - No "Integration not responding" warnings

### Testing Individual Components

**Test VTherm heating:**
```yaml
action: climate.set_temperature
target:
  entity_id: climate.your_thermostat
data:
  temperature: 25  # High enough to trigger heating
```

**Test scheduler:**
```yaml
action: switch.turn_on
target:
  entity_id: switch.your_schedule
```

**Test IHP service:**
```yaml
action: intelligent_heating_pilot.reset_learning
data:
  entity_id: sensor.living_room_anticipated_start_time
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
