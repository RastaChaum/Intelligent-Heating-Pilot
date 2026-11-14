Feature: IHP waits for Home Assistant to start
  As a user restarting Home Assistant
  I want IHP to calculate only once Home Assistant has started
  So that a normal restart does not fill the log with warnings about missing data

  Scenario: A schedule appearing during startup triggers no calculation
    Given Home Assistant is starting
    When a scheduler entity appears
    Then no anticipation is calculated

  Scenario: A thermostat reporting its temperature during startup triggers no calculation
    Given Home Assistant is starting
    And the thermostat exists without a room temperature
    When the thermostat reports a room temperature
    Then no anticipation is calculated

  Scenario: The sensors receive the first calculation once Home Assistant has started
    Given Home Assistant is starting
    And a scheduler entity appears
    When Home Assistant has started
    And the startup update runs
    Then one anticipation is calculated
    And the sensors are updated

  Scenario: A thermostat reporting late still triggers a calculation
    Given Home Assistant has started
    And the thermostat exists without a room temperature
    When the thermostat reports a room temperature
    Then one anticipation is calculated
