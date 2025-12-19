# Configuration Guide - Intelligent Heating Pilot

## Quick Setup (5 minutes)

### Step 1: Open Integration Settings

1. Go to **Settings** (⚙️) → **Devices & Services**
2. Click **+ Create Integration**
3. Search for **"Intelligent Heating Pilot"** (or "IHP")
4. Select it from the list

### Step 2: Fill in Required Information

A configuration dialog will appear. Here's what you need:

| Field | What It Is | How to Find |
|-------|-----------|------------|
| **Name** | A friendly name for this IHP instance | Any name you want (e.g., "Living Room") |
| **VTherm Entity** | Your Versatile Thermostat climate entity | Go to **Devices** → Find your thermostat → Copy entity name (e.g., `climate.living_room`) |
| **Scheduler Entity** | HACS Scheduler switch(es) that control the VTherm | Go to **Devices** → Find your scheduler → Copy entity name (e.g., `switch.schedule_heating`) |

### Step 3: (Optional) Add Environmental Sensors

These sensors help IHP make better predictions but are **not required**:

| Sensor | Purpose | Example |
|--------|---------|---------|
| **Humidity Sensor** | Adjusts calculations for moisture impact | `sensor.living_room_humidity` |
| **Outdoor Temp Sensor** | Accounts for outdoor conditions | `sensor.outdoor_temperature` |
| **Cloud Coverage Sensor** | Adjusts for solar gain | `sensor.cloud_coverage` |

### Step 4: Complete Setup

1. Click **Submit**
2. IHP will initialize and start monitoring your heating system
3. You should see a new device: **"Intelligent Heating Pilot [Your Name]"**

✅ **Setup complete!** IHP is now running. Continue reading to understand what to expect.

---

## After Installation: What to Expect

### First 3-5 Heating Cycles

During this initial learning phase:

- ✅ IHP monitors your VTherm's heating behavior
- ✅ It collects data about how fast your room heats
- 📊 The **Learned Heating Slope** sensor might show default values (conservative)
- 📈 Predictions improve with each heating cycle

**What you'll see:**
- New sensors appear on your device
- Logs show IHP learning and calculating
- Predictions become more accurate over time

### What IHP Does Automatically

Once configured, IHP operates automatically:

1. **Monitors** your scheduler for upcoming heating schedules
2. **Learns** how your heating system performs
3. **Calculates** when to trigger heating to reach target temperature exactly on time
4. **Triggers** heating at the optimal anticipation time

**You don't need to do anything—IHP works in the background!**

---

## Modifying Configuration

Need to change entities after setup?

1. Go to **Settings** → **Devices & Services**
2. Find your **Intelligent Heating Pilot** integration
3. Click the **⋮ (three dots)** menu
4. Select **Reconfigure** or **Options**
5. Update the entities
6. Click **Submit**

The integration will reload automatically.

---

## Advanced Configuration (Optional)

### Data Retention Settings

**New in v0.4.0+**: IHP now caches heating cycles for improved performance and longer learning history.

| Setting | Default | Description |
|---------|---------|-------------|
| **Data Retention Days** | 30 days | How long to keep cached heating cycles |

**What This Affects:**
- 📊 **Cycle Cache**: Heating cycles older than this are automatically pruned
- 🧠 **Learning History**: More retention = better slope calculations
- 💾 **Storage**: Longer retention uses slightly more disk space (minimal)

**Recommended Values:**
- **Minimum**: 7 days (matches typical HA recorder retention)
- **Default**: 30 days (optimal balance of learning quality and storage)
- **Maximum**: 90 days (for very detailed historical analysis)

**When to Change:**
- ✅ **Increase** if you want longer learning history for seasonal patterns
- ⚠️ **Decrease** if disk space is very limited (not recommended)

**Note**: This setting replaces the old `lhs_retention_days` configuration. Both keys are supported for backward compatibility.

### Disabling Optional Sensors

If you don't have certain sensors and don't want to see warnings:

1. Leave those fields empty in configuration
2. IHP will skip those calculations (no performance impact)

### Using Multiple Heating Zones

You can configure multiple IHP instances—one per VTherm:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Create Integration** again
3. Configure a **new instance** with a different VTherm entity
4. Each instance learns independently and triggers its own scheduler

---

## Entities Created by IHP

After configuration, IHP creates these sensors on your device:

### Main Sensors

| Sensor | What It Shows | Updated |
|--------|--------------|---------|
| **Learned Heating Slope** | How fast your room heats (°C/hour) | Every heating cycle |
| **Anticipation Time** | When heating will start | Every update cycle |
| **Next Schedule** | Details of next heating event | Every schedule change |

### Debug/Status Sensors

Additional sensors may appear for monitoring and troubleshooting (see [How IHP Works](HOW_IT_WORKS.md)).

---

## Configuration Checklist

Before moving forward, verify:

- [ ] IHP appears in integrations
- [ ] At least one VTherm entity selected
- [ ] At least one scheduler entity selected
- [ ] New sensors appear on your IHP device
- [ ] No error messages in logs

✅ **All checked?** Great! Now read [How IHP Works](HOW_IT_WORKS.md) to understand what's happening.

---

## Troubleshooting Configuration

### "VTherm entity not found"

**Solution:**
1. Go to **Developer Tools** → **States**
2. Search for entities starting with `climate.`
3. Copy the exact entity name (case-sensitive)
4. Update IHP configuration with correct name

### "No scheduler entities available"

**Solution:**
1. Verify HACS Scheduler Component is installed
2. Create at least one schedule in the scheduler
3. Verify scheduler switch entity exists (should start with `switch.`)
4. Restart Home Assistant and reconfigure IHP

### IHP won't save configuration

**Solution:**
- Check Home Assistant logs for error details
- Ensure all required fields are filled
- Try reconfiguring from scratch
- If still failing, report on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)

---

**Next:** Go to [How IHP Works](HOW_IT_WORKS.md) to understand heating cycle detection and prediction logic
