Feature: A brief load shedding does not restart the heating cycle
  As a household whose thermostats shed their load for a minute or two at a time
  I want IHP to learn a preheat interrupted by load shedding as one heating cycle
  So that the learned dead time is measured from when heating really started

  Background:
    Given a thermostat targeting 20.0 °C from 19.1 °C, ending a cycle 0.1 °C below its target
    And a preheat starting at 04:12, whose room gains 0.2 °C at 06:34 and reaches 19.9 °C at 08:22

  Scenario: Brief load sheddings are bridged and the whole preheat teaches its dead time
    Given a grace period of 10 minutes
    And the thermostat sheds its load for 2 minutes at 04:29
    And the thermostat sheds its load for 1 minutes at 04:49
    When IHP extracts the heating cycles and learns from them
    Then a single cycle is extracted, from 04:12 to 08:22
    And the cycle has a dead time of 142 minutes
    And the learned dead time is 142 minutes
    And the learned heating slope is 0.33 °C/h

  Scenario: Repeated load sheddings, each shorter than the grace period, are all bridged
    Given a grace period of 10 minutes
    And the thermostat sheds its load for 2 minutes every 3 minutes from 05:09 to 05:21
    When IHP extracts the heating cycles and learns from them
    Then a single cycle is extracted, from 04:12 to 08:22
    And the learned dead time is 142 minutes

  Scenario: A load shedding longer than the grace period still ends the cycle
    Given a grace period of 10 minutes
    And the thermostat sheds its load for 15 minutes at 04:29
    When IHP extracts the heating cycles and learns from them
    Then the first cycle ends at 04:29 and is disturbed
    And the learned dead time is 110 minutes

  Scenario: Without a grace period, a load shedding ends the cycle as before
    Given a grace period of 0 minutes
    And the thermostat sheds its load for 2 minutes at 04:29
    When IHP extracts the heating cycles and learns from them
    Then the first cycle ends at 04:29 and is disturbed

  Scenario: A window opening is not bridged
    Given a grace period of 10 minutes
    And a window drops the target to 7.0 °C for 2 minutes at 04:29
    When IHP extracts the heating cycles and learns from them
    Then the first cycle ends at 04:29
