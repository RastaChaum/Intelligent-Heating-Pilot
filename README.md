# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.3.0-blue)
![Status](https://img.shields.io/badge/status-beta-yellow)

**The Adaptive Brain for Versatile Thermostat**

IHP is a smart Home Assistant integration that learns how your heating system works and automatically starts heating at exactly the right time—no manual tuning required.

> [!NOTE]
> **🚀 VERSION 0.3.0 🚀** - Stable beta with comprehensive documentation
> - ✅ Core heating prediction features stable and tested
> - 📚 Complete user documentation (Installation, Configuration, How It Works)
> - 🤝 Clear contributor guidelines
> - 📊 3-5 heating cycles for good accuracy, 20+ for excellence
> 
> **[👉 START HERE: User Guide →](docs/USER_GUIDE.md)**

The ultimate vision of IHP is to act as the complete "Flight Controller" for your heating system, making autonomous decisions regarding when to heat, how long to heat, and what the optimal temporary setpoint should be, based on Adaptive Learning and real-time inputs.

The first release (V0.3.0) delivers the foundational feature: **Smart Predictive Pre-heating**. It continuously learns from your heating system to predict the exact moment to start heating, improving with each cycle.

## 🌟 Current Features (V1: Adaptive Start)

- **Smart Predictive Pre-heating**: Automatically determines when to start heating to reach the target temperature at the exact scheduled time.
- **Statistical Learning**: Continuously learns from VTherm's thermal slope observations using robust statistical aggregation (trimmed mean).
- **Multi-Factor Awareness**: Adapts calculations based on humidity and cloud coverage.
- **Thermal Slope Aggregation**: Collects and refines heating slope data from your VTherm to improve prediction accuracy over time.
- **Seamless Integration**: Works with Versatile Thermostat (VTherm) and HACS Scheduler Component.
- **Real-time Sensors**: Exposes learned heating slope, anticipation time, and next schedule information.
- **Configuration Interface**: Simple setup via the Home Assistant user interface.

## 🗺️ Future Features (The Pilot's Full Capabilities)

The long-term ambition of IHP includes, but is not limited to:

- **Optimal Setback Strategy**: Evaluating the energy efficiency of lowering the temperature (setback) and deciding if maintaining the current temperature is economically superior over a short period.
- **Occupancy-Aware Stop**: Strategic shutdown of heating based on learned occupancy patterns and real-time presence detection.
- **Thermal Inertia Coasting**: Automatically turning off the heating system early to leverage the room's residual heat, allowing the temperature to naturally coast down to the new target.
- **Multi-Room Coordination**: Intelligent coordination across multiple zones for optimal comfort and efficiency.
- **Energy Cost Optimization**: Dynamic adjustment based on real-time energy pricing and weather forecasts.

## 🧠 Understanding IHP

### What Happens Automatically

Once configured, IHP runs in the background:

1. ✅ Monitors your scheduler for heating events
2. ✅ Learns how fast your room heats (Learned Heating Slope)
3. ✅ Calculates optimal start time for next event
4. ✅ Triggers heating at exactly the right moment
5. ✅ Improves predictions with each heating cycle

**Result:** Your room reaches target temperature exactly on time, automatically, no manual intervention.

### First 5 Heating Cycles

Expect heating to start **earlier than necessary** during this learning phase:
- This is intentional (conservative approach)
- Room will reach target before scheduled time
- This is **normal and expected**
- Accuracy improves as IHP learns

**After 20+ cycles:** Predictions become very accurate.

### Key Concept: Learned Heating Slope

IHP learns **how fast your room heats** (°C per hour):
- 1.0 = slow heating (poor insulation)
- 2.0 = normal heating (typical)
- 4.0+ = fast heating (well-insulated)

It computes this from each detected heating cycle: slope = (end temperature − start temperature) / hours of the cycle, then averages across recent cycles.

Using this, IHP calculates: "To heat 3°C at 2°C/hour, I need 90 minutes" ✅

**[Learn more in How IHP Works →](docs/HOW_IT_WORKS.md)**

### Sensors Created

| Sensor | Shows |
|--------|-------|
| **Learned Heating Slope** | How fast your room heats (°C/h) |
| **Anticipation Time** | When heating will start next |
| **Next Schedule** | Details of next heating event |

---

## 🎛️ Services

### `intelligent_heating_pilot.reset_learning`

Resets learned data. Use this if you changed your heating system (new radiators, better insulation, etc.):

```yaml
service: intelligent_heating_pilot.reset_learning
```

IHP will start learning from scratch with the next heating cycle.

---

## 🐛 Something Wrong?

**[Check Troubleshooting Guide →](docs/TROUBLESHOOTING.md)**

Common issues and solutions:
- ❌ Predictions inaccurate
- ❌ Sensors show no data
- ❌ Heating never triggers
- ❌ IHP won't load

## 🤝 Contributing

We welcome contributions! Whether you want to:
- 🐛 Report bugs
- ✨ Suggest features
- 💻 Submit code improvements
- 📝 Improve documentation

**[Check out Contributing Guide →](CONTRIBUTING.md)**

For technical deep dive: [Architecture Documentation](ARCHITECTURE.md)

## 📚 Documentation

Choose your path below based on who you are:

### 👤 For Users

**New to IHP?** Start here:

1. **[User Guide](docs/USER_GUIDE.md)** - Overview and quick navigation
2. **[Installation Guide](docs/INSTALLATION.md)** - Step-by-step installation via HACS or manually
3. **[Configuration Guide](docs/CONFIGURATION.md)** - Set up IHP with your system
4. **[How IHP Works](docs/HOW_IT_WORKS.md)** - Understand heating cycle detection and prediction logic
5. **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)** - Common issues and solutions

**Quick Links:**
- 📋 [Changelog](CHANGELOG.md) - Version history and changes
- 🐛 [Report a Bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)
- 💬 [Ask Questions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
- 📦 [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)

### 👨‍💻 For Contributors

**Want to improve IHP?** Read these:

1. **[Contributing Guide](CONTRIBUTING.md)** - How to contribute (bugs, features, code)
2. **[Architecture Documentation](ARCHITECTURE.md)** - Technical design (DDD principles)
3. **[Copilot Instructions](.github/copilot-instructions.md)** - Development guidelines and standards

---

## 🚀 Installation (Quick)

### Via HACS (Recommended)

1. Open **HACS** → **Integrations**
2. Click **⋮** → **Custom repositories**
3. Add: `https://github.com/RastaChaum/Intelligent-Heating-Pilot` (Category: Integration)
4. Search for **"Intelligent Heating Pilot"** → **Download**
5. **Restart Home Assistant**

### Manual Installation

1. Download from [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)
2. Extract to: `config/custom_components/intelligent_heating_pilot/`
3. **Restart Home Assistant**

**[Full installation guide →](docs/INSTALLATION.md)**

---

## ⚙️ Configuration (Quick)

1. Settings → Devices & Services → **+ Create Integration**
2. Search for **"Intelligent Heating Pilot"**
3. Fill in:
   - **Name** - Any name (e.g., "Living Room")
   - **VTherm Entity** - Your thermostat (e.g., `climate.living_room`)
   - **Scheduler Entity** - Your scheduler (e.g., `switch.schedule_heating`)
4. (Optional) Add humidity/outdoor temp sensors for better accuracy
5. **Submit**

**[Full configuration guide →](docs/CONFIGURATION.md)**

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgements

- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) by @jmcollin78 - The foundation for intelligent heating
- [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) by @nielsfaber - Scheduling integration
- The Home Assistant community for their continuous support and feedback

## ⭐ Star History

If you find this project useful, please consider giving it a star! It helps others discover the project.

[![Star History Chart](https://api.star-history.com/svg?repos=RastaChaum/Intelligent-Heating-Pilot&type=Date)](https://star-history.com/#RastaChaum/Intelligent-Heating-Pilot&Date)
