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
   - Duration = end time − start time (minus dead time, see below)
   - Cycle slope = (temperature gain ÷ effective duration hours)
4. **Apply filters**: reject cycles with non-positive slopes and very short effective heating windows
5. **Average the slopes** across filtered cycles to produce the current LHS.

### Two Types of LHS

IHP uses two complementary approaches:

**Global LHS** — Simple average of ALL positive-slope cycles regardless of time of day
- Used as a fallback when no contextual data is available
- Represents your system's "typical" heating performance

**Contextual LHS** — Per-hour-of-day averages (e.g., cycles starting at 6am average separately from 9pm)
- More accurate because heating behavior varies by time (thermal mass, occupancy patterns, outdoor conditions)
- IHP uses contextual LHS when available for the current hour, falls back to global LHS if insufficient data

**Result:** More precise predictions as you use IHP throughout different times of day

### Important: Dead Time in Slope Calculations

When calculating a cycle's slope, IHP excludes the **dead time** (system startup lag) from the duration. Here's why:

```
Total cycle: 60 minutes
Dead time: 5 minutes (system ramps up, no temperature change)
Effective heating duration: 55 minutes

Cycle slope = temperature_gain / (55 minutes / 60)
NOT: temperature_gain / 60 minutes
```

This makes the slope more accurate by only counting the time when the room was actually heating.

### Filters Applied Before LHS Calculation

Before a cycle contributes to LHS:

1. **Non-positive slope filter**: Cycles where temperature didn't rise (or fell) are discarded — they contain no useful heating data
2. **Minimum effective duration filter**: Cycles whose effective heating window (after subtracting dead time) is too short are rejected
   - Why? When dead time ≈ total duration, the slope formula amplifies noise by orders of magnitude (e.g., 100,000°C/h)
   - Default threshold: 5 minutes of effective heating required
   - Example: A 6-minute cycle with 5-minute dead time has only 1 minute effective duration → rejected

### Cycle Cache: Performance Optimization

**New in v0.4.0+**: IHP uses an **incremental cycle cache** with progressive extraction to optimize performance and data retention.

**How It Works:**

1. **Progressive Extraction**: Rather than loading the entire recorder history at once, IHP extracts the full retention window in batches (default: 7-day periods, configurable via `task_range_days`)
2. **Sequential Batching**: Each batch is processed with brief pauses between, preventing database overload
3. **RecorderAccessQueue**: A global FIFO serializer prevents multiple IHP instances from querying the recorder simultaneously — essential for multi-zone setups to avoid OOM and watchdog timeouts
4. **Startup Staggering**: Each IHP instance adds a deterministic jitter delay so devices don't all start querying at the same time
5. **Lazy LHS Loading**: At startup, only the current hour's contextual LHS is loaded into memory; other 23 hours are loaded on-demand when first requested
6. **Automatic Refresh**: After initial extraction, new cycles are extracted every 24 hours (incremental updates only)
7. **Automatic Pruning**: Old cycles beyond retention period (default: 30 days) are removed

**Benefits:**
- ⚡ **Dramatic query reduction**: ~95% fewer database hits after initial extraction
- 📈 **Longer retention**: Keeps 30 days of cycles even if HA recorder retention is only 7-10 days
- 🚀 **Better learning**: More historical data = more accurate slope calculations
- 💾 **Persistent**: Cache survives Home Assistant restarts
- 🔄 **Multi-zone safe**: RecorderAccessQueue serialization prevents conflicts

**Expected Processing Time:**
- Initial extraction: approximately **1-2 minutes per week of history** on typical hardware
- Subsequent updates: only new data, much faster
- Processing happens **in the background** — HA and IHP sensors remain responsive

**Configuration:**
- Cache retention period: `data_retention_days` (default: 30 days)
- Extraction batch size: `task_range_days` (default: 7 days, range 1-30)

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

A heating cycle **ends** when one of these conditions is met:

1. **Heating mode is disabled** (`hvac_mode` no longer in `heat`, `heat_cool`, or `auto`, or the entity state becomes falsy)
2. **Room reached target**: indoor temperature is at or above `(target - delta)`, with delta defaulting to **0.2°C**

However, **brief heating interruptions** (< 10 minutes by default) do NOT immediately end the cycle:

**Safety Shutoff Grace Period**: When heating stops unexpectedly (e.g., safety shutoff, frost protection mode), IHP waits up to **10 minutes** (configurable, default 10 min) before closing the cycle. If heating resumes within this window, the interruption is absorbed and the cycle continues.

**Why?** Brief safety interruptions cause extreme slopes (100,000+ °C/h) if treated as separate micro-cycles. The grace period prevents these spurious learning events.

**Example Scenarios:**

| Scenario | What Happens |
|----------|--------------|
| Natural completion | Room hits target → End detected immediately |
| Scheduler or manual stop | Mode switches off → End detected immediately |
| Safety shutoff (brief, <10 min) | Mode stops → Grace period starts; if mode resumes within 10 min → interruption absorbed, cycle continues |
| Safety shutoff (extended, >10 min) | Mode stops → Grace period expires after 10 min → Cycle closes at the moment grace started |
| Early comfort | Target lowered while heating | Mode may stay on; end triggers when room is within 0.2°C of the new target |

### Why These Rules?

The current logic favors **quick detection** for natural completions and manual stops, but protects against false micro-cycles caused by brief safety interruptions. This keeps slope calculations aligned with actual heating performance rather than sensor noise or transient protection events.

---

## 🧮 Prediction Algorithm

Once IHP has learned the heating slope and dead time, it predicts when heating should start.

### The Calculation

**New in v0.6.0**: The prediction formula now includes dead time for more accurate predictions.

```
Anticipation Time (minutes) = Dead Time + (Temperature Difference / Learned Slope) × 60

Where:
- Dead Time = System lag before temperature starts rising (minutes)
- Temperature Difference = Target Temp - Current Temp (°C)
- Learned Slope = °C per hour (learned from heating cycles)
```

**Example:**
```
Need to heat: 3°C (from 18°C to 21°C)
Learned Slope: 2.0°C/hour
Dead Time: 1.5 minutes (system takes 1.5 minutes to respond)
Anticipation Time = 1.5 + (3 / 2.0) × 60 = 1.5 + 90 = 91.5 minutes
```

So IHP will trigger heating **91.5 minutes before the scheduled time** (accounting for the 1.5-minute delay).

### What is Dead Time?

**Dead Time** is the delay between when your heating system turns on and when indoor temperature actually starts rising. It accounts for:

- **Heat distribution delay**: Time for warm air to reach the temperature sensor
- **Thermal inertia**: Building elements warming up before affecting room temperature
- **System latency**: Time for boiler/heat pump to ramp up
- **Sensor response**: Temperature sensor accuracy and measurement lag

IHP automatically learns dead time from your heating cycles and refines it over time, similar to how it learns the heating slope.

### Environmental Adjustments

The basic calculation is then **adjusted** based on real-world conditions:

#### 1. **Outdoor Temperature Effect**

Colder outdoor air = **More heat loss** = **Need to heat longer**

```
Adjustment Factor = 1.0 + (20°C - outdoor_temp) × 0.05

Examples:
- Outdoor temp 20°C: factor = 1.0 (no adjustment)
- Outdoor temp 0°C: factor = 2.0 (heat twice as long)
- Outdoor temp -10°C: factor = 2.5 (heat 2.5× longer)
```

#### 2. **Humidity Effect**

Higher humidity = **Less efficient heating** = **Need to heat longer**

```
Adjustment Factor = 1.0 + (humidity - 50%) × 0.002

Examples:
- Humidity 50%: factor = 1.0 (neutral reference)
- Humidity 80%: factor = 1.06 (heat 6% longer)
- Humidity 20%: factor = 0.94 (heat 6% faster)
```

#### 3. **Solar Gain (Cloud Coverage)**

Clear sky = **Solar heat gain** = **Might heat faster**

```
Adjustment Factor = 1.0 - (100 - cloud_coverage%) × 0.001

Examples:
- Cloud coverage 100%: factor = 1.0 (no solar gain)
- Cloud coverage 0% (clear sky): factor = 0.9 (heat 10% faster)
- Cloud coverage 50%: factor = 0.95 (heat 5% faster)
```

### Safety Bounds

IHP applies **minimum and maximum limits** to predictions to stay reasonable:

| Limit | Value | Reason |
|-------|-------|--------|
| **Minimum Anticipation** | 10 minutes | Don't trigger too early if slope is very high |
| **Maximum Anticipation** | 6 hours (360 minutes) | Don't trigger too early for slow heating |

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
      ├─ Prevents overshooting (stops early if approaching target)
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
