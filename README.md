# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.1.0--alpha-orange)
![Status](https://img.shields.io/badge/status-alpha-red)

> [!WARNING]
> **🚧 ALPHA VERSION - USE AT YOUR OWN RISK 🚧**
> 
> This is the **first alpha release (v0.1.0-alpha)** of Intelligent Heating Pilot. While the core features are functional, this version is still in active development and testing.
>
> **Known Limitations:**
> - ⚠️ **Multi-scheduler per VTherm NOT tested**: Using multiple schedulers for a single thermostat has not been validated yet
> - 🧪 Multi-instance isolation (multiple IHP for different rooms) is newly implemented
> - 📊 Statistical learning requires several days of data collection for optimal accuracy
>
> **We encourage early adopters to test and provide feedback!** Please report any issues on [GitHub Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues).

---

**Intelligent Heating Pilot (IHP): The Adaptive Brain for Versatile Thermostat**

IHP is an ambitious Home Assistant integration designed to elevate your climate control from simple scheduling to strategic, energy-aware piloting.

The ultimate vision of IHP is to act as the complete "Flight Controller" for your heating system, making autonomous decisions regarding when to heat, how long to heat, and what the optimal temporary setpoint should be, based on Adaptive Learning and real-time inputs (occupancy, weather, inertia).

The first release (Proof of Concept / Alpha) focuses on delivering the foundational feature: **Smart Predictive Pre-heating (Adaptive Start)**. This initial capability uses statistical learning to continuously improve its predictions, laying the groundwork for future machine learning-based advanced functions.

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

## 📋 Prerequisites

- Home Assistant 2023.1.0 or higher
- Versatile Thermostat (VTherm) integration installed
- HACS Scheduler Component (for automated scheduling)
- Temperature sensors (indoor and outdoor recommended)

## 🚀 Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant.
2. Go to "Integrations".
3. Click on the three dots in the top right and select "Custom repositories".
4. Add the URL: `https://github.com/RastaChaum/Intelligent-Heating-Pilot`
5. Select the "Integration" category.
6. Click "Download".
7. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/intelligent_heating_pilot` folder into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.

## ⚙️ Configuration

### Initial Setup

1. Go to **Configuration** → **Integrations**.
2. Click **+ Add Integration**.
3. Search for "Intelligent Heating Pilot" or "IHP".
4. Fill in the required information:
   - **Name**: Name of your instance.
   - **VTherm Entity**: Your Versatile Thermostat climate entity (source of learned thermal slope).
   - **Scheduler Entities**: The HACS Scheduler Component switches that control this VTherm.
   - **Indoor Humidity Sensor** (optional): Room humidity sensor for refined calculations.
   - **Outdoor Humidity Sensor** (optional): External humidity sensor for refined calculations.
   - **Cloud Coverage Entity** (optional): Cloud coverage sensor to account for solar impact.

### Modifying Configuration

To change the entities after initial setup:

1. Go to **Configuration** → **Integrations**.
2. Find your **Intelligent Heating Pilot** integration.
3. Click on the **three dots** (⋮) menu.
4. Select **"Configure"** or **"Options"**.
5. Update the entities you want to change.
6. Click **"Submit"**.

The integration will automatically reload and start monitoring the new entities.

## 📊 Usage

### Automatic Operation

IHP works automatically in the background once configured:

1. **Monitors Your Scheduler**: Watches your configured scheduler entities for upcoming heating schedules.
2. **Learns Continuously**: Observes your VTherm's thermal slope and aggregates observations using robust statistics.
3. **Anticipates Start Time**: Calculates when to trigger the scheduler action to reach the target temperature exactly on time.
4. **Triggers Heating**: Automatically triggers the scheduler action at the optimal anticipated start time.
5. **Monitors Progress**: Tracks heating progress and prevents overshooting the target temperature.

### Sensors

The integration automatically creates several sensors for monitoring:

1. **Anticipation Time**: Shows the anticipated start time for the next heating schedule.
2. **Learned Heating Slope**: Displays the current learned heating slope (in °C/h) based on historical data.
3. **Next Schedule**: Shows details about the next scheduled heating event.

### Services

IHP provides a service for manual control if needed:

#### `intelligent_heating_pilot.reset_learning`

Resets the learned heating slope history. Use this if you've made significant changes to your heating system (new radiators, insulation, etc.) and want IHP to start learning from scratch.

**Example:**
```yaml
service: intelligent_heating_pilot.reset_learning
```

**Note**: The service uses the internal domain name `intelligent_heating_pilot` for backward compatibility with existing installations.

## 🧠 How IHP Works

IHP uses **statistical learning** to adapt to your specific heating system. Instead of using a fixed formula, it learns from your actual heating patterns.

### Simple Overview

1. **Learns from your system**: IHP monitors how fast your room heats up (from your VTherm's `temperature_slope` attribute)
2. **Builds history**: Collects and stores heating observations over time
3. **Calculates anticipation**: Determines when to start heating based on:
   - Temperature difference needed
   - Learned heating speed
   - Current conditions (humidity, cloud cover)
4. **Triggers heating**: Automatically starts your scheduler at the optimal time

### Key Features

- **Adaptive**: Continuously improves as it learns your system
- **Robust**: Uses statistical methods to filter out anomalies
- **Smart**: Adjusts for environmental factors
- **Automatic**: No manual tuning required

### Quick Calculation

For a typical scenario:
- Need to heat 3°C (18°C → 21°C)
- System heats at 2°C/hour
- Result: Start heating ~90 minutes before target time

**First time setup?** IHP starts with a conservative default and improves after 3-5 heating cycles.

### Reset Learning Data

If you make major changes to your heating system (new radiators, insulation, etc.):

```yaml
service: intelligent_heating_pilot.reset_learning
```

## 🐛 Troubleshooting

### Anticipation seems inaccurate

- **Initial learning phase**: IHP needs a few heating cycles to build accurate slope history. Give it 3-5 heating events to stabilize.
- **Extreme conditions**: Very cold outdoor temperatures or unusual weather can affect VTherm's slope calculations. IHP adapts over time.
- **Check logs**: Enable debug logging to see LHS values and calculation details:
  ```yaml
  logger:
    default: info
    logs:
      custom_components.intelligent_heating_pilot: debug
  ```

### Sensors show no data

- **Check VTherm configuration**: Ensure your VTherm entity has the `temperature_slope` attribute exposed.
- **Verify scheduler setup**: Make sure your scheduler entities have upcoming events configured.
- **Review logs**: Check Home Assistant logs for error messages or warnings from IHP.

### Need More Help?

- 📖 [Full Documentation](https://github.com/RastaChaum/Intelligent-Heating-Pilot)
- 🐛 [Report a Bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)
- 💬 [Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)

## 🤝 Contributing

We welcome contributions! Whether you want to:
- 🐛 Report bugs
- ✨ Suggest new features
- 💻 Submit code improvements
- 📝 Improve documentation

**Please read our [Contributing Guide](CONTRIBUTING.md)** to get started.

For technical documentation, see:
- 🏗️ [Architecture Documentation](ARCHITECTURE.md) - DDD principles and system design
- 🧪 [Testing Guide](CONTRIBUTING.md#testing) - How to write and run tests

## 📚 Documentation

### For Users

- **[Main README](README.md)** - You are here! Installation and usage guide
- **[Changelog](CHANGELOG.md)** - Version history and release notes
- **[Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)** - Download specific versions

### For Contributors

- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to the project
- **[Architecture Documentation](ARCHITECTURE.md)** - Technical design and DDD principles
- **[Copilot Instructions](.github/copilot-instructions.md)** - AI-assisted development guidelines

### Community

- **[Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)** - Ask questions, share ideas
- **[Issues](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues)** - Report bugs or request features

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgements

- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) by @jmcollin78 - The foundation for intelligent heating
- [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) by @nielsfaber - Scheduling integration
- The Home Assistant community for their continuous support and feedback

## ⭐ Star History

If you find this project useful, please consider giving it a star! It helps others discover the project.

[![Star History Chart](https://api.star-history.com/svg?repos=RastaChaum/Intelligent-Heating-Pilot&type=Date)](https://star-history.com/#RastaChaum/Intelligent-Heating-Pilot&Date)
