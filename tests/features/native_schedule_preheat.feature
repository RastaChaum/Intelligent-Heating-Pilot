Feature: Native schedule users get a real preheat
  As a user whose heating plan is a native Home Assistant schedule
  I want IHP to apply the next block's own action at the anticipated start
  So that the room is warm when the block starts, without building my own automation

  A block's data holds the action: a preset, a temperature, or both. Nothing is applied unless
  I turned on direct control of native schedules.

  Background:
    Given the thermostat is in the "eco" preset at 18.0°C
    And it offers the presets "eco", "comfort" and "boost"

  Scenario: The block's preset is applied as a preset
    Given direct control of native schedules is on
    And the next block starts at 18:00 with the data preset "boost"
    When the anticipated start is reached
    Then the thermostat preset becomes "boost"

  Scenario: The block's temperature is applied as a temperature
    Given direct control of native schedules is on
    And the next block starts at 18:00 with the data temperature 21.0
    When the anticipated start is reached
    Then the thermostat target becomes 21.0°C
    And no preset was set

  Scenario: A block without data gets the fallback preset
    Given direct control of native schedules is on
    And the next block starts at 18:00 with no data
    When the anticipated start is reached
    Then the thermostat preset becomes "comfort"

  Scenario: The preset wins when the block holds both
    Given direct control of native schedules is on
    And the next block starts at 18:00 with the data preset "boost" and temperature 22.0
    When the anticipated start is reached
    Then the thermostat preset becomes "boost"
    And no temperature was set

  Scenario: Nothing is applied without the opt-in
    Given the next block starts at 18:00 with the data preset "boost"
    When the anticipated start is reached
    Then no command is sent to the thermostat
    And the thermostat preset is still "eco"

  Scenario: A block that follows a running one is anticipated with its own action
    Given direct control of native schedules is on
    And the schedule is running a block until 18:00 with the data preset "comfort"
    And the next block starts at 18:00 with the data preset "boost"
    When the anticipated start is reached
    Then the thermostat preset becomes "boost"
