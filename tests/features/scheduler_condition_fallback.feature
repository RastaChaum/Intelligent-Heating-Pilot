Feature: Anticipation falls back to the next scheduler when one is blocked
  As a household with several scheduler entities routed by a condition
  (e.g. a vacation calendar and a non-vacation calendar)
  I want IHP to still heat on time through whichever scheduler can actually act
  So that a blocked scheduler's own conditions never leave the room cold until
  its slot time has simply elapsed (issue #64)

  Background:
    Given the thermostat "climate.living_room" currently targets 17.0°C
    # Timeslots are close together so both fall in the "anticipated start already
    # past, target still ahead" window IHP is checked at - exercising the
    # synchronous (immediate-trigger) fallback path within one recalculation.
    # The timer-fired retry path (same mechanism, different trigger) is covered
    # by the ScheduleAnticipationActionUseCase and HeatingOrchestrator unit tests.

  Scenario: The earliest scheduler is blocked by its own conditions, the next one takes over
    Given a HACS scheduler "switch.non_vacation" with its next timeslot at 07:00 for 20.0°C
    And a HACS scheduler "switch.vacation" with its next timeslot at 07:03 for 20.0°C
    And "switch.non_vacation" is blocked by its own conditions when triggered
    When IHP recalculates and schedules anticipation for "switch.non_vacation"
    Then the attempt on "switch.non_vacation" is confirmed blocked
    And IHP retries and succeeds with "switch.vacation" within the same cycle
    And the room's target temperature becomes 20.0°C
    And the anticipation data reports no scheduler blocked overall
    And the blocked schedulers for this cycle are "switch.non_vacation"

  Scenario: Every configured scheduler is blocked
    Given a HACS scheduler "switch.non_vacation" with its next timeslot at 07:00 for 20.0°C
    And a HACS scheduler "switch.vacation" with its next timeslot at 07:03 for 20.0°C
    And "switch.non_vacation" is blocked by its own conditions when triggered
    And "switch.vacation" is blocked by its own conditions when triggered
    When IHP recalculates and schedules anticipation for "switch.non_vacation"
    Then the room's target temperature stays at 17.0°C
    And the anticipation data reports every scheduler blocked overall
    And the blocked schedulers for this cycle are "switch.non_vacation, switch.vacation"

  Scenario: A single scheduler whose conditions hold is triggered normally (no regression)
    Given a HACS scheduler "switch.non_vacation" with its next timeslot at 07:00 for 20.0°C
    When IHP recalculates and schedules anticipation for "switch.non_vacation"
    Then the room's target temperature becomes 20.0°C
    And the anticipation data reports no scheduler blocked overall

  Scenario: A single scheduler whose conditions are blocked has no fallback candidate
    Given a HACS scheduler "switch.non_vacation" with its next timeslot at 07:00 for 20.0°C
    And "switch.non_vacation" is blocked by its own conditions when triggered
    When IHP recalculates and schedules anticipation for "switch.non_vacation"
    Then the room's target temperature stays at 17.0°C
    And the anticipation data reports every scheduler blocked overall
    And the blocked schedulers for this cycle are "switch.non_vacation"

  # Issue #256: scheduler-component returns from run_action before the thermostat
  # has applied the action. IHP must wait for the thermostat before reporting the
  # scheduler blocked.

  Scenario: The thermostat applies the action a moment after run_action returns
    Given the thermostat applies a triggered action a moment after run_action returns
    And a HACS scheduler "switch.weekend" with its next timeslot at 07:00 for 20.0°C
    And a HACS scheduler "switch.weekday" with its next timeslot at 07:03 for 19.0°C
    When IHP recalculates and schedules anticipation for "switch.weekend"
    Then the room's target temperature becomes 20.0°C
    And IHP is preheating for "switch.weekend"
    And "switch.weekday" is never triggered
    And the anticipation data reports no scheduler blocked overall
    And no scheduler is reported blocked this cycle

  Scenario: A blocked scheduler still falls back when the thermostat applies actions with a delay
    Given the thermostat applies a triggered action a moment after run_action returns
    And a HACS scheduler "switch.non_vacation" with its next timeslot at 07:00 for 20.0°C
    And a HACS scheduler "switch.vacation" with its next timeslot at 07:03 for 20.0°C
    And "switch.non_vacation" is blocked by its own conditions when triggered
    When IHP recalculates and schedules anticipation for "switch.non_vacation"
    Then the attempt on "switch.non_vacation" is confirmed blocked
    And IHP retries and succeeds with "switch.vacation" within the same cycle
    And the room's target temperature becomes 20.0°C
    And the blocked schedulers for this cycle are "switch.non_vacation"
