# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/RastaChaum/Intelligent-Heating-Pilot?label=version&color=blue)](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/latest)
![Status](https://img.shields.io/badge/status-beta-yellow)

🇫🇷 [Version française](README.fr.md)

> **The Adaptive Brain for Your Thermostat, with Versatile Thermostat as the recommended companion**

A Home Assistant integration that learns your heating system and automatically starts heating at exactly the right time—no manual tuning required.

---

## What IHP Does

```text
📅 Next heating: 18:00 (target 21°C)
🧠 Learned slope: 2.3°C/hour
⏰ Start time: 16:42 (calculated automatically)
✅ Room reaches 21°C exactly at 18:00
```

IHP monitors your thermostat, learns how fast your room heats, and triggers your scheduler at the perfect moment so you arrive to a warm home—every time.

---

## ✅ Requirements

- **Home Assistant** 2026.2 or later
- **A `climate` entity to preheat**: use one IHP device per thermostat. **[Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)** is the recommended target and the best supported, but any `climate` entity works (see [what a generic climate must expose](docs/users/CONFIGURATION.md#using-a-climate-that-is-not-a-versatile-thermostat))
- **A supported scheduler**, for IHP to anticipate your slots:

| Scheduler | Anticipated start | IHP starts the heating |
| --- | --- | --- |
| [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) (`switch.schedule_*`) | ✅ | ✅ |
| [Climate Scheduler](https://github.com/kneave/climate-scheduler) | ✅ | ✅ |
| [ha-chauffage](https://github.com/armellarcier/ha-chauffage) (its *Next change* sensor) | ✅ | ✅ |
| Native `schedule.*` helper | ✅ | ⚙️ if you turn on direct control (or build your own automation) |
| Other schedulers (automations, calendars, other integrations) | ❌ | ❌ use the `calculate_anticipated_start_time` service |

The scheduler decides what happens and when; IHP decides how early, and applies the slot's own action (a preset or a temperature) to your thermostat a little before the slot. With HACS Scheduler, each slot's action must be `climate.set_temperature` or `climate.set_preset_mode`, on the VTherm of the IHP device. **[Supported schedulers in detail →](docs/users/CONFIGURATION.md#supported-schedulers)**

---

## ⚡ Quick Start

### 1. Install via HACS

```text
HACS → Integrations → ⋮ → Custom repositories
→ Add: https://github.com/RastaChaum/Intelligent-Heating-Pilot
→ Search "Intelligent Heating Pilot" → Download → Restart HA
```

**[Full installation guide →](docs/users/INSTALLATION.md)**

### 2. Configure

```text
Settings → Devices & Services → + Add Integration
→ Search "Intelligent Heating Pilot"
→ Select your thermostat + HACS Scheduler → Submit
```

**[Full configuration guide →](docs/users/CONFIGURATION.md)**

### 3. Let It Learn

- Right after setup, IHP learns from your past heating cycles in the Home Assistant recorder history
- Each new heating cycle refines the learned slope and dead time, hour by hour
- No manual intervention needed

**[How IHP works →](docs/users/HOW_IT_WORKS.md)**

---

## 🎯 Features

### Current

- ✅ **Smart Pre-heating** - Automatically calculates optimal start time based on learned heating performance
- ✅ **Dead Time Learning** - Accounts for system lag in temperature response for more accurate predictions
- ✅ **Enable/Disable Switch** - Toggle preheating on/off while maintaining learning data
- ✅ **Configurable Revert Threshold** - Active preheating is only canceled when anticipated start is pushed later by a configurable time delta
- ✅ **Cycle Detection** - Learns from real heating cycles, not thermostat slopes
- ✅ **Configurable Detection Parameters** - Fine-tune cycle detection for your heating system
- ✅ **Time-Contextual Learning** - Different heating speeds by time of day
- ✅ **HACS Scheduler Preheating** - Triggers the upcoming slot early, with the scheduler's conditions respected; several schedulers per device
- ✅ **Climate Scheduler and Native Schedules** - IHP applies the next node's or block's action to your thermostat itself (native schedules: turn on direct control, the preset or temperature comes from each block's data), and puts it back if the preheat is cancelled and nobody changed it meanwhile
- ✅ **Wake-up Sources** - Give a device your phone's next alarm (or any date-time entity): IHP preheats so the room is ready at that time, takes the target from your schedule if you want, and can put the thermostat back after it
- ✅ **Calculation Service** - `calculate_anticipated_start_time` for your own automations, with or without a scheduler
- ✅ **Outdoor Source** - Outdoor sensor or `weather.*` entity, recorded with each heating cycle
- ✅ **Incremental Cache** - Reduces HA database load for long-term learning
- ✅ **Any climate entity** - Versatile Thermostat v8+ is recommended and gets its extra capabilities (preset temperatures, load shedding awareness) detected automatically; other thermostats work too
- ✅ **Optimized Startup** - Lazy loading and smart filtering prevent HA watchdog timeouts
- ✅ **Vacation Mode Ready** - Stops automatically when the HACS Scheduler is switched off or its conditions block it

### Future Vision

- 🔮 Setback optimization (lowering the temperature before a comfort slot ends, using the room's inertia)
- 🔮 Occupancy-aware scheduling
- 🔮 Multi-zone coordination
- 🔮 Energy cost optimization

---

## 📚 Documentation

| For | Start Here |
| --- | --- |
| **New Users** | [User Guide](docs/users/USER_GUIDE.md) - Overview and quick navigation |
| **Installation** | [Installation Guide](docs/users/INSTALLATION.md) - HACS or manual setup |
| **Configuration** | [Configuration Guide](docs/users/CONFIGURATION.md) - Entity setup and options |
| **Understanding** | [How IHP Works](docs/users/HOW_IT_WORKS.md) - Cycle detection and prediction |
| **Issues** | [Troubleshooting](docs/users/TROUBLESHOOTING.md) - Common problems and fixes |
| **Contributors** | [Contributing Guide](docs/contributors/CONTRIBUTING.md) - Development workflow and standards |
| **Documentation Hub** | [docs/README.md](docs/README.md) - Full user, contributor, and maintainer docs |

**Quick Links:** [Changelog](CHANGELOG.md) · [Report Bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md) · [Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions) · [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)

---

## 💡 Key Concepts

**Learned Heating Slope** - How fast your room heats (°C/hour)

- Calculated from detected heating cycles, after the dead time
- Averaged over the cycles kept, globally and for each hour of the day
- Used to predict exact start time for next event

**Example:** To heat 3°C at 2°C/hour → 90 minutes, plus the dead time and a 5-minute margin ✅

**Vacation Mode** - No action needed!

- IHP automatically stops when you switch the HACS Scheduler off, or when its conditions (e.g. `input_boolean.vacation`) block it
- Resumes when you turn the scheduler back on
- Preserves learned data across vacation periods

---

Contributions welcome! Report bugs, suggest features, or submit code improvements.

**[Read Contributing Guide →](docs/contributors/CONTRIBUTING.md)**

For technical architecture: [Architecture Overview](docs/architecture/OVERVIEW.md)

For all long-form documentation: [Documentation Hub](docs/README.md)

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 👏 Acknowledgements

- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) by @jmcollin78
- [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) by @nielsfaber
- Home Assistant community

---

**⭐ If you find IHP useful, please star the project!**

[![Star History Chart](https://api.star-history.com/svg?repos=RastaChaum/Intelligent-Heating-Pilot&type=Date)](https://star-history.com/#RastaChaum/Intelligent-Heating-Pilot&Date)
