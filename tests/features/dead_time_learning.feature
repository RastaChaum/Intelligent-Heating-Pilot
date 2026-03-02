Feature: Dead Time Learning and Sensor Display
  As a heating system operator
  I want the system to learn dead time from heating cycles
  And display the effective dead time (learned or configured)
  So that preheating is accurately calibrated based on actual system behavior

  Background:
    Given a HeatingApplication is initialized with a device
    And the device has auto_learning enabled
    And the device has configured dead_time of 5.0 minutes

  Scenario: Learn dead time from cycles when auto_learning is enabled
    Given a heating cycle with dead_time_cycle_minutes of 8.0
    And another heating cycle with dead_time_cycle_minutes of 7.5
    When cycles are processed by the lifecycle manager
    Then the learned dead_time should be 7.75 minutes (average)
    And the learned value should persist to storage

  Scenario: Use configured dead time when auto_learning is disabled
    Given auto_learning is disabled
    And a heating cycle with dead_time_cycle_minutes of 8.0
    When cycles are processed
    Then get_effective_dead_time() returns 5.0 (configured value)
    And no learning occurs

  Scenario: Sensor displays learned dead time when available
    Given cycles have been processed with learned dead_time of 6.5
    And auto_learning is enabled
    When the dead time sensor updates
    Then sensor native_value should be 6.5

  Scenario: Sensor displays configured dead time as fallback
    Given no cycles have been processed yet (no learned value)
    And the configured dead_time is 5.0
    When the dead time sensor updates
    Then sensor native_value should be 5.0

  Scenario: Sensor displays auto_learning flag in attributes
    Given a dead time sensor exists
    And auto_learning is enabled
    When the sensor's extra_state_attributes is read
    Then attributes should include auto_learning: true

  Scenario: Learned dead time persists across Home Assistant restart
    Given cycles have been processed with learned dead_time of 6.5
    And the value is saved to ILhsStorage
    When Home Assistant is restarted
    And get_learned_dead_time() is called
    Then it returns 6.5

  Scenario: Fallback when learned value is None after restart
    Given no learned dead_time was ever saved
    And get_learned_dead_time() returns None
    When get_effective_dead_time() is called with fallback
    Then it returns the configured dead_time_minutes

  Scenario: Zero dead times are handled correctly
    Given a heating cycle with dead_time_cycle_minutes of 0.0
    And another heating cycle with dead_time_cycle_minutes of None
    When cycles are processed
    Then calculate_average_dead_time returns None (no valid data)
    And no learning occurs
