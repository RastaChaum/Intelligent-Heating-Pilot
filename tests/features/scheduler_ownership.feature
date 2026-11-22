Feature: Scheduler ownership decides how a preheat is started
  As a user whose schedules come from different scheduler integrations
  I want IHP to know which integration owns each schedule
  So that it never sends a command that integration cannot receive

  Climate Scheduler imitates the HACS Scheduler attributes, so the look of an entity says
  nothing about its owner: Home Assistant's entity registry does.

  Scenario: A Climate Scheduler switch is never sent a HACS command
    Given a schedule switch "switch.living_room_plan" owned by "climate_scheduler"
    And HACS Scheduler is not installed
    When the anticipated start is reached
    Then no scheduler command is sent
    And no error is logged
    And the preheat is treated as computed only

  Scenario: A HACS Scheduler switch is still triggered
    Given a schedule switch "switch.living_room_plan" owned by "scheduler"
    When the anticipated start is reached
    Then the scheduler run action is triggered once for "switch.living_room_plan"

  Scenario: A schedule the registry does not know is computed only
    Given a schedule switch "switch.living_room_plan" that is not in the entity registry
    And HACS Scheduler is not installed
    When the anticipated start is reached
    Then no scheduler command is sent
    And no error is logged
    And the preheat is treated as computed only
