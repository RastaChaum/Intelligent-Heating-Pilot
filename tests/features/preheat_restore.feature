Feature: A preheat is undone safely
  As a user whose thermostat IHP preheats
  I want the thermostat to return to where it was if the preheat is cancelled
  So that IHP never leaves the room in a state I did not choose, and never overrides me

  Direct control records the thermostat's state once, before it acts, and keeps that record
  across a restart.

  Background:
    Given direct control of native schedules is on
    And the next block starts at 18:00 with the data preset "comfort"

  Scenario: Removing the block restores the earlier state
    Given the thermostat is in the "eco" preset at 18.0°C
    And a preheat is in progress for that block
    When the block is removed from the schedule
    And IHP recalculates
    Then the thermostat preset is back to "eco"

  Scenario: A manual change during the preheat is never overwritten
    Given the thermostat is in the "eco" preset at 18.0°C
    And a preheat is in progress for that block
    And the user selects the "boost" preset by hand
    When the block is removed from the schedule
    And IHP recalculates
    Then the thermostat preset is still "boost"
    And IHP wrote nothing to the thermostat after the preheat started

  Scenario: A thermostat set by hand goes back to its temperature
    Given the thermostat is set by hand to 19.0°C without a preset
    And a preheat is in progress for that block
    When the block is removed from the schedule
    And IHP recalculates
    Then the thermostat target is back to 19.0°C

  Scenario: A restart in the middle of the preheat keeps it going
    Given the thermostat is in the "eco" preset at 18.0°C
    And a preheat is in progress for that block
    When Home Assistant restarts
    And IHP recalculates
    Then IHP sends no new command
    And the preheat is still in progress

  Scenario: Cancelling when the slot is imminent restores nothing
    Given the thermostat is in the "eco" preset at 18.0°C
    And a preheat is in progress for that block
    And it is 3 minutes before the block starts
    When the block is removed from the schedule
    And IHP recalculates
    Then the thermostat preset is still "comfort"

  Scenario: Reaching the slot forgets what was recorded
    Given the thermostat is in the "eco" preset at 18.0°C
    And a preheat is in progress for that block
    When the start time of the block is reached
    And IHP recalculates
    Then the thermostat preset is still "comfort"
    And nothing is left recorded
