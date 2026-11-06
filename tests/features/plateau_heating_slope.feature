Feature: A plateau below the target does not lower the learned heating slope
  As a household whose thermostat settles a few tenths below its target
  I want the heating slope measured on the rise only, not on the plateau that follows it
  So that my preheats do not start earlier every day

  Background:
    Given a thermostat targeting 20.0 °C, read every 6 minutes by a sensor reporting 0.1 °C steps

  Scenario: A preheat that settles below its target learns the slope of its rise
    Given a heating cycle from 18.5 °C that stays flat for 30 minutes, rises 1.0 °C per hour to 19.7 °C, then stays flat for 120 minutes until it is switched off
    When IHP extracts the heating cycles
    Then the cycle has a heating slope of 1.0 °C/h
    And the cycle has a dead time of 42 minutes
    And the cycle lasts 222 minutes and ends at 19.7 °C

  Scenario: The slope is measured up to the first plateau, even when the room climbs again
    Given a heating cycle from 18.5 °C that stays flat for 30 minutes, rises 1.0 °C per hour to 19.2 °C, stays flat for 90 minutes, then rises 1.0 °C per hour to its target
    When IHP extracts the heating cycles
    Then the cycle has a heating slope of 1.0 °C/h

  Scenario: A room that keeps warming until its target keeps its slope
    Given a heating cycle from 18.5 °C that stays flat for 30 minutes, then rises 1.0 °C per hour to its target
    When IHP extracts the heating cycles
    Then the cycle has a heating slope of 1.0 °C/h

  Scenario: A slow heating system that keeps warming keeps its slow slope
    Given a heating cycle from 19.0 °C that rises 0.25 °C per hour to its target
    When IHP extracts the heating cycles
    Then the cycle has a heating slope of 0.25 °C/h

  Scenario: A flat stretch shorter than a plateau at the end of the cycle is kept in the slope
    Given a heating cycle from 18.5 °C that stays flat for 30 minutes, rises 1.0 °C per hour to 19.7 °C, then stays flat for 40 minutes until it is switched off
    When IHP extracts the heating cycles
    Then the cycle has a heating slope of 0.6 °C/h

  Scenario: Split cycles of a plateau preheat get the slope of the rise
    Given heating cycles are split every 30 minutes
    And a heating cycle from 18.5 °C that stays flat for 30 minutes, rises 1.0 °C per hour to 19.7 °C, then stays flat for 120 minutes until it is switched off
    When IHP extracts the heating cycles
    Then every sub-cycle has a heating slope of 1.0 °C/h
    And the last sub-cycle ends 102 minutes after the cycle start
