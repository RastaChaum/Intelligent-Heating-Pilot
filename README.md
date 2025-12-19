# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.4.2-blue)
![Status](https://img.shields.io/badge/status-beta-yellow)

> **The Adaptive Brain for Versatile Thermostat**

A Home Assistant integration that learns your heating system and automatically starts heating at exactly the right time—no manual tuning required.

---

## What IHP Does

```
📅 Next heating: 18:00 (target 21°C)
🧠 Learned slope: 2.3°C/hour  
⏰ Start time: 16:42 (calculated automatically)
✅ Room reaches 21°C exactly at 18:00
```

IHP monitors your VTherm, learns how fast your room heats, and triggers your scheduler at the perfect moment so you arrive to a warm home—every time.

---

## ⚡ Quick Start

### 1. Install via HACS

```
HACS → Integrations → ⋮ → Custom repositories
→ Add: https://github.com/RastaChaum/Intelligent-Heating-Pilot
→ Search "Intelligent Heating Pilot" → Download → Restart HA
```

**[Full installation guide →](docs/INSTALLATION.md)**

### 2. Configure

```
Settings → Devices & Services → + Add Integration
→ Search "Intelligent Heating Pilot"
→ Select VTherm + Scheduler → Submit
```

**[Full configuration guide →](docs/CONFIGURATION.md)**

### 3. Let It Learn

- First 5 cycles: conservative (starts early)
- After 20+ cycles: very accurate predictions
- No manual intervention needed

**[How IHP works →](docs/HOW_IT_WORKS.md)**

---

## 🎯 Features

### Current (v0.4.1)

- ✅ **Smart Pre-heating** - Automatically calculates optimal start time
- ✅ **Cycle Detection** - Learns from real heating cycles, not VTherm slopes
- ✅ **Time-Contextual Learning** - Different heating speeds by time of day
- ✅ **Incremental Cache** - Reduces HA database load for long-term learning
- ✅ **VTherm v8+ Compatible** - Works with latest Versatile Thermostat
- ✅ **Vacation Mode Ready** - Stops automatically when scheduler disabled

### Future Vision

- 🔮 Setback optimization
- 🔮 Occupancy-aware scheduling
- 🔮 Multi-zone coordination
- 🔮 Energy cost optimization

---

## 📚 Documentation

| For | Start Here |
|-----|-----------|
| **New Users** | [User Guide](docs/USER_GUIDE.md) - Overview and quick navigation |
| **Installation** | [Installation Guide](docs/INSTALLATION.md) - HACS or manual setup |
| **Configuration** | [Configuration Guide](docs/CONFIGURATION.md) - Entity setup and options |
| **Understanding** | [How IHP Works](docs/HOW_IT_WORKS.md) - Cycle detection and prediction |
| **Issues** | [Troubleshooting](docs/TROUBLESHOOTING.md) - Common problems and fixes |
| **Contributors** | [Contributing Guide](CONTRIBUTING.md) - Development and architecture |

**Quick Links:** [Changelog](CHANGELOG.md) · [Report Bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md) · [Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions) · [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)

---

## 💡 Key Concepts

**Learned Heating Slope** - How fast your room heats (°C/hour)
- Calculated from detected heating cycles (start temp → end temp)
- Refined over time with trimmed mean algorithm
- Used to predict exact start time for next event

**Example:** To heat 3°C at 2°C/hour → Start 90 minutes early ✅

**Vacation Mode** - No action needed!
- IHP automatically stops when scheduler disabled
- Re-enables when you turn scheduler back on
- Preserves learned data across vacation periods

---

## 🛠️ Services

Reset learning data if you modify your heating system:

```yaml
service: intelligent_heating_pilot.reset_learning
```

---

## 🤝 Contributing

Contributions welcome! Report bugs, suggest features, or submit code improvements.

**[Read Contributing Guide →](CONTRIBUTING.md)**

For technical architecture: [Architecture Documentation](ARCHITECTURE.md)

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
