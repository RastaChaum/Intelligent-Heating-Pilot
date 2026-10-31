Feature: A slot learns from the cycles that reached its target around it
  As a user with a heating schedule
  I want a cycle that reaches the target a little before or after a slot to count for that slot
  So that the slope learned for a slot does not depend on how precisely preheating lands

  Background:
    Given a heating slope learner with persistent storage
    And the global heating slope is 1.5 degrees per hour

  Scenario: A cycle that reaches the target just before a 07:00 slot counts for it
    Given a preheat cycle from 05:40 to 06:58 that heated at 3.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 3.0 degrees per hour

  Scenario: Cycles that land just before and just after a 07:00 slot are averaged together
    Given a preheat cycle from 05:40 to 06:58 that heated at 3.0 degrees per hour
    And a preheat cycle from 06:00 to 07:20 that heated at 4.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 3.5 degrees per hour

  Scenario: A cycle that reaches the target more than half an hour before a slot counts for the earlier hour
    Given a preheat cycle from 05:00 to 06:20 that heated at 3.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 06:00 is requested
    Then the heating slope returned is 3.0 degrees per hour
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 1.5 degrees per hour

  Scenario: A half-hour slot counts the cycles that reached the target before it or exactly at it
    Given a preheat cycle from 05:00 to 06:10 that heated at 3.0 degrees per hour
    And a preheat cycle from 05:10 to 06:30 that heated at 4.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 06:30 is requested
    Then the heating slope returned is 3.5 degrees per hour

  Scenario: A cycle that reaches the target after a half-hour slot counts for the next hour
    Given a preheat cycle from 05:20 to 06:40 that heated at 3.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 06:30 is requested
    Then the heating slope returned is 1.5 degrees per hour
    When the heating slope for a slot at 07:00 is requested
    Then the heating slope returned is 3.0 degrees per hour

  Scenario: A cycle that reaches the target just before midnight counts for a midnight slot
    Given a preheat cycle from 22:40 to 23:50 that heated at 3.0 degrees per hour
    And contextual slopes are learned from these cycles
    When the heating slope for a slot at 00:00 is requested
    Then the heating slope returned is 3.0 degrees per hour
