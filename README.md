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

## 🧠 Intelligent Calculation Logic (Statistical Learning)

IHP goes beyond static calculations by employing **statistical learning** to dynamically adapt to your specific environment. Instead of relying on a fixed "thermal slope," the system continuously collects and aggregates thermal slope data from your VTherm to refine its predictions over time.

### How it works:

1. **Data Collection**: The integration continuously monitors your VTherm's `temperature_slope` attribute, which represents how quickly your room is heating up (in °C/h).

2. **Slope Aggregation**: IHP collects positive slope values (heating phases) and stores up to 100 recent observations. Negative slopes (cooling phases) are ignored to focus on heating behavior.

3. **Robust Statistical Analysis**: The Learned Heating Slope (LHS) is calculated using a **trimmed mean** approach:
   - Sort all collected slope values
   - Remove the top and bottom 10% (outliers)
   - Calculate the average of the remaining values
   - This provides a robust estimate resistant to extreme measurements

4. **Anticipation Calculation**: When a scheduled heating event approaches, IHP calculates:
   ```
   Base Time (minutes) = (Target Temp - Current Temp) / LHS × 60
   ```

5. **Environmental Corrections**: The base time is adjusted based on optional sensors:
   - **High Indoor Humidity** (>70%): +10% time (humid air feels cooler, heating perception slower)
   - **High Cloud Coverage** (>80%): +5% time (less solar gain, slower heating)

6. **Final Anticipation**: Add safety buffer and apply limits:
   ```
   Final Time = Base Time × Corrections + 5 minutes buffer
   Constrained between 10 and 180 minutes
   ```

7. **Trigger Point**: IHP triggers the scheduler action at:
   ```
   Start Time = Schedule Time - Final Anticipation Time
   ```

This statistical approach ensures IHP continuously improves its accuracy as it observes your heating system's real-world behavior, adapting to seasonal changes, VTherm configuration updates, and room characteristics.

### Cold Start Behavior

When IHP first starts or has no historical data, it uses a conservative default Learned Heating Slope (LHS) of **2.0°C/h**. As your VTherm heats the room, IHP begins collecting slope observations and the LHS becomes more accurate within a few heating cycles.

**Note**: Outdoor temperature is **not** directly used in the calculation. The VTherm's thermal slope already reflects environmental conditions (outdoor temperature affects how fast the room heats). IHP learns from these real-world observations rather than applying theoretical corrections.

### Calculation Example

**Scenario:**
- Current Temperature: 18°C
- Target Temperature: 21°C
- Learned Heating Slope (LHS): 2.0°C/h (from VTherm observations)
- Indoor Humidity: 65% (below threshold, no correction)
- Cloud Coverage: 85% (above 80%, applies correction)
- Scheduled Target Time: 07:00

**Step-by-Step Calculation:**

1. **Temperature Delta**: 21 - 18 = **3°C**

2. **Base Anticipation Time**: 3°C / 2.0°C/h × 60 = **90 minutes**

3. **Environmental Corrections**:
   - Humidity correction: None (65% < 70%)
   - Cloud coverage correction: 1.05 (85% > 80%)
   - Total correction factor: **1.05**

4. **Corrected Time**: 90 × 1.05 = **94.5 minutes**

5. **Add Safety Buffer**: 94.5 + 5 = **99.5 minutes**

6. **Apply Limits**: min(max(99.5, 10), 180) = **99.5 minutes** ✓

7. **Anticipated Start Time**: 07:00 - 99.5 min = **05:20:30**

**Result: IHP will trigger the scheduler action at 05:20:30 to reach 21°C by 07:00**

## 🔧 How IHP Learns Your Heating System

IHP automatically learns from your [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) by reading its `temperature_slope` attribute. No manual configuration is required.

### What is Thermal Slope?

The thermal slope represents how quickly your room heats up, measured in °C/h. For example, if your room goes from 18°C to 20°C in one hour, the thermal slope is 2.0°C/h.

**Factors influencing thermal slope:**
- Room insulation quality
- Radiator power and efficiency
- Room volume
- Heating system type
- Outdoor temperature (cold weather slows heating)
- Solar gain (sunny days speed heating)

### Learning Process

1. **VTherm measures**: Your VTherm continuously calculates the current thermal slope based on real-time temperature changes.

2. **IHP observes**: IHP reads this slope value whenever your room is heating (positive slopes only).

3. **Statistical aggregation**: IHP stores up to 100 recent slope observations and calculates a robust average (trimmed mean) to filter out outliers.

4. **Continuous improvement**: As seasons change, insulation settles, or you adjust your VTherm settings, IHP automatically adapts its predictions.

### Resetting Learning History

If you make significant changes to your heating system (new radiators, insulation work, etc.), you can reset IHP's learning history:

```yaml
service: intelligent_heating_pilot.reset_learning
```

IHP will start fresh with the default 2.0°C/h slope and begin learning again from your new system's behavior.

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

## 🤝 Contribution

Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## 📝 License

This project is licensed under the MIT License.

## 👏 Acknowledgements

- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) for inspiration
- The Home Assistant community
