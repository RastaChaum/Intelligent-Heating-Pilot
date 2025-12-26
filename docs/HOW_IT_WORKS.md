# How IHP Works - Heating Cycle Detection & Prediction

## 🎯 The Big Picture

Intelligent Heating Pilot does one thing very well: **It learns how fast your heating system works, then uses that knowledge to start heating at exactly the right time.**

```
┌─ Does my room need to heat?
│
├─ If YES: Calculate how long it will take
│  └─ Using: Learned slope + Distance to target + Environment
│
└─ Trigger heating at the perfect moment
   (Not too early, not too late)
```

---

## 📊 Core Concept: Learned Heating Slope (LHS)

### What is it?

The **Learned Heating Slope (LHS)** is how fast your room heats up, measured in **°C per hour** (degrees per hour).

**Examples:**
- LHS = 2.0 means your room heats up 2°C every hour
- LHS = 0.5 means your room heats up 0.5°C every hour (slower, poor insulation)
- LHS = 5.0 means your room heats up 5°C every hour (well-insulated)

### How is it Learned?

IHP computes the Learned Heating Slope from detected heating cycles:

1. **Detect a heating cycle** using the start/stop rules described below.
2. **Capture temps**: record indoor temperature at cycle start and at cycle end.
3. **Calculate cycle slope**: 
   - Temperature gain = end temp − start temp
   - Duration = end time − start time
   - Cycle slope = (temperature gain ÷ duration hours)
4. **Average the slopes** across observed cycles to produce the current LHS.

### Cycle Cache: Performance Optimization

**New in v0.4.0+**: IHP now uses an **incremental cycle cache** to dramatically improve performance and data retention.

**What Changed:**
- **Before**: Every LHS calculation scanned the entire Home Assistant recorder history (heavy database load)
- **After**: Detected cycles are cached locally, with only new cycles extracted every 24 hours

**How It Works:**
1. **First Run**: IHP scans recorder history and caches all detected heating cycles
2. **24-Hour Refresh**: Every 24 hours, IHP queries only new data since last search
3. **Incremental Updates**: New cycles are automatically appended to cache (no duplicates)
4. **Automatic Pruning**: Old cycles beyond retention period (default: 30 days) are removed
5. **LHS Calculation**: Uses cached cycles only—no recorder queries needed

**Benefits:**
- ⚡ **~95% reduction** in database queries (only searches new data every 24h)
- 📈 **Longer retention**: Keeps 30 days of cycles even if HA recorder retention is only 7-10 days
- 🚀 **Better learning**: More historical data = more accurate slope calculations
- 💾 **Persistent**: Cache survives Home Assistant restarts

**Configuration:**
The cache retention period is controlled by `data_retention_days` (default: 30 days). This can be configured during setup or by reconfiguring the integration.

**Note**: The old configuration key `lhs_retention_days` is still supported for backward compatibility but will be deprecated in future versions.

### Why This Matters

Knowing your LHS, IHP can answer: **"If I need to heat 3°C and my slope is 2°C/hour, how long should I wait?"**

Answer: 1.5 hours (3 ÷ 2 = 1.5)

---

## 🔍 Heating Cycle Detection

A **heating cycle** is a period when your room is actively heating. IHP uses specific rules to identify when a cycle starts and stops.

### What Triggers a Heating Cycle Start?

In the current implementation, a heating cycle **starts** when all of these are true:

1. **Heating mode is enabled** (`hvac_mode` in `heat`, `heat_cool`, or `auto`, or the entity state is truthy)
2. **Heating action is active** (`hvac_action` reports `heating` or `preheating`, or the entity state is truthy)
3. **Target is above current temperature** by more than the configured delta (default **0.2°C**)

This logic is evaluated on every historical measurement; there is no additional debounce.

### What Stops a Heating Cycle?

A heating cycle **ends** as soon as **one** of these conditions is met:

1. **Heating mode is disabled** (`hvac_mode` no longer in `heat`, `heat_cool`, or `auto`, or the entity state becomes falsy)
2. **Room reached target**: indoor temperature is at or above `(target - delta)`, with delta defaulting to **0.2°C**

There is **no 5-minute grace period** in the code today—cycle end is detected immediately on the measurement that satisfies one of the conditions.

**Example Scenarios:**

| Scenario | What Happens |
|----------|--------------|
| Natural completion | Room hits target → End detected immediately |
| Scheduler or manual stop | Mode switches off → End detected immediately |
| Early comfort | Target lowered while heating | Mode may stay on; end triggers when room is within 0.2°C of the new target |


### Why These Rules?

The current logic favors **quick detection** over debounce: cycles start as soon as heating truly begins and stop as soon as the system is off or the room is effectively at target. This keeps slope calculations aligned with the exact heating window but means brief oscillations around the target can create short cycles if the temperature crosses the `(target - delta)` boundary repeatedly.

---

## 🧮 Prediction Algorithm

Once IHP has learned the heating slope, it predicts when heating should start.

### The Calculation

The core prediction formula is simple:

```
Anticipation Time (minutes) = (Temperature Difference / Learned Slope) × 60

Where:
- Temperature Difference = Target Temp - Current Temp
- Learned Slope = °C per hour (learned from heating cycles)
```

**Example:**
```
Need to heat: 3°C (from 18°C to 21°C)
Learned Slope: 2.0°C/hour
Anticipation Time = (3 / 2.0) × 60 = 90 minutes
```

So IHP will trigger heating **90 minutes before the scheduled time**.

### Environmental Adjustments

The basic calculation is then **adjusted** based on real-world conditions:

#### 1. **Outdoor Temperature Effect**

Colder outdoor air = **More heat loss** = **Need to heat longer**

```
Adjustment: If outdoor temp is below 15°C
→ Add extra heating time (warmth escapes faster)
```

#### 2. **Humidity Effect**

Higher humidity = **Less efficient heating** = **Need to heat longer**

```
Adjustment: High humidity (>70%)
→ Add extra heating time (moisture affects thermal dynamics)
```

#### 3. **Solar Gain (Cloud Coverage)**

Clear sky = **Solar heat gain** = **Might heat faster**

```
Adjustment: If cloud coverage is low (<20%)
→ Reduce anticipation time slightly (free solar energy helps)
```

### Safety Bounds

IHP applies **minimum and maximum limits** to predictions to stay reasonable:

| Limit | Value | Reason |
|-------|-------|--------|
| **Minimum Anticipation** | 5 minutes | Don't trigger too early if slope is very high |
| **Maximum Anticipation** | 4 hours | Don't trigger too early for slow heating |

---

## 📈 Confidence Levels

IHP calculates a **confidence score** (0-100%) for each prediction.

### What Affects Confidence?

| Factor | Impact |
|--------|--------|
| **No heating history** | Very low (≈30%) - First prediction uses default |
| **Few cycles observed** | Low (≈50%) - Limited data to learn from |
| **Many cycles observed** | High (≈80%+) - Solid understanding of your system |
| **Extra sensors available** | +10% per sensor - Better environmental awareness |

**Why Confidence Matters:**
- **High confidence (80%+)**: IHP knows your system well, predictions are accurate
- **Low confidence (30-50%)**: IHP is still learning, predictions may be less accurate
- **Zero confidence (0%)**: Error condition - heating won't trigger automatically

### First-Time Setup: Default Behavior

When IHP has no learning history:

- ✅ It uses a **conservative default slope of 2°C/hour**
- ✅ **Confidence is ~30%** (low confidence, conservative approach)
- ✅ **It will trigger heating early** to avoid undershooting
- ✅ After 3-5 cycles, confidence increases and predictions improve

---

## 🔄 Complete Flow: From Schedule to Heating

Here's the full journey from a scheduled event to IHP triggering heating:

```
1. SCHEDULER ACTIVATION
   └─ "Heat to 21°C at 06:00" → IHP detects this event

2. PREDICTION CALCULATION
   └─ Calculate when to start heating to reach 21°C by 06:00
      ├─ Get current temp (18°C)
      ├─ Calculate delta (21°C - 18°C = 3°C)
      ├─ Use learned slope (2°C/hour)
      ├─ Apply environmental adjustments (+/- minutes)
      ├─ Apply safety bounds (5 min to 4 hours)
      └─ Result: "Start heating at 04:30"

3. HEATING CYCLE STARTS
   └─ At 04:30 → IHP triggers the scheduler
      └─ VTherm detects heating activity
      └─ Temperature rises toward 21°C

4. HEATING CYCLE MONITORING
   └─ IHP watches temperature rise
      ├─ Collects VTherm's slope observations
      ├─ **OVERSHOOT RISK DETECTION**: Monitors estimated temperature
      │  └─ On every temperature update during preheating:
      │     ├─ Calculate: estimated_temp = current_temp + (slope × time_remaining)
      │     ├─ Check: if estimated_temp > target_temp + 0.5°C
      │     └─ Action: Stop preheating (revert to scheduler setpoint)
      └─ Waits for cycle completion

5. CYCLE COMPLETION & LEARNING
   └─ Temperature reaches 21°C (or schedule ends)
      ├─ Heating stops
      ├─ IHP captures final slope reading
      ├─ Adds slope to history
      ├─ Recalculates learned slope average
      └─ Confidence increases

6. NEXT CYCLE
   └─ Next scheduled heating event
      └─ IHP uses updated slope for even better predictions
```

### Important: IHP Does Not Directly Control VTherm

**Key architectural principle:**
- IHP never directly controls your thermostat (VTherm)
- IHP triggers the **scheduler's run_action service**
- The scheduler then controls VTherm based on its configuration
- This ensures all your scheduler conditions and automations work as expected

**Benefits:**
- ✅ Vacation mode works automatically (scheduler conditions)
- ✅ Input boolean conditions are respected
- ✅ Time-based conditions continue to work
- ✅ You maintain full control through your scheduler
- ✅ IHP is only an intelligent trigger mechanism

**What happens when scheduler is disabled:**
```
Scheduler State = "off"
   ├─ IHP detects no upcoming timeslots
   ├─ Anticipation sensors show "unknown"
   ├─ No heating will be triggered
   └─ IHP waits for scheduler to be re-enabled
```


---

## 🛡️ Overshoot Risk Prevention

### What is Overshoot?

**Overshoot** occurs when preheating starts too early, causing the room temperature to exceed the target before the scheduled time. This wastes energy and can reduce comfort.

**Example of Overshoot:**
```
Target: 20°C at 09:00
Preheating started: 07:00 (with LHS = 2°C/h, anticipating 2 hours needed)
Problem: By 08:00, room reaches 20°C (1 hour early!)
Result: Room continues heating to 21-22°C, wasting energy
```

### How IHP Prevents Overshoot

IHP continuously monitors temperature during preheating and **stops early** if it detects overshoot risk.

#### Detection Algorithm

During active preheating, on every VTherm temperature update:

1. **Get current data:**
   - Current temperature: 19°C
   - Current heating slope: 3°C/hour
   - Time until target: 30 minutes (0.5 hours)
   - Target temperature: 20°C

2. **Calculate estimated temperature:**
   ```
   estimated_temp = current_temp + (slope × time_remaining)
   estimated_temp = 19°C + (3°C/h × 0.5h) = 20.5°C
   ```

3. **Check overshoot threshold:**
   ```
   overshoot_threshold = target_temp + 0.5°C
   overshoot_threshold = 20°C + 0.5°C = 20.5°C
   
   if estimated_temp >= overshoot_threshold:
       STOP PREHEATING (revert to scheduler setpoint)
   ```

4. **Action taken:**
   - Calls `scheduler.cancel_action()` to revert to current scheduled temperature
   - Clears preheating state
   - Logs warning with current, estimated, and target temperatures
   - Respects scheduler conditions (won't cancel if scheduler is disabled)

#### Key Features

| Feature | Behavior |
|---------|----------|
| **Trigger Frequency** | Every VTherm temperature change during preheating |
| **Threshold** | Target temperature + 0.5°C |
| **Action** | Revert to scheduler setpoint (via `cancel_action`) |
| **Conditions** | Only active during preheating with valid scheduler entity |
| **Safety** | Checks scheduler is enabled before reverting |

### When Overshoot Detection Activates

**Conditions for overshoot check:**
1. ✅ Preheating is currently active (`_is_preheating_active = True`)
2. ✅ Scheduler entity is set (`_active_scheduler_entity` is not None)
3. ✅ VTherm temperature has changed (event bridge triggers)
4. ✅ Current slope is positive and valid
5. ✅ Target time is in the future
6. ✅ Estimated temperature > threshold

**Example Log Output:**
```
WARNING: Overshoot risk! Current: 19.0°C, estimated: 21.0°C, target: 20.0°C - reverting to current schedule
```

### Why Overshoot Can Still Occur

Even with detection enabled, overshoot might happen if:

1. **Slope changes rapidly**: If heating suddenly accelerates between temperature updates
2. **Infrequent updates**: If VTherm reports temperature changes slowly (>5 minutes)
3. **Thermal inertia**: Radiators/heating elements continue warming after shutdown
4. **Threshold too loose**: Default 0.5°C threshold might be insufficient for fast heating systems

### Tuning Recommendations

If you experience overshoot despite the detection:

1. **Check VTherm slope attribute**: Ensure it's being reported correctly
2. **Monitor log frequency**: Look for "Preheating active, checking overshoot risk" messages
3. **Consider TPI settings**: Adjust VTherm's TPI parameters for better temperature control
4. **Verify sensor accuracy**: Ensure temperature sensor is accurate and responsive

### Troubleshooting Overshoot Detection

**Problem: Overshoot still occurring**

Possible causes:
- Slope calculation is delayed or inaccurate
- VTherm temperature updates are too infrequent
- Heating system has high thermal inertia

**Problem: Preheating stops too early (undershoot)**

Possible causes:
- Slope is overestimated (system heats slower than predicted)
- Need more heating cycles for LHS to stabilize
- Environmental conditions changed (colder outdoor temperature)

---

## ⚠️ Common Scenarios & Expected Behavior

### Scenario 1: First Heating Cycle

**Expected:**
- Low confidence (30%)
- Heating triggers **early** (conservative approach)
- May reach target before scheduled time (overshoots)

**Why:** No learning history yet, using default slope

**Next:** After 2-3 more cycles, accuracy improves

### Scenario 2: After 3-5 Cycles

**Expected:**
- Confidence increases (50-70%)
- Predictions get **closer to actual scheduled time**
- Less overshoot, more precise timing

**Why:** IHP has learned your actual heating slope

### Scenario 3: Very Cold Weather

**Expected:**
- Predictions **increase slightly** (start heating earlier)
- More heat loss through walls

**Why:** Environmental adjustment for outdoor temperature

### Scenario 4: High Humidity

**Expected:**
- Predictions **increase slightly** (start heating earlier)
- Humidity affects thermal transfer

**Why:** Environmental adjustment for humidity

### Scenario 5: Very Sunny Day

**Expected:**
- Predictions **might decrease slightly** (start heating later)
- Solar gain helps heating

**Why:** Environmental adjustment for solar gain

### Scenario 6: Vacation Mode / Scheduler Disabled

**Expected:**
- Anticipation sensors show `unknown`
- No heating triggers occur
- IHP remains installed but inactive
- Learning data is preserved

**Why:** When scheduler state is "off", IHP detects no upcoming timeslots

**How to trigger vacation mode:**
1. Turn off your scheduler switch (state becomes "off")
2. OR: Use scheduler conditions (e.g., `input_boolean.vacation`)
3. IHP automatically stops monitoring
4. When you return, re-enable scheduler
5. IHP resumes normal operation with preserved learning

**What's preserved:**
- ✅ Learned heating slope
- ✅ Historical data
- ✅ Confidence level
- ✅ All configuration

**What happens:**
- ❌ No heating triggers
- ❌ Sensors show "unknown" (no upcoming timeslots)
- ❌ No predictions calculated

### Scenario 7: Scheduler Conditions Not Met

**Expected:**
- IHP calculates anticipation time normally
- At trigger time, IHP calls `run_action`
- Scheduler evaluates its conditions
- If conditions fail, heating is skipped
- IHP continues monitoring for next timeslot

**Why:** IHP uses `skip_conditions: false` to respect scheduler logic

**Example:**
```yaml
# Your scheduler has a condition:
condition:
  - condition: state
    entity_id: input_boolean.vacation
    state: 'off'

# When input_boolean.vacation is 'on':
- IHP still calculates trigger time
- IHP calls run_action at 04:30
- Scheduler checks condition → fails
- Heating is NOT triggered
- IHP tries again next scheduled time
```

---

## 🐛 Troubleshooting: Why is prediction inaccurate?

### Problem: Always heats too early

**Possible Causes:**
- Learned slope is **too low** (IHP thinks heating is slower than it is)
- **Few cycles observed** - Still in learning phase
- **External heat source** (sunlight, other heating) not accounted for

**Solution:**
- Wait 3-5 more heating cycles
- Or manually reset learning: `service: intelligent_heating_pilot.reset_learning`

### Problem: Always heats too late (room never reaches target)

**Possible Causes:**
- Learned slope is **too high** (IHP thinks heating is faster than it is)
- **Radiators blocked** or heating capacity reduced
- **Humidity very high** - Adjustments may be insufficient

**Solution:**
- Check radiators are clear and working
- Verify thermostat sensor readings are correct
- Reset learning and monitor next 5 cycles

### Problem: Prediction jumps around wildly

**Possible Causes:**
- **Very few cycles** - High variability with limited data
- **Inconsistent heating** - System behaves differently each time
- **Sensor errors** - Temperature readings are noisy

**Solution:**
- Wait for 10+ cycles to stabilize
- Check sensor accuracy
- Verify heating system is functioning consistently

### Problem: No prediction at all

**Possible Causes:**
- **No learning history** yet
- **Zero confidence** - Something prevented learning
- **Scheduler not detected** - IHP can't see upcoming events

**Solution:**
1. Check IHP is configured with correct scheduler entity
2. Create a test schedule 
3. Check logs: `logger: custom_components.intelligent_heating_pilot: debug`

---

## 📊 Monitoring IHP

### Key Sensors to Watch

| Sensor | What to Check |
|--------|--------------|
| **Learned Heating Slope** | Should gradually stabilize around your actual slope (0.5-5.0°C/h) |
| **Anticipation Time** | Should match when heating actually starts |
| **Confidence** | Should increase toward 80%+ after 5-10 cycles |

### Debug Mode

Enable detailed logging to see what IHP is thinking:

```yaml
logger:
  default: info
  logs:
    custom_components.intelligent_heating_pilot: debug
```

Then check Home Assistant logs for detailed calculations and decision-making.

---

## 🎓 Key Concepts Summary

| Concept | Meaning |
|---------|---------|
| **Learned Heating Slope (LHS)** | How fast your room heats (°C/hour) |
| **Heating Cycle** | A period from when heating starts until it stops |
| **Cycle Detection** | Rules that identify when heating cycles begin and end |
| **Anticipation Time** | When to trigger heating to reach target on time |
| **Confidence** | How sure IHP is about its predictions |
| **Environmental Adjustments** | Tweaks to account for weather, humidity, etc. |

---

## 🔗 Related Documentation

- **[Configuration Guide](CONFIGURATION.md)** - How to set up IHP
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues and solutions
- **[Architecture Guide](../ARCHITECTURE.md)** - For developers: How IHP is built

---

**Questions?** Check [Troubleshooting](TROUBLESHOOTING.md) or ask on [GitHub Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
