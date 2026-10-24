Feature: Cache Cascade Error Isolation
  As a heating system operator
  I want LHS updates to be isolated from each other
  So that one failing calculation doesn't prevent the other from completing

  Background:
    Given a HeatingCycleLifecycleManager is configured
    And a LhsLifecycleManager is attached for cascade updates

  Scenario: Global LHS update fails but contextual LHS succeeds
    Given a heating cycle has completed
    And global LHS calculation throws an error
    When cascade triggers LHS updates
    Then contextual LHS should still be calculated
    And no exception should propagate to caller
    And an error should be logged for global LHS failure

  Scenario: Contextual LHS update fails but global LHS succeeds
    Given a heating cycle has completed
    And contextual LHS calculation throws an error
    When cascade triggers LHS updates
    Then global LHS should still be calculated
    And no exception should propagate to caller
    And an error should be logged for contextual LHS failure

  Scenario: Both global and contextual LHS updates fail
    Given a heating cycle has completed
    And global LHS calculation throws an error
    And contextual LHS calculation throws an error
    When cascade triggers LHS updates
    Then no exception should propagate to caller
    And errors should be logged for both failures

  Scenario: Both LHS updates succeed
    Given a heating cycle has completed
    And no errors occur during calculation
    When cascade triggers LHS updates
    Then global LHS should be updated
    And contextual LHS should be updated
    And no errors should be logged
