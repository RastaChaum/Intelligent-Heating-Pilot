Feature: Lazy Contextual LHS Population
  As a heating system
  I want contextual LHS to be populated only when needed
  So that I minimize unnecessary calculations and improve performance

  Background:
    Given a LhsLifecycleManager is configured
    And heating cycles are available for calculation

  Scenario: Contextual LHS populated on first request for specific hour
    Given no contextual LHS cache exists for hour 14
    When ensure_contextual_lhs_populated is called for hour 14
    Then LHS should be calculated for hour 14
    And result should be cached in memory
    And result should be persisted to storage

  Scenario: Memory cache hit avoids recalculation
    Given contextual LHS cache exists in memory for hour 10
    And the cached value is 2.5 degrees per hour
    When ensure_contextual_lhs_populated is called for hour 10 with force_recalculate=False
    Then no calculation should occur
    And existing cache value 2.5 should be returned

  Scenario: Storage cache hit loads into memory
    Given contextual LHS cache exists in storage for hour 18
    But memory cache is empty for hour 18
    When ensure_contextual_lhs_populated is called for hour 18
    Then LHS should be loaded from storage
    And result should be loaded into memory cache
    And no calculation should occur

  Scenario: Fallback to global LHS when no contextual data exists
    Given no contextual LHS data exists for hour 22
    When ensure_contextual_lhs_populated is called for hour 22
    Then global LHS should be returned as fallback
    And no error should occur

  Scenario: Force recalculate bypasses both memory and storage cache
    Given contextual LHS cache exists in memory for hour 15
    And storage also contains a cached value for hour 15
    When ensure_contextual_lhs_populated is called for hour 15 with force_recalculate=True
    Then LHS should be recalculated from fresh cycles
    And memory cache should be ignored (fresh calculation performed)
    And storage cache should be ignored (not queried)
    And fresh result should be persisted to storage
    And memory cache should be updated with fresh value
