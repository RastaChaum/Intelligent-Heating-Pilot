# User Guide - Intelligent Heating Pilot

## Welcome to IHP!

**Intelligent Heating Pilot (IHP)** is a smart heating assistant for Home Assistant that learns how your heating system works and automatically starts heating at exactly the right time.

### What IHP Does

Instead of manually deciding when to turn on heating, IHP:

- ✅ **Learns** how fast your room heats
- ✅ **Calculates** the optimal start time
- ✅ **Triggers** heating automatically, through HACS Scheduler
- ✅ **Improves** predictions with each cycle

### What IHP Doesn't Do (Yet)

These features are planned for future versions:
- Setback optimization (deciding when to lower temperature)
- Occupancy-aware scheduling
- Multi-zone coordination
- Energy cost optimization

---

## 🚀 Quick Start (15 minutes)

### 1. Install IHP
Follow [Installation Guide](INSTALLATION.md)

### 2. Configure IHP
Follow [Configuration Guide](CONFIGURATION.md)

### 3. Learn How It Works
Read [How IHP Works](HOW_IT_WORKS.md) to understand:
- What learned heating slope is
- How heating cycles are detected
- How predictions are calculated

### 4. Monitor & Troubleshoot
Check [Troubleshooting Guide](TROUBLESHOOTING.md) if anything seems wrong

---

## 📚 Documentation Overview

| Document | For Whom | Read This If... |
|----------|----------|-----------------|
| **[Installation](INSTALLATION.md)** | First-time users | You need to install IHP |
| **[Configuration](CONFIGURATION.md)** | Setup users | You're setting up IHP for the first time |
| **[How It Works](HOW_IT_WORKS.md)** | Curious users | You want to understand what's happening behind the scenes |
| **[Troubleshooting](TROUBLESHOOTING.md)** | Users with issues | Something isn't working right |

---

## 🎯 Common Tasks

### Task: Verify IHP is working

**Steps:**
1. Go to Settings → Devices & Services
2. Find "Intelligent Heating Pilot"
3. Click on it to see the device
4. Should show several sensors with values
5. If no sensors, see [Troubleshooting](TROUBLESHOOTING.md)

### Task: Check what IHP learned

**Steps:**
1. Find your IHP device
2. Look for the "Global Learned Heating Slope" sensor (°C per hour)
3. Exactly 2.0 usually means no cycle is learned yet: that is the default value
4. The "Contextual Learned Heating Slope" sensor shows the slope learned for the next slot's hour, or *unknown* if that hour has no learned cycle yet

### Task: Understand the Dead Time sensor

**Steps:**
1. Find your IHP device
2. Look for "Dead Time" sensor (shows value in minutes)
3. This represents system lag before temperature starts changing
4. Higher values = slower response to heating commands

**What is Dead Time?**
- Time between when heating turns on and when temperature actually starts rising, measured as the time until the room is 0.2°C above its starting temperature
- IHP automatically learns this from your heating cycles
- Improves prediction accuracy for your system
- Until a dead time is learned (new device, after `reset_learning`, or with **Automatic Learning** disabled), the sensor shows the **Initial Dead Time** setting

### Task: See next heating plan

**Steps:**
1. Find your IHP device
2. Look for the "Anticipated Start Time" sensor
3. Shows when IHP will trigger heating next; "Next Schedule Time" shows the slot it is aimed at

### Task: Enable or disable IHP preheating

**Steps:**
1. Find your IHP device
2. Look for "IHP Preheating" switch
3. Turn OFF to disable automatic preheating (IHP continues learning but won't trigger heating)
4. Turn ON to re-enable automatic preheating

**Why disable?**
- 🎛️ You want manual control temporarily
- 👀 You want to monitor IHP's predictions without it taking action
- 🔧 You're testing or troubleshooting

**Note:** When disabled, IHP continues to learn and calculate—you'll still see predictions in sensors.

### Task: Change configuration

**Steps:**
1. Settings → Devices & Services
2. Find your Intelligent Heating Pilot
3. Click "Configure" on the device
4. Update entities or settings, click Submit
5. The device reloads automatically

## Related Documentation

- [Architecture Overview](../architecture/OVERVIEW.md)
- [Contributor Guide](../contributors/CONTRIBUTING.md)
- [Documentation Hub](../README.md)

---

## 💡 Tips & Best Practices

### ✅ Do This

- ✅ Use a [supported scheduler](CONFIGURATION.md#supported-schedulers): HACS Scheduler, with slots that set a temperature or a preset
- ✅ Let IHP run a few days before judging accuracy
- ✅ Monitor the "Global Learned Heating Slope" sensor (should stabilize)
- ✅ Check logs if behavior seems strange

### ❌ Don't Do This

- ❌ Don't disable scheduling right after IHP triggers (let it heat)
- ❌ Don't expect perfection on first cycle (learning takes time)
- ❌ Don't ignore error messages (they tell you what's wrong)

---

## ⚠️ When to Check the Logs

Check Home Assistant logs if:

- ❌ Heating never triggers
- ❌ Heating triggers at random times
- ❌ IHP integration won't load
- ❌ Any error messages appear

**To check logs:**
1. Settings → System → Logs
2. Search for `intelligent_heating_pilot`
3. Enable debug mode to see more details

---

## 🔗 Related Documentation

- **[CHANGELOG](../../CHANGELOG.md)** - What's new in this version?
- **[Architecture Guide](../architecture/OVERVIEW.md)** - For developers: How IHP is built
- **[CONTRIBUTING Guide](../contributors/CONTRIBUTING.md)** - How to contribute improvements
- **[Documentation Hub](../README.md)** - Full documentation map

---

## 🤔 Frequently Asked Questions

### Q: How many heating cycles before IHP is accurate?

**A:** Often from the start: right after setup, IHP reads your past heating cycles from the Home Assistant recorder history. Without usable history, it uses a default slope of 2.0 °C/h, which is not cautious: a slow room starts too late until its first cycles are learned. Each slot uses the slope learned for its own hour, so a slot gets accurate once a few preheats aimed at it have been learned.

### Q: What is the cycle cache and how does it help?

**A:** IHP caches detected heating cycles locally instead of repeatedly scanning Home Assistant's database. This means:
- ⚡ **Much faster** LHS calculations (~95% fewer database queries)
- 📈 **Longer history** retained (30 days by default vs. typical 7-10 day HA retention)
- 🎯 **Better accuracy** from more historical data

The cache automatically refreshes every 24 hours to include new cycles and removes old cycles beyond the retention period.

### Q: How do I tune cycle detection for my heating system?

**A:** You can configure how IHP detects heating cycles in the device settings:

**Common scenarios:**

- **Intermittent heating** (on/off frequently): Increase temperature threshold to 0.3-0.5°C
- **Fast-response systems** (heat pumps, electric): Lower minimum cycle duration to 1-3 minutes
- **Long heating cycles** (poorly insulated): Increase maximum cycle duration to 240-360 minutes
- **Micro-cutoffs/noise**: Increase minimum cycle duration to 10-15 minutes

See [Configuration Guide](CONFIGURATION.md#heating-cycle-detection-parameters) for detailed parameter descriptions.

### Q: Can I use IHP with multiple thermostats?

**A:** Yes! Create one IHP device per thermostat, each with its own name. Each learns independently. Do not create two IHP devices for the same thermostat: both would trigger its schedulers.

### Q: Which schedulers does IHP support?

**A:** Only two kinds, see [Supported Schedulers](CONFIGURATION.md#supported-schedulers):

- **HACS Scheduler** (`switch.schedule_*`): IHP computes the anticipated start **and** starts the heating. Each slot's action must be `climate.set_temperature` or `climate.set_preset_mode`, and the schedule must control this VTherm.
- **Native `schedule.*` helpers**: IHP only computes the anticipated start, with the VTherm comfort preset as target. It does not start the heating.

Other schedulers (automations, calendars, other scheduler integrations) are not read. Use the `calculate_anticipated_start_time` service with them.

### Q: Can I use IHP without a scheduler?

**A:** Yes, the scheduler is **optional**. When configured without a scheduler:

- ✅ IHP continues to **learn** your heating slope
- ✅ All learning sensors work normally
- ⚠️ Anticipation sensors show **"unknown"** (no scheduled events)
- ⚠️ IHP does **not auto-trigger** heating

**Use case**: Call the `calculate_anticipated_start_time` service in your own automations for dynamic scheduling (e.g., based on phone alarm, voice commands, calendar events).

See [Configuration Guide - Using IHP Without a Scheduler](CONFIGURATION.md#using-ihp-without-a-scheduler) for examples.

### Q: How do I use the calculation service?

**A:** Call `intelligent_heating_pilot.calculate_anticipated_start_time` in automations:

```yaml
action: intelligent_heating_pilot.calculate_anticipated_start_time
data:
  entity_id: sensor.living_room_anticipated_start_time
  target_time: "{{ states('sensor.phone_next_alarm') }}"
  target_temp: 21.0
response_variable: heating_calc
```

The service returns when to start heating, estimated duration, learned slope, and confidence level. Use these values to create smart, adaptive heating automations!

### Q: What happens if I don't have outdoor temperature sensor?

**A:** That's fine! The prediction does not use the outdoor temperature directly: the learned heating slope, computed from your recent heating cycles, already reflects recent weather. When a source is configured, IHP records the outdoor temperature of each heating cycle to prepare a future weather adjustment. If you have no outdoor sensor, you can select a `weather.*` entity instead.

### Q: Is IHP making my heating worse?

**A:** Unlikely. IHP only triggers your existing scheduler at calculated times. Your thermostat still controls the actual heating. If problems occur, disable IHP (uninstall integration) and check thermostat works normally.

### Q: Can I manually override IHP?

**A:** Yes! You have multiple options:

1. **Use the IHP Preheating switch** - Turn OFF to disable automatic preheating while keeping learning active
2. **Manual thermostat control** - You can manually turn on/off your thermostat anytime. IHP won't interfere.
3. **Switch off the HACS Scheduler** - IHP stops anticipating its slots

The switch is useful when you want temporary manual control but want IHP to continue learning in the background.

### Q: Where is IHP storing my data?

**A:** All learning data is stored locally on your Home Assistant instance. Nothing is sent to cloud or external services.

### Q: What happens when I go on vacation? Does IHP stop automatically?

**A:** With HACS Scheduler, yes: IHP stops when you switch the scheduler off or when its conditions aren't met. A native `schedule.*` helper cannot be switched off, but IHP never starts the heating for it anyway. Here's how it works with HACS Scheduler:

**When the scheduler is switched off (state = "off"):**
- IHP detects no upcoming timeslots
- Anticipation sensors return to `unknown`
- No heating will be triggered
- No action needed from you

**When scheduler conditions aren't met (e.g., vacation mode):**
- IHP calls `run_action` with `skip_conditions: false`
- The scheduler respects its own conditions (like `input_boolean.vacation`)
- If conditions fail, heating won't trigger, and IHP tries the next configured scheduler, if any
- A preheat starting the day before its slot (e.g. Sunday 23:00 for the Monday 05:00 slot of a Mon–Fri schedule) finds no slot to run that day: IHP retries the same scheduler at 00:01 before trying the next one
- IHP stays ready but inactive

**How IHP interacts with your system:**
- IHP does not set the VTherm itself to start preheating
- IHP triggers HACS Scheduler's `run_action` service
- The scheduler then controls VTherm based on its conditions
- This ensures all your existing automations and conditions work as expected

**For vacation mode:**
1. Set your thermostat to eco mode (optional)
2. Switch your HACS Scheduler off (turn its switch to "off"), or use a scheduler condition
3. IHP automatically becomes inactive
4. When you return, enable the scheduler
5. IHP resumes normal operation

Rest assured, you can go on vacation without any additional configuration!

---

## 📞 Getting Help

- 💬 **Questions?** Ask on [GitHub Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
- 🐛 **Found a bug?** Report on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)
- 📖 **Need more details?** Check [Troubleshooting Guide](TROUBLESHOOTING.md)

---

## 🎓 Next Steps

1. **👉 First time?** Start with [Installation](INSTALLATION.md)
2. **👉 Just installed?** Go to [Configuration](CONFIGURATION.md)
3. **👉 Want to understand it?** Read [How It Works](HOW_IT_WORKS.md)
4. **👉 Something wrong?** Check [Troubleshooting](TROUBLESHOOTING.md)

---

**Happy heating!** 🔥

_Intelligent Heating Pilot v0.7.1 - Documentation Last Updated: November 2026_
