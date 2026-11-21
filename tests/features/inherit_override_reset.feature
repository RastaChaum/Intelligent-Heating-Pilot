Feature: Inherit, override and reset a device value
  As a user
  I want to see which values a device inherits and to override or reset them
  So that I keep control of each device without repeating shared values

  Scenario: Reset an override to the central value
    Given a central data retention of 30 days
    And an IHP device that overrides its data retention with 90 days
    When I set the data retention of the device back to "inherit" and apply
    Then the device uses a data retention of 30 days

  Scenario: Override an inherited value
    Given a central data retention of 30 days
    And an IHP device that overrides nothing
    When I override the data retention of the device with 45 days
    Then the device uses a data retention of 45 days

  Scenario: Use no sensor while the central one is set
    Given a central outdoor temperature sensor "sensor.outdoor_a"
    And an IHP device that overrides nothing
    When I override the outdoor temperature sensor of the device with none
    Then the device uses no outdoor temperature sensor

  Scenario: The native schedule drive is never inherited
    Given a central configuration holding a native schedule drive of true
    And an IHP device that overrides nothing
    Then the device does not drive native schedules
