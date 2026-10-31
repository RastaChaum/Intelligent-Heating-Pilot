Feature: A heating cycle's dead time and heating slope are measured where heating really starts
  As a household relying on IHP to start preheating on time
  I want the dead time and heating slope of my heating cycles measured where heating really starts
  So that the learned values describe how fast my room actually heats

  Background:
    Given a thermostat targeting 20.0 °C, with an indoor reading every 6 minutes rounded to 0.1 °C

  Scenario: A rise of exactly 0.2 °C ends the dead time
    Given a heating cycle from 18.0 °C that stays flat for 30 minutes, then rises 1.0 °C per hour
    When IHP extracts the heating cycles
    Then the cycle has a dead time of 42 minutes
    And the cycle has a heating slope of 1.0 °C/h

  Scenario: A fall at heating start stays in the dead time, out of the heating slope
    Given a heating cycle from 18.0 °C that falls 0.4 °C in 24 minutes, then rises 1.0 °C per hour
    When IHP extracts the heating cycles
    Then the cycle has a dead time of 60 minutes
    And the cycle has a heating slope of 1.0 °C/h

  Scenario: A cycle rejected from the heating slope does not teach the dead time
    Given a heating cycle from 18.0 °C that stays flat for 30 minutes, then rises 1.0 °C per hour
    And a heating cycle from 19.5 °C that falls 0.3 °C in 18 minutes, then rises 1.0 °C per hour until it is switched off at 19.7 °C
    When IHP extracts the heating cycles
    And IHP learns the dead time from them
    Then the learned dead time is 42 minutes

  Scenario: Split cycles keep the heating slope of the heating phase
    Given heating cycles are split every 30 minutes
    And a heating cycle from 18.0 °C that stays flat for 30 minutes, then rises 1.0 °C per hour
    When IHP extracts the heating cycles
    Then every sub-cycle has a heating slope of 1.0 °C/h
    And only the first sub-cycle has a dead time, of 42 minutes, and it starts with the cycle
