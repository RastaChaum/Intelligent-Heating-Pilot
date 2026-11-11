Feature: A preheat starting before midnight reaches an after-midnight slot
  As a household whose HACS schedules only run on some weekdays
  I want a preheat that starts the evening before an early-morning slot to still heat the room
  So that a schedule that does not run today is not reported blocked by its own conditions (issue #250)

  # HACS Scheduler's run_action receives only a time ("05:00") and looks for
  # the timeslot at that time on the day it is called. Before midnight, a
  # schedule that does not run today has no such timeslot and does nothing.
  # IHP then retries the same scheduler just after midnight, once the slot's
  # day has started, before trying another scheduler.

  Background:
    Given the home is in the "Europe/Paris" time zone
    And the thermostat "climate.bedroom" currently targets 17.0°C
    And IHP anticipates each slot 6 hours ahead

  Scenario Outline: A schedule that does not run today is retried just after midnight
    Given a HACS scheduler "<scheduler>" running on "<days>" with a timeslot at 05:00 for 20.0°C
    And it is <now>
    When IHP recalculates and schedules anticipation
    Then the room's target temperature stays at 17.0°C
    And no scheduler is reported blocked this cycle
    And a retry of "<scheduler>" is planned at <retry>
    When the planned retry fires
    Then the room's target temperature becomes 20.0°C
    And IHP is preheating for "<scheduler>"

    Examples:
      | scheduler        | days                | now                     | retry            |
      | switch.weekdays  | mon,tue,wed,thu,fri | Sunday 2026-11-01 23:00 | 2026-11-02 00:01 |
      | switch.weekend   | sat,sun             | Friday 2026-11-06 23:00 | 2026-11-07 00:01 |

  Scenario: Another scheduler is not tried before the midnight retry
    Given a HACS scheduler "switch.weekdays" running on "mon,tue,wed,thu,fri" with a timeslot at 05:00 for 20.0°C
    And a HACS scheduler "switch.vacation" running on "mon,tue,wed,thu,fri,sat,sun" with a timeslot at 05:30 for 19.0°C
    And it is Sunday 2026-11-01 23:00
    When IHP recalculates and schedules anticipation
    Then "switch.vacation" is never triggered
    And no scheduler is reported blocked this cycle
    And a retry of "switch.weekdays" is planned at 2026-11-02 00:01
    When the planned retry fires
    Then the room's target temperature becomes 20.0°C
    And IHP is preheating for "switch.weekdays"
    And "switch.vacation" is never triggered

  Scenario: The retry after midnight is blocked by conditions, the next scheduler takes over
    Given a HACS scheduler "switch.weekdays" running on "mon,tue,wed,thu,fri" with a timeslot at 05:00 for 20.0°C
    And a HACS scheduler "switch.vacation" running on "mon,tue,wed,thu,fri,sat,sun" with a timeslot at 05:30 for 19.0°C
    And "switch.weekdays" is blocked by its own conditions when triggered
    And it is Sunday 2026-11-01 23:00
    When IHP recalculates and schedules anticipation
    Then "switch.vacation" is never triggered
    And a retry of "switch.weekdays" is planned at 2026-11-02 00:01
    When the planned retry fires
    Then the room's target temperature becomes 19.0°C
    And IHP is preheating for "switch.vacation"

  Scenario: A schedule that runs every day starts preheating before midnight (no regression)
    Given a HACS scheduler "switch.daily" running on "mon,tue,wed,thu,fri,sat,sun" with a timeslot at 05:00 for 20.0°C
    And it is Sunday 2026-11-01 23:00
    When IHP recalculates and schedules anticipation
    Then the room's target temperature becomes 20.0°C
    And IHP is preheating for "switch.daily"
    And no retry is planned

  Scenario: A schedule blocked by its own conditions on the slot's day still falls back at once
    Given a HACS scheduler "switch.non_vacation" running on "mon,tue,wed,thu,fri,sat,sun" with a timeslot at 05:00 for 20.0°C
    And a HACS scheduler "switch.vacation" running on "mon,tue,wed,thu,fri,sat,sun" with a timeslot at 05:30 for 19.0°C
    And "switch.non_vacation" is blocked by its own conditions when triggered
    And it is Monday 2026-11-02 00:30
    When IHP recalculates and schedules anticipation
    Then the room's target temperature becomes 19.0°C
    And IHP is preheating for "switch.vacation"
    And the blocked schedulers for this cycle are "switch.non_vacation"
    And no retry is planned
