Feature: Only a dead time measured on heating cycles is stored as learned
  As a household relying on IHP to calibrate preheating
  I want only the dead time measured on my heating cycles to be stored as learned
  So that my configured dead time and a learning reset are respected

  Scenario: The configured dead time is not stored as learned
    Given no learned dead time is stored
    When IHP recalculates the anticipation with the configured dead time of 5 minutes
    Then no learned dead time is stored
    And no dead time update is announced

  Scenario: A restart does not rewrite the learned dead time
    Given a learned dead time of 6.5 minutes is stored
    When Home Assistant restarts and IHP recalculates the anticipation twice
    Then no learned dead time is stored
    And no dead time update is announced

  Scenario: A cache refresh keeps an unchanged learned dead time
    Given a learned dead time of 7.5 minutes is stored
    And cached heating cycles with dead times of 5 and 10 minutes
    When IHP refreshes its heating cycle cache
    Then no learned dead time is stored
    And no dead time update is announced

  Scenario: Turning auto-learning on learns from the cached cycles
    Given no learned dead time is stored
    And cached heating cycles with dead times of 5 and 10 minutes
    When IHP refreshes its heating cycle cache
    Then a learned dead time of 7.5 minutes is stored
    And a dead time update is announced
