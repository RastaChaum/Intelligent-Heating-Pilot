Feature: Slow heating cycles are learned, and only the thermostat's own signals mark a cycle as disturbed
  As a household with a slow heating system, such as underfloor heating
  I want IHP to learn from my slowest preheats, and to ignore only the cycles my thermostat reports as disturbed
  So that preheating starts early enough on cold mornings

  Background:
    Given a thermostat targeting 20.0 °C, with an indoor reading every 10 minutes rounded to 0.1 °C

  Scenario: A slow underfloor preheat teaches its long dead time
    Given a heating cycle from 19.4 °C that stays flat for 220 minutes, then rises 0.6 °C per hour
    When IHP extracts the heating cycles and learns from them
    Then the cycle has a dead time of 240 minutes
    And the cycle has a heating slope of 0.6 °C/h
    And the learned dead time is 240 minutes
    And the learned heating slope is 0.6 °C/h

  Scenario: A slow but undisturbed room learns its own heating slope
    Given a heating cycle from 19.4 °C that stays flat for 60 minutes, then rises 0.12 °C per hour
    When IHP extracts the heating cycles and learns from them
    Then the learned dead time is 140 minutes
    And the learned heating slope is 0.12 °C/h

  Scenario: A cycle in safety mode teaches nothing, however fast it heats
    Given a heating cycle from 18.0 °C that stays flat for 30 minutes, then rises 1.0 °C per hour
    And the thermostat is in safety mode from minute 60 to minute 90
    When IHP extracts the heating cycles and learns from them
    Then nothing is learned from the cycle

  Scenario: A cycle cut short by load shedding teaches nothing
    Given a heating cycle from 18.0 °C that stays flat for 30 minutes, then rises 1.0 °C per hour
    And the thermostat sheds its load at minute 60
    When IHP extracts the heating cycles and learns from them
    Then nothing is learned from the cycle

  Scenario: A cycle that never warmed the room teaches nothing
    Given a heating cycle from 19.7 °C that rises 0.4 °C per hour
    When IHP extracts the heating cycles and learns from them
    Then the cycle has no dead time
    And nothing is learned from the cycle
