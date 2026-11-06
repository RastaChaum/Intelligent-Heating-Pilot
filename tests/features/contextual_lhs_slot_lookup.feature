Feature: Scheduled slots use the heating slope learned for them
  As a user with a heating schedule
  I want each scheduled slot to use the slope learned while preheating for that slot
  So that anticipation adapts to how the room heats at that time of day

  Background:
    Given a heating slope learner with persistent storage
    And a preheat cycle from 05:30 to 07:00 that heated at 3.0 degrees per hour
    And a preheat cycle from 06:00 to 07:15 that heated at 4.0 degrees per hour
    And a daytime cycle from 13:00 to 14:00 that heated at 1.0 degrees per hour
    And contextual slopes are learned from these cycles

  Scenario: A 07:00 slot reads the slope learned while preheating for it
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 3.5 degrees per hour

  Scenario: The learned slot slope survives a restart
    Given Home Assistant restarts
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 3.5 degrees per hour

  Scenario: The hour a preheat cycle started does not pick up its slope
    When the heating slope for a slot at 05:00 is requested
    Then the heating slope returned is not learned from the preheat cycles

  Scenario: A slot whose learned slope is unrealistically low uses the global slope
    Given the global heating slope is 0.4 degrees per hour
    And a slow cycle from 21:00 to 22:00 that heated at 0.15 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 22:00 is requested
    Then the heating slope returned is 0.4 degrees per hour

  Scenario: A slow slope stored for a slot is used after a restart
    Given the global heating slope is 0.4 degrees per hour
    And a slope of 0.15 degrees per hour is stored for 22:00
    And Home Assistant restarts
    When the heating slope for a slot at 22:00 is requested
    Then the heating slope returned is 0.15 degrees per hour

  Scenario: A slope that is not positive, stored by an earlier version, uses the global slope
    Given the global heating slope is 0.4 degrees per hour
    And a slope of 0.0 degrees per hour is stored for 22:00
    And Home Assistant restarts
    When the heating slope for a slot at 22:00 is requested
    Then the heating slope returned is 0.4 degrees per hour
    And no slope is stored for 22:00 any more

  Scenario: A slot whose slope becomes unrealistically low stops using its earlier slope
    Given the global heating slope is 0.4 degrees per hour
    And a slope of 1.2 degrees per hour was learned earlier for 22:00
    And a slow cycle from 21:00 to 22:00 that heated at 0.15 degrees per hour
    And contextual slopes are learned from these cycles
    And Home Assistant restarts
    When the heating slope for a slot at 22:00 is requested
    Then the heating slope returned is 0.4 degrees per hour
    And no slope is stored for 22:00 any more

  Scenario: Cycles that barely heated do not drag the global slope down
    Given a slow cycle from 21:00 to 22:00 that heated at 0.15 degrees per hour
    And a slow cycle from 22:00 to 23:00 that heated at 0.1 degrees per hour
    And the global slope is learned from these cycles
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 22:00 is requested
    Then the heating slope returned is 2.67 degrees per hour
