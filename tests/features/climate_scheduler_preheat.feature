Feature: Climate Scheduler users get a real preheat
  As a user whose schedules come from Climate Scheduler
  I want IHP to apply the next node's own action at the anticipated start
  So that the room is warm when the node starts, with no extra automation

  Climate Scheduler applies a node only when it starts and when it is edited: it never
  re-applies a setpoint between two nodes.

  Background:
    Given the thermostat is in the "eco" preset at 18.0°C
    And it offers the presets "eco", "comfort" and "boost"

  Scenario: The next node is applied early
    Given an enabled Climate Scheduler switch whose next node at 18:00 sets 21.0°C
    When the anticipated start is reached
    Then the thermostat target becomes 21.0°C

  Scenario: A preset node is applied as a preset
    Given an enabled Climate Scheduler switch whose next node at 18:00 selects the "boost" preset
    When the anticipated start is reached
    Then the thermostat preset becomes "boost"

  Scenario: A disabled switch is never applied
    Given a disabled Climate Scheduler switch whose next node at 18:00 sets 21.0°C
    When the anticipated start is reached
    Then no command is sent to the thermostat

  Scenario: The room of a group gets its own node action
    Given an enabled Climate Scheduler switch for two rooms whose next node at 18:00 sets 21.0°C here and 19.0°C in the other room
    When the anticipated start is reached
    Then the thermostat target becomes 21.0°C

  Scenario: A re-application by the scheduler is not fought
    Given an enabled Climate Scheduler switch whose next node at 18:00 sets 21.0°C
    And the anticipated start is reached
    And the scheduler re-applies its current node after a restart
    When IHP recalculates
    Then IHP sends no new command
