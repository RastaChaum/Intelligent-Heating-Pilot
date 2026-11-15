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

  Scenario: A wake-up source drives the thermostat without any scheduler
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort"
    And the source is set to 06:30 tomorrow
    When the anticipated start is reached
    Then the next deadline is at 06:30 tomorrow
    And the thermostat preset becomes "comfort"

  Scenario: The earlier state is put back after the hold
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort" and a hold of 90 minutes
    And the source is set to 06:30 tomorrow
    When the anticipated start is reached
    And the wake-up time has passed
    Then the thermostat preset is still "comfort"
    When the hold ends
    Then the thermostat preset becomes "eco"

  Scenario: A manual change during the hold is kept
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort" and a hold of 90 minutes
    And the source is set to 06:30 tomorrow
    When the anticipated start is reached
    And the wake-up time has passed
    And somebody sets the thermostat to the "boost" preset
    And the hold ends
    Then the thermostat preset is still "boost"
    And the thermostat was never restored

  Scenario: Without a hold the thermostat is left as it is after the wake-up time
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort"
    And the source is set to 06:30 tomorrow
    When the anticipated start is reached
    And the wake-up time has passed
    And the hold ends
    Then the thermostat preset is still "comfort"
    And the thermostat was never restored

  Scenario: A schedule slot reached during the hold ends it without a restore
    Given a wake-up source "sensor.phone_next_alarm" with the target preset "comfort" and a hold of 120 minutes
    And the schedule has a block at 07:30 with the data preset "comfort"
    And the source is set to 06:30 tomorrow
    When the anticipated start is reached
    And the wake-up time has passed
    And the hold ends
    Then the thermostat preset is still "comfort"
    And the thermostat was never restored
