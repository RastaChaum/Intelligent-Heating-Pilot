Feature: The weather corrects only the heating phase, and the sun only in daylight
  As a user with a humidity sensor and a cloud coverage source
  I want the weather to adjust only the time my room takes to warm up once it responds
  So that IHP never starts a preheat late because of a shortened dead time or a sun not yet up

  Background:
    Given the sun rises at 07:50 and sets at 17:30

  Scenario: A clear sky does not shorten the dead time
    Given a learned dead time of 60.0 minutes and a heating phase of 60.0 minutes
    And the indoor humidity is 50 %
    And the sky is clear
    When IHP computes the anticipation for 12:00
    Then the anticipation is 119.0 minutes

  Scenario: A clear sky before sunrise does not shorten the preheat
    Given a learned dead time of 60.0 minutes and a heating phase of 60.0 minutes
    And the sky is clear
    When IHP computes the anticipation for 07:00
    Then the anticipation is the same as under an overcast sky

  Scenario: A winter morning preheat ending before sunrise is no longer planned late
    Given a learned dead time of 85.8 minutes and a heating phase of 76.2 minutes
    And the indoor humidity is 60 %
    And the sky is clear
    When IHP computes the anticipation for 07:30
    Then the anticipation is 168.5 minutes

  Scenario: A heating phase half in daylight gets half the solar shortening
    Given a learned dead time of 0.0 minutes and a heating phase of 60.0 minutes
    And the sky is clear
    When IHP computes the anticipation for 08:20
    Then the anticipation is 62.0 minutes

  Scenario: Without sun data a clear sky does not shorten the preheat
    Given the sun position is unknown
    And a learned dead time of 30.0 minutes and a heating phase of 60.0 minutes
    And the sky is clear
    When IHP computes the anticipation for 12:00
    Then the anticipation is the same as under an overcast sky
