Feature: Preheat for a wake-up time given by an entity
  As a user whose life does not follow a fixed schedule
  I want IHP to warm the room for the time held by my phone's next alarm
  So that the room is ready when I wake up, and nothing is heated for an empty bed

  A wake-up source is an entity holding a point in time. The earliest valid deadline among the
  schedules and the sources wins. IHP applies the source's target to the thermostat itself.

  Background:
    Given the thermostat is in the "eco" preset at 18.0°C
    And it offers the presets "eco", "comfort" and "boost"

  Scenario: An alarm earlier than the schedule becomes the next deadline
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort"
    And the schedule has a block at 07:00 with the data preset "boost"
    And the source is set to 05:30 tomorrow
    When the anticipated start is reached
    Then the next deadline is at 05:30 tomorrow
    And the thermostat preset becomes "comfort"

  Scenario: The schedule is the next deadline again once the alarm has passed
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort"
    And the schedule has a block at 07:00 with the data preset "boost"
    And the source is set to 10 minutes ago
    When the anticipated start is reached
    Then the next deadline is at 07:00 tomorrow
    And the thermostat preset becomes "boost"
