Feature: Check Overshoot Risk
  As a heating system
  I want to detect when heating will overshoot the target temperature
  So that I can stop preheating early to avoid overheating the home

  Background:
    Given the overshoot risk checker is configured
    And the overshoot threshold is 0.5°C above target

  Scenario: Overshoot detected — cancel preheating
    Given preheating is active for scheduler "switch.living_room_schedule"
    And the next target is 21°C at 07:00
    And the current indoor temperature is 20.0°C
    And the current heating slope is 3.0°C per hour
    And the current time is 06:45
    When the system checks for overshoot risk
    Then overshoot should be detected
    And preheating should be canceled to prevent overheating
    And the method should return True

  Scenario: No overshoot risk — continue preheating
    Given preheating is active for scheduler "switch.living_room_schedule"
    And the next target is 21°C at 07:00
    And the current indoor temperature is 18.0°C
    And the current heating slope is 2.0°C per hour
    And the current time is 06:30
    When the system checks for overshoot risk
    Then no overshoot should be detected
    And preheating should continue normally
    And the method should return False

  Scenario: No preheating active — skip check
    Given no preheating is currently active
    And the next target is 21°C at 07:00
    When the system checks for overshoot risk
    Then the check should be skipped
    And the method should return False

  Scenario: No timeslot available — skip check
    Given preheating is active for scheduler "switch.living_room_schedule"
    And no scheduler timeslot is available
    When the system checks for overshoot risk
    Then the check should be skipped
    And the method should return False

  Scenario: Current slope is zero — skip check
    Given preheating is active for scheduler "switch.living_room_schedule"
    And the next target is 21°C at 07:00
    And the current indoor temperature is 19.0°C
    And the current heating slope is 0.0°C per hour
    And the current time is 06:30
    When the system checks for overshoot risk
    Then the check should be skipped because slope is zero
    And the method should return False

  Scenario: Target time already passed — skip check
    Given preheating is active for scheduler "switch.living_room_schedule"
    And the next target is 21°C at 07:00
    And the current indoor temperature is 19.0°C
    And the current heating slope is 2.0°C per hour
    And the current time is 07:15
    When the system checks for overshoot risk
    Then the check should be skipped because target time has passed
    And the method should return False
