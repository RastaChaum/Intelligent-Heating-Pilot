Feature: IHP Enable/Disable Switch Controls Preheating
  As a user of Intelligent Heating Pilot
  I want the IHP enable/disable switch to control whether preheating occurs
  So that I can quickly enable or disable intelligent preheating without reconfiguring the system

  Background:
    Given a VTherm device "climate.bedroom" exists
    And a scheduler "switch.bedroom_schedule" is configured to heat to 21°C at 07:00
    And the current temperature is 18°C at 05:00
    And the learned heating slope is 2°C per hour

  Scenario: When IHP switch is disabled, no preheating occurs before scheduled time
    Given the IHP enable switch is turned off
    When the system calculates anticipation at 05:00
    Then the VTherm temperature setpoint should remain at the current scheduled temperature
    And no preheating should be triggered before 07:00
    And the VTherm temperature should still be 18°C at 06:30

  Scenario: When IHP switch is enabled, intelligent preheating occurs as expected
    Given the IHP enable switch is turned on
    When the system calculates anticipation at 05:00
    Then preheating should be scheduled to start at 05:30
    And the VTherm temperature setpoint should be raised to 21°C at 05:30
    And the home should reach target temperature by 07:00

  Scenario: Disabling IHP switch during active preheating cancels preheating immediately
    Given the IHP enable switch is turned on
    And preheating started at 05:30 with target temperature 21°C
    And the current time is 06:00 and preheating is active
    When the user turns off the IHP enable switch
    Then the active preheating should be canceled immediately
    And the VTherm temperature setpoint should revert to the current scheduled temperature
    And the system should wait for the original scheduled time (07:00)

  Scenario: Re-enabling IHP switch after disabling it resumes anticipation calculations
    Given the IHP enable switch was turned off at 05:00
    And no preheating was active
    When the user turns on the IHP enable switch at 05:15
    And the system recalculates anticipation
    Then preheating should be scheduled based on current conditions
    And anticipation calculations should resume normally
    And the next scheduled event (07:00) should be anticipated correctly

  Scenario: IHP switch state persists across Home Assistant restarts
    Given the IHP enable switch is turned off
    And the configuration is saved
    When Home Assistant restarts
    Then the IHP enable switch should still be in the off state
    And no preheating should occur after restart

  Scenario: Multiple scheduler events respect IHP disable state
    Given the IHP enable switch is turned off
    And scheduler has 3 events today (07:00, 12:00, 19:00)
    When the system processes all scheduled events
    Then none of the events should trigger preheating
    And all events should occur at their exact scheduled times
    And room temperature should only change at scheduled times
