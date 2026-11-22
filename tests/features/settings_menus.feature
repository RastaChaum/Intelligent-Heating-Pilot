Feature: Device options grouped by theme
  As a user with several IHP devices
  I want to change one group of settings at a time
  So that I only see the fields that matter to what I am changing

  The options of a device open on a menu of themes. A theme is stored as soon as it is saved, and
  "Apply" reloads the device with what is stored. "Apply" is only offered while something is
  stored and not applied, and closing the dialog loses nothing.

  Background:
    Given an IHP device with a data retention of 30 days

  Scenario: Change one setting from its theme
    When I open the device options and choose the "learning" theme
    And I set the data retention to 60 days and save
    Then the options menu is shown again
    And the data retention stored for the device is 60 days
    And the device has not reloaded
    And the menu offers "Apply"
    When I choose "Apply"
    Then the device has reloaded once

  Scenario: Nothing to apply
    When I open the device options
    Then the menu does not offer "Apply"

  Scenario: Unapplied changes survive closing the dialog
    Given I saved a data retention of 60 days in the "learning" theme
    When I close the dialog and open the device options again
    Then the menu offers "Apply"
    And the data retention stored for the device is 60 days

  Scenario: Leaving a theme without saving changes nothing
    When I open the device options and choose the "learning" theme
    And I close the dialog and open the device options again
    Then the data retention stored for the device is 30 days
    And the menu does not offer "Apply"

  Scenario: The wake-up sources are still reachable
    When I open the device options and choose the "wake_up_sources" theme
    Then the wake-up sources menu is shown

  Scenario: A thermostat already used by another device is refused
    Given another IHP device drives "climate.bedroom"
    When I open the device options and choose the "thermostat_schedulers" theme
    And I submit the thermostat "climate.bedroom"
    Then the form stays open with the error "vtherm_already_configured"
    And the thermostat stored for the device is "climate.living"
