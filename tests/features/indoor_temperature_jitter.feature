Feature: Indoor temperature jitter does not delay the preheat
  As a user whose room sensor toggles between two adjacent values
  I want IHP to anticipate from the thermostat's smoothed room temperature
  So that a higher reading just before the preheat does not push it later

  Scenario: The preheat is anticipated from the smoothed room temperature
    Given the thermostat reads 18.90 °C with a smoothed temperature of 19.00 °C
    When IHP reads the current environment
    Then the room temperature is 19.00 °C

  Scenario: A thermostat without a smoothed temperature is read as before
    Given the thermostat reads 19.10 °C with no smoothed temperature
    When IHP reads the current environment
    Then the room temperature is 19.10 °C

  Scenario: A toggling sensor triggers no recalculation
    Given IHP monitors the thermostat
    When the thermostat reads 19.12, 19.33, 19.12, 19.33 °C with a smoothed temperature of 19.20 °C
    Then no step triggers a recalculation

  Scenario: A change of the smoothed temperature triggers a recalculation
    Given IHP monitors the thermostat
    When the smoothed temperature goes 19.20, 19.25 °C while the thermostat reads 19.33 °C
    Then every step triggers a recalculation
