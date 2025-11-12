# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

**Intelligent Heating Pilot (IHP): The Adaptive Brain for Versatile Thermostat**

IHP is an ambitious Home Assistant integration designed to elevate your climate control from simple scheduling to strategic, energy-aware piloting.

The ultimate vision of IHP is to act as the complete "Flight Controller" for your heating system, making autonomous decisions regarding when to heat, how long to heat, and what the optimal temporary setpoint should be, based on Adaptive Learning and real-time inputs (occupancy, weather, inertia).

The first release (Proof of Concept) focuses on delivering the foundational feature: **Smart Predictive Pre-heating (Adaptive Start)**. This initial capability lays the groundwork by building the essential Online Learning Model needed for all future advanced functions.

## 🌟 Current Features (V1: Adaptive Start)

- **Smart Predictive Pre-heating**: Automatically determines when to start heating to reach the target temperature at the exact scheduled time.
- **Adaptive Learning**: Continuously learns your heating system's behavior through online machine learning.
- **Multi-Factor Awareness**: Adapts calculations based on outdoor temperature, humidity, and cloud coverage.
- **Thermal Modeling**: Builds and refines thermal models specific to your room and heating system.
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

1. Copy the `custom_components/smart_starter_vtherm` folder into your Home Assistant `custom_components` folder.
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
2. **Learns Continuously**: Observes your VTherm's thermal slope and builds an adaptive model.
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

## 🧠 Intelligent Calculation Logic (Online Machine Learning)

IHP goes beyond static calculations by employing an **online machine learning model** to dynamically learn and adapt to your specific environment. Instead of relying on a fixed "thermal slope," the system continuously refines its understanding of your heating system's behavior based on historical data and new observations from your Home Assistant installation.

For each VTherm instance, the model learns:

1.  **Room-specific thermal characteristics**: How quickly a particular room heats up or cools down under various conditions.
2.  **Impact of external factors**: The influence of outdoor temperature, humidity, and other environmental variables on heating efficiency.
3.  **System inertia**: The time it takes for your heating system to respond and for the room temperature to change.

### How it works:

-   **Data Collection**: The integration collects data points including current temperature, target temperature, outdoor temperature, heating duration, and actual time to reach the target.
-   **Model Training**: An online machine learning algorithm (e.g., a regression model) is continuously trained and updated with this new data. This allows the model to adapt to changes in insulation, radiator performance, seasonal variations, and other dynamic factors.
-   **Predictive Calculation**: When a preheat is required, the model uses its learned knowledge to predict the precise duration needed to reach the target temperature at the scheduled time. This prediction is highly personalized to your specific VTherm and room conditions.

This approach ensures that IHP provides optimal preheating, minimizing energy waste while maximizing comfort, as it constantly learns and improves its accuracy over time.

### Initial Calculation (Fallback/Cold Start)

For initial setup or in cases where insufficient historical data is available, the system will use a simplified model based on:

1.  **Temperature Difference (ΔT)**: `target_temp - current_temp`
2.  **Outdoor Factor**: Impact of outdoor temperature on heating speed.
    -   Formula: `outdoor_factor = 1 + (20 - outdoor_temp) * 0.05`
    -   At 20°C outdoor: factor = 1.0 (no impact)
    -   At 0°C outdoor: factor = 2.0 (heating twice as slow)
    -   At -10°C outdoor: factor = 2.5
3.  **Effective Thermal Slope**: `effective_slope = thermal_slope / outdoor_factor`
4.  **Preheat Duration**: `duration = ΔT / effective_slope` (in hours, converted to minutes)
5.  **Start Time**: `start_time = target_time - duration`

As more data is collected, the online machine learning model will gradually take over, providing increasingly accurate and personalized preheating predictions.

### Calculation Example (Initial/Fallback Logic)

**Conditions:**
- Current Temperature: 18°C
- Target Temperature: 21°C
- Outdoor Temperature: 5°C
- Thermal Slope: 2.0°C/h
- Target Time: 07:00

**Calculation:**
1. ΔT = 21 - 18 = 3°C
2. outdoor_factor = 1 + (20 - 5) * 0.05 = 1.75
3. effective_slope = 2.0 / 1.75 = 1.14°C/h
4. duration = 3 / 1.14 = 2.63 hours = 158 minutes
5. start_time = 07:00 - 158 min = 04:22

**Result: Start heating at 04:22 to reach 21°C at 07:00**

## 🔧 Thermal Slope Configuration

### Option 1: Using Versatile Thermostat Entity

If you're using [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat), it already calculates and exposes the thermal slope as an entity. Simply:

1. During setup, select **"Entity"** as the Thermal Slope Source.
2. Choose the VTherm sensor that exposes the slope (typically named `sensor.<your_vtherm>_slope`).

The integration will automatically use the real-time thermal slope calculated by VTherm, ensuring the most accurate preheating predictions.

### Option 2: Manual Configuration **(Not Yet Implemented !)**

If you don't have Versatile Thermostat or prefer manual configuration:

1. During setup, select **"Manual"** as the Thermal Slope Source.
2. Enter your estimated thermal slope value.

**To determine your thermal slope manually:**

1. Note your room's initial temperature.
2. Start heating at full power.
3. After 1 hour, note the new temperature.
4. The difference is your thermal slope in °C/h.

Example: 18°C → 20°C after 1h = 2.0°C/h slope.

**Factors influencing thermal slope:**
- Room insulation
- Radiator power
- Room volume
- Heating type

**Note:** IHP's online machine learning model will continuously adapt and improve its predictions based on your actual heating patterns, regardless of initial configuration.



## 🔧 Determining Your Thermal Slope

The thermal slope represents the rate at which your room heats up. To determine it:

1. Note your room's initial temperature.
2. Start heating at full power.
3. After 1 hour, note the new temperature.
4. The difference is your thermal slope in °C/h.

Example: 18°C → 20°C after 1h = 2.0°C/h slope.

**Factors influencing thermal slope:**
- Room insulation
- Radiator power
- Room volume
- Heating type

## 🐛 Troubleshooting

### Service does not calculate correctly

- Verify all parameters are correct.
- Ensure the thermal slope matches your installation.
- Check Home Assistant logs for more details.

### Sensors do not update

- Verify the service has been called at least once.

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
