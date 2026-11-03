Feature: A late preheat is learned by the slot it heated for
  As a user whose room sometimes reaches the target after the scheduled time
  I want a late preheat to count for the slot it was heating for
  So that the slot learns its preheats are late and starts them earlier

  Background:
    Given the room heats toward 20.0 degrees

  Scenario: A preheat that reaches the target long after its slot counts for that slot
    Given a 20.0 degree slot came due at 08:45
    And the room heated from 06:20 until it reached the target at 09:56
    When the heating cycles are extracted and contextual slopes are learned
    Then the cycle is learned for a slot at 08:45
    And the cycle is not learned for a slot at 10:00

  Scenario: A preheat that lands just before its slot keeps the nearest hour
    Given a 20.0 degree slot came due at 07:00
    And the room heated from 05:40 until it reached the target at 06:58
    When the heating cycles are extracted and contextual slopes are learned
    Then the cycle is learned for a slot at 07:00

  Scenario: A slot with another target does not claim the cycle
    Given a 18.0 degree slot came due at 08:45
    And the room heated from 06:20 until it reached the target at 09:56
    When the heating cycles are extracted and contextual slopes are learned
    Then the cycle is learned for a slot at 10:00
    And the cycle is not learned for a slot at 08:45

  Scenario: Without a slot history the cycle keeps the nearest hour
    Given the room heated from 06:20 until it reached the target at 09:56
    When the heating cycles are extracted and contextual slopes are learned
    Then the cycle is learned for a slot at 10:00

  Scenario: Every sub-cycle of a late preheat counts for its slot
    Given cycles are split every 60 minutes
    And a 20.0 degree slot came due at 08:45
    And the room heated from 06:20 until it reached the target at 09:56
    When the heating cycles are extracted and contextual slopes are learned
    Then there are several cycles
    And every cycle is learned for a slot at 08:45
