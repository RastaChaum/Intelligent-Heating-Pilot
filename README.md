# Smart Starter VTherm

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Home Assistant integration for Versatile Thermostat (VTherm). Intelligently preheats your home to ensure the exact target temperature at the scheduled time, taking into account thermal slope, outdoor temperature, and scheduling.

## 🌟 Features

- **Intelligent Preheat Time Calculation**: Automatically determines when to start heating to reach the target temperature at the exact scheduled time.
- **Outdoor Conditions Awareness**: Adapts calculations based on outdoor temperature.
- **Thermal Modeling**: Utilizes the "thermal slope" (heating rate) of your room.
- **Home Assistant Service**: Easy to integrate into your automations.
- **Dedicated Sensors**: Exposes preheat duration and optimal start time.
- **Configuration Interface**: Setup via the Home Assistant user interface.

## 📋 Prerequisites

- Home Assistant 2023.1.0 or higher
- Versatile Thermostat (recommended but not mandatory)
- Temperature sensors (indoor and outdoor)

## 🚀 Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant.
2. Go to "Integrations".
3. Click on the three dots in the top right and select "Custom repositories".
4. Add the URL: `https://github.com/RastaChaum/SmartStarterVTherm`
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
3. Search for "Smart Starter VTherm".
4. Fill in the required information:
   - **Name**: Name of your instance.
   - **VTherm Entity**: Your Versatile Thermostat climate entity.
   - **Thermal Slope Entity**: The sensor exposing the thermal slope from VTherm (e.g., `sensor.vtherm_bedroom_slope`).
   - **Current Temperature Sensor**: Room temperature sensor.
   - **Current Humidity Sensor**: Room humidity sensor.
   - **Target Temperature Entity**: The thermostat or input_number with target temperature.
   - **Outdoor Temperature Sensor**: External temperature sensor.
   - **Outdoor Humidity Sensor**: External humidity sensor.
   - **Cloud Coverage Entity**: Cloud coverage sensor (from weather integration).

### Modifying Configuration

To change the entities after initial setup:

1. Go to **Configuration** → **Integrations**.
2. Find your **Smart Starter VTherm** integration.
3. Click on the **three dots** (⋮) menu.
4. Select **"Configure"** or **"Options"**.
5. Update the entities you want to change.
6. Click **"Submit"**.

The integration will automatically reload and start monitoring the new entities.

## 📊 Usage

### Service: `smart_starter_vtherm.calculate_start_time`

Calculates the optimal start time to reach the target temperature.

**Parameters:**
- `current_temp` (required): Current temperature in °C.
- `target_temp` (required): Target temperature in °C.
- `outdoor_temp` (required): Outdoor temperature in °C.
- `target_time` (required): Target time (format: "YYYY-MM-DD HH:MM:SS").
- `thermal_slope` (optional): Thermal slope in °C/h (default: 2.0).

**Service Call Example:**

```yaml
service: smart_starter_vtherm.calculate_start_time
data:
  current_temp: 18.5
  target_temp: 21.0
  outdoor_temp: 5.0
  target_time: "2024-01-15 07:00:00"
  thermal_slope: 2.5
```

### Sensors

The integration automatically creates two sensors:

1. **Preheat Duration**: Required preheat duration (in minutes).
2. **Start Time**: Optimal start time (timestamp).

### Automation Example

```yaml
automation:
  - alias: "Intelligent Heating Start"
    trigger:
      - platform: time_pattern
        minutes: "/5"  # Checks every 5 minutes
    action:
      - service: smart_starter_vtherm.calculate_start_time
        data:
          current_temp: "{{ states('sensor.salon_temperature') }}"
          target_temp: 21.0
          outdoor_temp: "{{ states('sensor.outdoor_temperature') }}"
          target_time: "{{ states('sensor.scheduler_next_time') }}"
          thermal_slope: 2.0
      - condition: template
        value_template: "{{ states('sensor.smart_starter_vtherm_start_time') <= now() }}"
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.versatile_thermostat
        data:
          hvac_mode: heat
```

## Intelligent Calculation Logic (Online Machine Learning)

The Smart Starter VTherm goes beyond static calculations by employing an **online machine learning model** to dynamically learn and adapt to your specific environment. Instead of relying on a fixed "thermal slope," the system continuously refines its understanding of your heating system's behavior based on historical data and new observations from your Home Assistant installation.

For each VTherm instance, the model learns:

1.  **Room-specific thermal characteristics**: How quickly a particular room heats up or cools down under various conditions.
2.  **Impact of external factors**: The influence of outdoor temperature, humidity, and other environmental variables on heating efficiency.
3.  **System inertia**: The time it takes for your heating system to respond and for the room temperature to change.

### How it works:

-   **Data Collection**: The integration collects data points including current temperature, target temperature, outdoor temperature, heating duration, and actual time to reach the target.
-   **Model Training**: An online machine learning algorithm (e.g., a regression model) is continuously trained and updated with this new data. This allows the model to adapt to changes in insulation, radiator performance, seasonal variations, and other dynamic factors.
-   **Predictive Calculation**: When a preheat is required, the model uses its learned knowledge to predict the precise duration needed to reach the target temperature at the scheduled time. This prediction is highly personalized to your specific VTherm and room conditions.

This approach ensures that the Smart Starter VTherm provides optimal preheating, minimizing energy waste while maximizing comfort, as it constantly learns and improves its accuracy over time.

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

### Option 2: Manual Configuration

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

**Note:** Even with manual configuration, the online machine learning model will continuously adapt and improve its predictions based on your actual heating patterns.



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
- Sensors are updated during the `smart_starter_vtherm_calculation_complete` event.

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
