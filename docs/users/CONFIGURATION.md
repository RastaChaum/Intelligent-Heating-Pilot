# Configuration Guide - Intelligent Heating Pilot

## Device Setup

### Step 1: Open Integration Settings

1. Go to **Settings** (⚙️) → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Intelligent Heating Pilot"** (or "IHP")
4. Select it from the list

### Step 2: Fill in Required Information

A configuration dialog will appear. Here's what you need:

| Field | Required? | What It Is | How to Find |
|-------|-----------|-----------|------------|
| **Name** | ✅ Yes | A friendly name for this IHP device; it also names the device and its entities. Each device needs its own name | Any name you want (e.g., "Living Room" gives `sensor.living_room_anticipated_start_time`) |
| **Thermostat** | ✅ Yes | The `climate` entity IHP preheats (Versatile Thermostat recommended) | Pick it from the list: every `climate` entity is offered. Use one IHP device per thermostat |
| **Scheduler Entities** | ⚠️ Optional | The schedulers that control this thermostat | Pick them from the list (e.g., `switch.schedule_heating`). See [Supported Schedulers](#supported-schedulers) below |

The scheduler list offers the `switch.*` and `schedule.*` entities that look like schedulers. If none is found, an entity picker accepting any `switch.*` or `schedule.*` entity is shown instead.

### Using a climate that is not a Versatile Thermostat

Versatile Thermostat is the recommended target: IHP detects what it publishes and uses it when present. Any other `climate` entity (a TRV, a generic thermostat, a heat pump…) can be selected and preheated if it exposes the standard attributes below.

| Attribute | Needed for | If missing |
|-----------|-----------|-----------|
| `current_temperature` | Everything | IHP cannot anticipate |
| `temperature` (the target) | Everything | IHP cannot anticipate |
| `hvac_mode` | Cycle detection | Cycles are not detected |
| `hvac_action` (`heating` / `idle`…) | **Learning** the heating slope | The thermostat is preheated, but IHP learns nothing from it and logs one warning. The default or configured slope is used |
| `preset_modes` | Slots that set a preset | See below |

**Presets.** Versatile Thermostat publishes the temperature behind each preset; a standard climate only lists its presets. For a slot that uses `climate.set_preset_mode`, or a native schedule block mapped to a preset, IHP needs to know the temperature:

1. Open the device's **Configure** form.
2. Tick **Map presets to temperatures after saving** (only offered when your thermostat lists presets but does not publish their temperatures).
3. Enter the temperature of each preset you use. A preset left empty is not anticipated.

IHP uses, in this order: the temperature the thermostat publishes, then your mapping, then the target of the thermostat while that preset is active. An unmapped preset is logged once as a warning, and its slot is not anticipated (a native schedule block falls back to 20 °C).

Versatile Thermostat-only capabilities (published preset temperatures, load shedding and safety mode awareness, the smoothed room temperature) are used when found and never required.

### Supported Schedulers

IHP does not work with every scheduler. What it can do depends on the scheduler type:

| Scheduler | Anticipated start computed | Heating started by IHP |
|-----------|---------------------------|------------------------|
| [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) switch (`switch.schedule_*`) | ✅ Yes | ✅ Yes, through the scheduler's own `run_action` |
| [Climate Scheduler](https://github.com/kneave/climate-scheduler) switch | ✅ Yes | ✅ Yes, IHP applies the node's action to the thermostat |
| Native Home Assistant `schedule.*` helper | ✅ Yes | ⚙️ Only if you turn on [direct control](#native-schedule-helpers) |
| Anything else (automations, calendars, `input_datetime`, other scheduler integrations) | ❌ No | ❌ No |

**The principle:** the scheduler decides what happens, when, and whether it happens. IHP only decides how early: at the anticipated start it applies the next slot's own action to the thermostat, and at the slot time the scheduler applies the same action, which changes nothing.

Without a supported scheduler, use the [`calculate_anticipated_start_time` service](#using-ihp-without-a-scheduler) in your own automations.

#### HACS Scheduler

IHP calls `scheduler.run_action` at the anticipated start so that the scheduler applies the upcoming slot early, with the scheduler's own conditions still checked. Restrictions:

- **The slot action must set a temperature.** IHP reads the target temperature from the slot's action, and only understands two actions:
  - `climate.set_temperature` with a `temperature`
  - `climate.set_preset_mode` with a preset (e.g. `comfort`), whose temperature IHP reads from the thermostat (Versatile Thermostat publishes it; for any other climate, map it in the **Configure** form)

  A slot whose action is anything else (`climate.set_hvac_mode`, a script, a scene, a preset whose temperature the thermostat does not expose and you did not map) has no target for IHP and is not anticipated.
- **The schedule must control the thermostat of this IHP device.** IHP does not check which entity the action targets. After triggering the slot, it waits up to 10 seconds for this thermostat to take the slot's temperature; if it does not, IHP treats the scheduler as blocked by its conditions.
- **A preheat that starts the day before its slot may start at 00:01.** `run_action` looks for the slot on the day it is called. On Sunday 23:00, the Monday 05:00 slot of a Mon–Fri schedule does not exist yet, so nothing heats. IHP retries the same scheduler at 00:01 on the slot's day and treats it as blocked only if that retry has no effect either. The room then starts heating later than anticipated. Schedules that run every day are not affected.
- **Only the next slot of each scheduler is anticipated.** If the next slot does not need heating (an eco slot, or a room already warm enough), nothing is preheated until that slot has passed, and the slot after it is anticipated then.
- **A scheduler switched off is ignored.** Switching it back on makes IHP use it again.
- **Several schedulers can be configured.** IHP anticipates the earliest upcoming slot among them. If that scheduler's conditions block it, IHP tries the next scheduler right away.

#### Climate Scheduler

IHP recognises a Climate Scheduler switch by the integration that registered it, not by its look (it imitates the HACS Scheduler attributes). At the anticipated start IHP applies the **next node's action to this device's thermostat itself**, with no extra automation:

- A node that sets a **temperature** is applied as a temperature; a node that selects a **preset** is applied as a preset.
- A node that switches the thermostat **off** is ignored, whatever temperature it carries. A "no change" node cannot be told apart from another: Climate Scheduler publishes it with the temperature it keeps, so IHP anticipates that temperature.
- A schedule that covers several thermostats gives each IHP device its own node action: only the thermostat of this device is touched.
- A switch that is off is ignored.
- Climate Scheduler applies a node when it starts, and again after a restart or an edit. If it undoes a preheat that way, IHP does not fight it: the slot is simply reached on time.
- A schedule that does not name its thermostats is taken as this device's thermostat.
- **Limit:** between the last node of the day and midnight, Climate Scheduler announces the first node of *today's* schedule instead of tomorrow's, which is wrong in its 5/2 and individual modes (after midnight it is right). IHP follows what the switch announces.

#### Native `schedule.*` Helpers

A native schedule does not say what its blocks mean: each block may carry free **data** that you filled in. IHP reads the **next block start** through the helper (Home Assistant 2025.3 or later), even while another block is running, so adjacent blocks are anticipated too. On an older Home Assistant, IHP reads only the helper's next event: nothing is anticipated while a block runs, block data is not available, and a driven schedule gets the fallback preset. A warning says so once.

By default IHP only **computes** the anticipated start, with the thermostat **comfort** preset temperature as target (20 °C if the comfort preset cannot be read), and does not start the heating.

To let IHP start the heating, turn on **Drive Native Schedules** in the device's **Configure** form. IHP then applies the next block's action to the thermostat at the anticipated start, read from the block's data:

| Option | Default | Meaning |
|--------|---------|---------|
| Drive Native Schedules | off | IHP applies the next block itself |
| Native Schedule Preset Key | `preset` | Data entry that holds a preset name |
| Native Schedule Temperature Key | `temperature` | Data entry that holds a target temperature |
| Native Schedule Fallback Preset | `comfort` | Preset applied when a block has neither entry |

A block with the data `preset: comfort` is applied as the comfort preset; with `temperature: 21`, as 21 °C. When a block holds both, the **preset is applied** and the temperature only feeds the anticipation. Without the opt-in, block data is not read and nothing changes for you.

- **A native schedule applies nothing by itself.** After a block ends, nothing puts the thermostat back to eco unless you have an automation for it.
- A native schedule cannot be switched off: IHP keeps anticipating it, during a vacation too.

#### What IHP Leaves Alone

When IHP drives your thermostat it first records its state, and it only puts that state back if nobody touched the thermostat meanwhile:

- If you or an automation change the preset or temperature during the preheat, IHP never overwrites it, restores nothing, and **does not apply that slot again**: your change stands until the slot.
- A thermostat you switch off is left off, and nothing is written to it.
- A cancellation a few minutes before the slot restores nothing, because the scheduler is about to apply the same action.
- After a Home Assistant restart IHP picks up the preheat in progress; if its scheduler cannot answer yet, it waits and asks again.

#### When IHP Applies a Temperature: the Manual Override Duration

Versatile Thermostat has an optional **manual override duration** (advanced configuration, off by default). When it is set, VTherm treats any `set_temperature` call as a temporary manual change: it keeps that temperature for that many minutes, then goes back to the preset it had before.

IHP cannot tell VTherm that its call is not a manual change, so with this option on, a slot that sets a **temperature** can be undone by VTherm after the configured duration: before the slot if the preheat is longer, or in the middle of the slot otherwise. Slots that select a **preset** are not affected. If your schedules use temperatures, either leave the option off, or use presets in your slots.

### Step 3: (Optional) Add Environmental Sensors

These sensors help IHP make better predictions but are **not required**:

| Sensor | Purpose | Example |
|--------|---------|---------|
| **Indoor Humidity Sensor** | Adjusts calculations for moisture impact | `sensor.living_room_humidity` |
| **Outdoor Temperature Sensor** | Recorded with each heating cycle; not used in the prediction yet | `sensor.outdoor_temperature` or `weather.home` |
| **Outdoor Humidity Sensor** | Monitored; not used in the prediction yet | `sensor.outdoor_humidity` or `weather.home` |
| **Cloud Coverage Sensor** | Adjusts for solar gain | `sensor.cloud_coverage` or `weather.home` |

> **Weather entities:** The outdoor temperature, outdoor humidity and cloud coverage fields accept either a dedicated sensor or a `weather.*` entity. For a weather entity, IHP reads its `temperature`, `humidity` and `cloud_coverage` attributes, so one weather entity can feed all three fields. Temperatures in °F or K are converted to °C.

### Step 4: Complete Setup

1. Click **Submit**
2. IHP will initialize and start monitoring your heating system
3. You should see a new device named after the **Name** you entered

✅ **Setup complete!** IHP is now running. Continue reading to understand what to expect.

---

## After Installation: What to Expect

### Learning Starts From Your History

IHP does not wait for new heating cycles: right after setup, it reads the heating cycles of your VTherm from the Home Assistant recorder history, over the **Slope Data Retention** period (limited to what the recorder still keeps). This runs in the background and can take a few minutes.

- 📊 If cycles are found, the **Global Learned Heating Slope** and **Dead Time** sensors show learned values as soon as the extraction ends
- 📊 Until then, or if the history holds no usable cycle, the default slope of 2.0 °C/h and the **Initial Dead Time** are used
- 📈 Each new heating cycle refines the values; a new cycle is picked up at the latest by the daily refresh
- 🕐 The **Contextual Learned Heating Slope** stays *unknown* for an hour of the day until a cycle has been learned for it

### What IHP Does Automatically

Once configured, IHP operates automatically:

1. **Monitors** your schedulers for the next slot
2. **Learns** how your heating system performs
3. **Calculates** when to start heating to reach the target temperature exactly on time
4. **Applies** the slot early: through HACS Scheduler's own `run_action`, or by applying the slot's action to your thermostat (Climate Scheduler, and native schedules when you turn on direct control)

**You don't need to do anything—IHP works in the background!**

---

## Wake-up Sources (Alarm, Date-Time Entity)

A **wake-up source** is an entity that holds a point in time: your phone's next alarm, a date-time helper, a date-time entity. IHP preheats so that the room reaches the target temperature **at that time**, using the heating speed it learned, and applies the target to your thermostat itself. You do not need a scheduler or an automation.

### Setting One Up

1. Open the device's **Configure** screen and tick **Manage wake-up sources after saving**, then save.
2. In the menu, choose **Add a source** and fill in:

| Field | What it does |
|-------|--------------|
| **Entity holding the time** | A `sensor` with the *timestamp* device class (such as the phone's next-alarm sensor), a `datetime` entity, or an `input_datetime` with both date and time. A date alone or a time alone is refused: it does not say when. |
| **Target preset** / **Target temperature** | What to apply and reach. When both are given, the preset is applied and the temperature is the one IHP heads for in its calculation. |
| **Take the target from the schedule** | Only offered when the device has a scheduler. See below. |
| **Ignore times further than (hours)** | Default 24. A time further away is ignored, so a distant alarm never starts a preheat by accident. |
| **Keep the target after the time (minutes)** | Optional. After this long, IHP puts the thermostat back in its earlier state. 0 leaves the thermostat as it is. |

3. **Save and close**. A device can have several sources; each source belongs to one device.

### How the Deadlines Combine

IHP picks the **earliest valid deadline** among your schedulers and your wake-up sources. There is no priority setting:

- An alarm **earlier** than the next schedule slot becomes the next deadline; once it has passed, IHP goes back to the schedule.
- An alarm **later** than the next schedule slot changes nothing: the schedule slot is still the next deadline.
- If a schedule slot and an alarm fall at the same minute, the schedule wins, so a single target applies.

> **IHP cannot stop a scheduler.** A scheduler applies its own slots whatever IHP does. To keep the room cold for a late alarm, either **disable or add a condition to the schedule** on those days, or use **only a wake-up source and no scheduler** on that device. IHP then drives the thermostat by itself.

### Where the Target Comes From

- **Fixed target** (the default): the preset or temperature you gave.
- **From the schedule**: IHP takes the target of the schedule slot that **follows** the wake-up time (an alarm at 05:30 before a 07:00 comfort slot heads for the comfort target), but **never lower than the slot already in effect** at that time (an alarm at 08:00 during a comfort block that ends at 09:00 keeps the comfort target). Your fixed target is the fallback when the schedule cannot tell.

What the schedule can tell depends on the scheduler:

| Scheduler | Slot in effect | Slot that follows |
|-----------|----------------|-------------------|
| Native `schedule.*` (Home Assistant 2025.3+) | ✅ | ✅ |
| HACS Scheduler | ❌ | ✅, once no other slot lies between now and the wake-up time |
| Climate Scheduler | ❌ | ✅, once no other slot lies between now and the wake-up time |

When only one slot is known, IHP uses it only if its temperature is **higher** than your thermostat's current target; otherwise it falls back to the fixed target. With HACS Scheduler and Climate Scheduler, giving a fixed target as well is therefore recommended.

### What Happens Around the Wake-up Time

- The target is applied at the anticipated start, as a preset when you chose a preset, as a temperature otherwise. IHP never changes the thermostat's heating mode, and does nothing if it is switched off.
- A **snooze** or an edited alarm that moves the deadline by less than the **Preheating Revert Time Delta** (15 minutes by default) is followed without putting the thermostat back in between; a larger move cancels the preheat and starts it again for the new time. A **closer** alarm takes over a preheat for a later slot without putting the thermostat back in between.
- If you change the thermostat yourself, IHP does not apply the target again over your change.
- If the alarm is **removed or dismissed** before its time, the preheat is cancelled and the thermostat is put back as it was, unless you changed it.
- With a **hold**, the earlier state is put back that long after the wake-up time, unless you changed it or a schedule slot of the same device comes first: the schedule then owns the setting and IHP restores nothing.
- Preheats driven by a wake-up source are learned from like any other.

---

## Using IHP Without a Scheduler

IHP can be used without a scheduler, or with a scheduler it does not start (a native `schedule.*` helper without direct control). This is useful for:

- 🤖 **Dynamic scheduling** based on external triggers (e.g., calendar events) — for a smartphone alarm or any date-time entity, see [Wake-up Sources](#wake-up-sources-alarm-date-time-entity)
- 🔧 **Custom automations** that calculate start times programmatically
- 📱 **Voice-controlled** heating schedules
- 🧪 **Testing** IHP's prediction capabilities

### What Happens Without a Scheduler?

When no scheduler is configured:

- ✅ IHP continues to **learn** from your heating cycles
- ✅ The **Global Learned Heating Slope** and **Dead Time** sensors update normally
- ⚠️ Anticipation sensors show **"unknown"** (no scheduled events to anticipate)
- ⚠️ IHP does **not automatically trigger** heating (you control this via automations)

### Using the Calculation Service

Without a scheduler, you can use the **`calculate_anticipated_start_time`** service in your own automations:

**Example: Wake-up heating based on phone alarm** (for the alarm alone, a [wake-up source](#wake-up-sources-alarm-date-time-entity) needs no automation)

```yaml
alias: "Dynamic Wake-up Heating"
mode: restart
triggers:
  - trigger: state
    entity_id: sensor.phone_next_alarm
actions:
  # Calculate when to start heating
  - action: intelligent_heating_pilot.calculate_anticipated_start_time
    data:
      entity_id: sensor.living_room_anticipated_start_time
      target_time: "{{ states('sensor.phone_next_alarm') }}"
      target_temp: 21.0
    response_variable: heating_calc

  # Wait until the calculated start time
  - delay:
      seconds: "{{ [0, (as_datetime(heating_calc.anticipated_start_time) - now()).total_seconds()] | max }}"

  # Start heating
  - action: climate.set_temperature
    target:
      entity_id: climate.living_room
    data:
      temperature: 21.0
```

**Service Parameters:**

| Parameter | Required? | Description | Example |
|-----------|-----------|-------------|---------|
| `entity_id` | ✅ Yes | Any IHP sensor of the device (to identify it) | `sensor.living_room_anticipated_start_time` |
| `target_time` | ✅ Yes | When you want target temperature reached | `"2024-01-15 07:00:00"` or template |
| `target_temp` | ⚠️ Optional | Desired temperature (defaults to VTherm's current target) | `21.0` |

**Service Response:**

The service returns calculation results visible in Developer Tools:

```yaml
anticipated_start_time: "2024-01-15T06:27:00+01:00"
target_time: "2024-01-15T07:00:00+01:00"
target_temp: 21.0
current_temp: 18.5
estimated_duration_minutes: 33.0
learned_heating_slope: 2.1
confidence_level: 0.9
```

When IHP cannot calculate (no current temperature, for instance), `anticipated_start_time`, `estimated_duration_minutes` and `confidence_level` are `null`.

**Use these values in your automations** to create intelligent, adaptive heating schedules!

---

## Modifying Configuration

Need to change entities or settings after setup?

1. Go to **Settings** → **Devices & Services**
2. Open **Intelligent Heating Pilot**
3. Click **Configure** on the device you want to change
4. Update the entities or settings
5. Click **Submit**

The device reloads automatically. The **Name** cannot be changed there: rename the device from its device page.

---

## Advanced Configuration (Optional)

### Initial Dead Time

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Initial Dead Time** | 0 min | 0–60 min | Seed value for dead time before learning begins |

When to use: If you know your heating system has a significant startup lag (e.g., hydronic radiators that take 2-3 minutes to warm up), set this to speed up initial learning accuracy. IHP will refine this value automatically after each heating cycle.

**Example:** If your boiler takes 2 minutes to start heating the room, set this to 2 minutes for better initial predictions.

---

### Automatic Learning

| Setting | Default | Description |
|---------|---------|-------------|
| **Automatic Learning** | Enabled | When enabled, IHP learns the dead time from heating cycles. When disabled, the **Initial Dead Time** is always used. The heating slope is learned in both cases |

When to disable: During testing or when you want to freeze the dead time for a period while evaluating IHP's behavior with a fixed value.

---

### Recorder Extraction Period

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Recorder Extraction Period** | 7 days | 1–30 days | Size of each batch when extracting recorder history |

This controls how the initial recorder extraction is chunked. Smaller values = lighter database load per batch (good for low-power hardware like Raspberry Pi), but more total batches. Larger values = fewer batches (faster total extraction on powerful hardware).

**Recommended values:**
- **Low-power hardware (Raspberry Pi, HA Green)**: 3–5 days
- **Standard hardware (NUC, mini PC)**: 7–14 days
- **Powerful hardware**: 14–30 days

---

### Safety Shutoff Grace Period

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Safety Shutoff Grace Period** | 10 min | 0–30 min | How long IHP waits before closing a cycle after an unexpected heating stop |

When heating stops unexpectedly (e.g., safety protection, frost mode), IHP waits this long. If heating resumes, the interruption is ignored and the cycle continues. If not, the cycle closes.

The same delay applies to Versatile Thermostat **load shedding** (`power` preset) and to **target drops**, such as a window or a door opened for a couple of minutes: an interruption shorter than this delay does not split the preheat, which is learned as one cycle. A longer one ends the cycle when it started; after a load shedding, that cycle is not learned.

**When to adjust:**
- **Set lower (0–2 min)**: For systems that stop cleanly with no safety interruptions. With 0, every load shedding ends the cycle
- **Keep it above your load sheddings and brief openings**: Versatile Thermostat usually sheds the load for 1–3 minutes; the default 10 minutes covers them, and a window opened to air the room for longer is not bridged
- **Set higher (15–20 min)**: For boilers with long safety cycle lockouts or heat pumps with regular defrost cycles

---

### Preheating Revert Time Delta

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Preheating Revert Time Delta** | 15 min | 1–60 min | Minimum postponement required to cancel an active preheating and reschedule |

This setting controls how IHP reacts when anticipation is recalculated while preheating is already active.

**Current behavior:**
- IHP cancels active preheating only when the newly calculated anticipated start is pushed later by at least this threshold and is still in the future; a timer then restarts preheating at the new start
- If the new anticipated start moves earlier, IHP keeps active preheating running
- If the postponement is below threshold, IHP keeps active preheating running

**When to adjust:**
- **Lower (5–10 min)**: More reactive to schedule shifts, but may increase cancel/reschedule churn
- **Higher (20–30 min)**: More stable behavior, but less reactive to moderate postponements

---

### Data Retention Settings

IHP caches heating cycles for performance and a longer learning history.

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Slope Data Retention** | 30 days | 7–90 days | How long to keep cached heating cycles |

**Recommended Values:**
- **7 days**: Matches typical HA recorder retention, minimal history
- **30 days** (default): Optimal balance of learning quality and storage
- **90 days**: For detailed historical analysis and seasonal patterns

**When to Change:**
- ✅ **Increase** if you want longer learning history for seasonal accuracy
- ⚠️ **Decrease** if disk space is very limited (not recommended)

**What This Affects:**
- Cycle Cache: Heating cycles older than this are automatically pruned
- Learning History: More retention = better slope calculations
- Storage: Longer retention uses slightly more disk space (minimal)

**Initial Recorder Extraction:**

When you first configure IHP or increase the **Slope Data Retention** setting, IHP performs **progressive, batched extraction**:

- Extraction is split into `task_range_days`-day periods (default: 7 days, configurable 1-30 days)
- Each period is processed sequentially with brief pauses between batches
- Multiple IHP instances are serialized via RecorderAccessQueue — they don't compete for the recorder simultaneously
- Expected processing time: approximately **1-2 minutes per week of history** on typical hardware
- Processing happens **in the background** — HA and IHP sensors remain responsive

**Factors affecting processing time:**
- Higher **Slope Data Retention** = more history to extract = longer total time
- Smaller **Recorder Extraction Period** = more batches but lighter load per batch
- Slower hardware (e.g., Raspberry Pi, Home Assistant Green) = longer processing time

**Recommendation**: If you experience slowness, consider:
- Setting **Recorder Extraction Period** to 3–5 days (if on low-power hardware)
- Reducing **Slope Data Retention** to 30 days (default) or lower
- Allowing the initial extraction to complete before making other configuration changes

### Heating Cycle Detection Parameters

Fine-tune how IHP detects and processes heating cycles for the Learned Heating Slope calculation.

#### Temperature Detection Threshold

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Temperature Detection Threshold** | 0.2°C | 0.1 - 1.0°C | Temperature difference to detect cycle start/end |

**When to Adjust:**
- 🔻 **Lower (0.1°C)**: For heating systems with subtle temperature changes or high-precision thermostats
- 🔺 **Higher (0.3-0.5°C)**: For systems with frequent micro-cutoffs or intermittent heating
- ⚠️ **Too low**: May detect false cycles from sensor noise
- ⚠️ **Too high**: May miss short heating cycles

#### Cycle Duration Filters

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Minimum Cycle Duration** | 5 minutes | 1 - 30 min | Shortest valid heating cycle |
| **Maximum Cycle Duration** | 300 minutes (5h) | 15 - 360 min | Longest valid heating cycle |

**When to Adjust:**

**Minimum Duration:**
- 🔻 **Lower (1-3 min)**: For fast-response heating systems (electric radiators, heat pumps)
- 🔺 **Higher (10-15 min)**: For systems with frequent switching noise
- ⚠️ **Too low**: Includes micro-cycles (noise) in learning data
- ⚠️ **Too high**: May exclude legitimate short heating cycles

**Maximum Duration:**
- 🔻 **Lower (120-180 min)**: For well-insulated homes or powerful heating systems
- 🔺 **Higher (240-360 min)**: For poorly insulated spaces, weak heating systems, or underfloor heating whose preheats last more than 5 hours
- ⚠️ **Too low**: May exclude long but valid heating cycles: a cycle longer than this setting is not learned at all, and the slowest preheats are the ones that teach IHP to start earlier
- ⚠️ **Too high**: May include abnormal cycles from sensor malfunctions

#### Cycle Split Duration (Advanced)

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Cycle Split Duration** | 0 (disabled) | 0 - 120 min | Split long cycles into sub-cycles for ML (0 = disabled) |

**When to Enable:**
- ✅ **Planning to use ML mode** (future feature): Increases training data samples
- ✅ **Very long heating cycles** (>2 hours): Provides more granular learning
- ❌ **Simple mode only**: Keep disabled for simplicity

**Recommended Values:**
- 30 minutes: Good balance for most systems
- 60 minutes: For very long heating cycles
- Disabled (0): For simple mode users

**How cycles are split:** the heating phase, after the dead time, is cut into periods of this duration. The first sub-cycle also covers the dead time, so the dead time is still learned, and every sub-cycle gets the heating slope of the whole heating phase. A cycle whose heating phase is not longer than this duration is not split.

---

### How to Modify Advanced Settings

1. Go to **Settings** → **Devices & Services**
2. Open **Intelligent Heating Pilot**
3. Click **Configure** on the device
4. Scroll down to the settings below the entities
5. Adjust parameters based on your heating system
6. Click **Submit**

**Tip**: Start with defaults and only adjust if you notice issues with cycle detection in the logs.

### Disabling Optional Sensors

If you don't have certain sensors and don't want to see warnings:

1. Leave those fields empty in configuration
2. IHP will skip those calculations (no performance impact)

### Using Multiple Heating Zones

You can configure multiple IHP instances—one per VTherm:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** again
3. Configure a **new device** with another name and a different VTherm entity
4. Each device learns independently and triggers its own schedulers

---

## Entities Created by IHP

After configuration, IHP creates these entities on your device:

### Control Switch

| Switch | What It Does | Default State |
|--------|-------------|--------------|
| **IHP Preheating** | Enable/disable intelligent preheating | ON (enabled) |

**When Enabled (ON):**
- ✅ IHP triggers heating at calculated anticipation time
- ✅ Learning and calculations continue normally
- ✅ All sensors update as expected

**When Disabled (OFF):**
- ❌ IHP does NOT trigger heating early: your scheduler applies its slots at their normal time
- ✅ Learning continues (heating cycles still detected)
- ✅ Calculations continue (predictions still shown in sensors)
- ✅ You can monitor what IHP would do without it taking control

**Use Case:** Temporarily disable preheating during manual heating control, or when you want to monitor IHP's predictions without automatic intervention.

### Main Sensors

| Sensor | What It Shows | Updated |
|--------|--------------|---------|
| **Anticipated Start Time** | When heating will start (also available as **Anticipated Start Time (HMS)**, a plain time) | Every update cycle |
| **Next Schedule Time** | Time and target of the next heating event (also available as **Next Schedule Time (HMS)**) | Every schedule change |
| **Global Learned Heating Slope** | How fast your room heats (°C/hour), all hours combined | Every heating cycle |
| **Contextual Learned Heating Slope** | Slope learned for the hour nearest to the next slot (a 6:45 slot uses 7:00, shown in the `scheduled_hour` attribute); *unknown* until that hour is learned (the global slope is used meanwhile) | Every heating cycle |
| **Dead Time** | System delay in temperature response (minutes) | Every heating cycle |
| **Prediction Confidence** | An indication of how reliable the prediction is (%), see [Confidence Levels](HOW_IT_WORKS.md#-confidence-levels) | Every update cycle |

---

## Configuration Checklist

Before moving forward, verify:

- [ ] IHP appears in integrations
- [ ] A thermostat (`climate` entity) selected
- [ ] A HACS Scheduler configured (optional — required for automatic preheating)
- [ ] New sensors appear on your IHP device
- [ ] No error messages in logs

✅ **All checked?** Great! Now read [How IHP Works](HOW_IT_WORKS.md) to understand what's happening.

---

## Troubleshooting Configuration

### My thermostat is not in the list

**Solution:**
- Every `climate` entity is offered. If yours is missing, check that its integration is loaded and that the entity exists in Developer Tools → States

### "This integration is already configured"

**Solution:**
- Another IHP device already has this **Name**. Choose another name

### My scheduler is not in the list

**Solution:**
1. Verify the HACS Scheduler component is installed (or that your `schedule.*` helper exists)
2. Create at least one schedule that controls this VTherm
3. Verify its entity exists in **Developer Tools** → **States** (`switch.schedule_*`)
4. Open the IHP device's **Configure** form again

### IHP won't save configuration

**Solution:**
- Check Home Assistant logs for error details
- Ensure all required fields are filled
- Try reconfiguring from scratch
- If still failing, report on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)

---

**Next:** Go to [How IHP Works](HOW_IT_WORKS.md) to understand heating cycle detection and prediction logic
