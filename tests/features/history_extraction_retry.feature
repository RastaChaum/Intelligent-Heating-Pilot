Feature: Learning history survives Recorder failures and shutdowns
  As a household relying on IHP to learn how fast each room heats
  I want days whose history could not be read to be read again later
  So that a slow Recorder or a restart does not silently erase learning data

  Background:
    Given a period of 7 days of heating history to extract

  Scenario: A failed history read leaves the period to be retried
    Given the Recorder fails to return the history of that period
    When IHP extracts the period
    Then the period is not marked as explored
    And no heating cycles are learned from it

  Scenario: A purged period still ends the backfill
    Given the Recorder has already purged the history of that period
    When IHP extracts the period
    Then the period is marked as explored

  Scenario: A shutdown during a history read leaves the period to be retried
    Given Home Assistant shuts down while the history of that period is being read
    When IHP extracts the period
    Then the extraction stops
    And the period is not marked as explored
