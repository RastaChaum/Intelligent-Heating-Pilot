Feature: ha-chauffage users get a real preheat
  As a user whose schedules come from ha-chauffage
  I want IHP to apply the next change at the anticipated start
  So that the room is warm when the change happens, with no extra automation

  ha-chauffage decides what happens and when: IHP only decides how early. Its "Next change"
  sensor gives the time of the next change and what it will send, named like a climate entity.

  Background:
    Given the thermostat is in the "eco" preset at 18.0°C
    And it offers the presets "eco", "comfort" and "boost"

  Scenario: A preset change is applied as a preset
    Given a ha-chauffage sensor whose next change at 18:00 is the "comfort" preset in heat mode
    When the anticipated start is reached
    Then the thermostat preset becomes "comfort"

  Scenario: A temperature change is applied as a temperature
    Given a ha-chauffage sensor whose next change at 18:00 is 21.0°C in heat mode
    When the anticipated start is reached
    Then the thermostat target becomes 21.0°C

  Scenario: A change that is not heating is never preheated
    Given a ha-chauffage sensor whose next change at 18:00 is the "comfort" preset in cool mode
    When the anticipated start is reached
    Then no command is sent to the thermostat

  Scenario: A sensor with no next change is never preheated
    Given a ha-chauffage sensor with no next change
    When the anticipated start is reached
    Then no command is sent to the thermostat

  Scenario: The application of the change by ha-chauffage is not fought
    Given a ha-chauffage sensor whose next change at 18:00 is 21.0°C in heat mode
    And the anticipated start is reached
    And ha-chauffage applies its change at the slot time
    When IHP recalculates
    Then IHP sends no new command
