Feature: Central default configuration
  As a user with several IHP devices
  I want to set the shared values once
  So that every device follows them unless it has its own

  A device uses its own value when it has one, else the central value, else the built-in
  default. Applying a central change reloads only the devices that inherit a changed value.

  Scenario: A central value reaches devices that do not override it
    Given two IHP devices that override no setting
    And a central outdoor temperature sensor "sensor.outdoor_a"
    When I change the central outdoor temperature sensor to "sensor.outdoor_b"
    Then both devices use "sensor.outdoor_b"

  Scenario: A device that overrides a value keeps it
    Given two IHP devices that override no setting
    And the second device overrides the data retention with 90 days
    And a central data retention of 30 days
    When I change the central data retention to 60 days
    Then the first device uses a data retention of 60 days
    And the second device uses a data retention of 90 days

  Scenario: Without a central configuration devices behave as before
    Given two IHP devices that override no setting
    And no central configuration
    Then both devices use the built-in data retention of 30 days

  Scenario: Applying reloads only the devices that inherit the changed value
    Given two IHP devices that override no setting
    And the second device overrides the data retention with 90 days
    And a central data retention of 30 days
    When I change the central data retention to 60 days and apply
    Then only the first device is reloaded

  Scenario: A device created before the feature keeps its values
    Given a device created before the central configuration with a data retention of 45 days
    And a central data retention of 60 days
    Then that device uses a data retention of 45 days

  Scenario: Device creation stores no shareable value
    When a device is created with a name, a thermostat and schedulers
    Then the device stores only those three values
