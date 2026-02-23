Feature: Lazy Loading Contextual LHS at Startup

  Scenario: Startup loads only current hour contextual LHS
    Given a LhsLifecycleManager is created
    And the current time is 14:30
    When startup() is called
    Then only the current hour (14) contextual LHS is loaded from storage
    And storage.get_cached_contextual_lhs is called exactly once for hour 14
    And the other 23 hours are NOT loaded from storage
    And global LHS is loaded once
    And the LHS cache is initialized with only hour 14

  Scenario: Lazy loading - accessing non-loaded hour triggers storage read
    Given startup is complete with only current hour (10) loaded
    And hour 14 is not in memory cache
    When get_contextual_lhs() is called for hour 14
    Then storage is accessed to read contextual LHS for hour 14
    And the hour's contextual LHS is fetched from storage
    And cached in memory cache for subsequent calls

  Scenario: Memory cache prevents repeated storage reads
    Given startup is complete with only current hour (10) loaded
    And contextual LHS for hour 15 is cached in memory
    When get_contextual_lhs() is called for hour 15 multiple times (5 times)
    Then storage is accessed only once (first time)
    And subsequent calls return cached value from memory
    And no additional storage accesses occur

  Scenario: Lazy loading with no cached value triggers computation
    Given startup is complete with only current hour (10) loaded
    And hour 18 has no cached value in storage
    When get_contextual_lhs() is called for hour 18
    Then contextual LHS is computed using the cycles
    And computed value is cached in memory
    And storage is not accessed (cache miss, computation occurs)

  Scenario: ensure_contextual_lhs_populated handles lazy loading
    Given startup is complete with only current hour (10) loaded
    And hour 22 is not in memory cache
    When ensure_contextual_lhs_populated() is called for hour 22
    Then the hour's contextual LHS is loaded from storage (if exists)
    Or computed from cycles (if no storage cache)
    And cached in memory for subsequent calls

  Scenario: force_recalculate bypasses lazy load cache
    Given startup is complete with only current hour (10) loaded
    And hour 18 is cached in memory with stale value (3.5)
    When ensure_contextual_lhs_populated(force_recalculate=True) is called for hour 18
    Then memory cache is bypassed
    And storage cache is bypassed
    And contextual LHS is recomputed from cycles
    And fresh value is persisted and cached

  Scenario: Bulk operations load all 24 hours
    Given startup is complete with only current hour (10) loaded
    When on_retention_change(cycles) is called
    Then all 24 hours are recalculated
    And all hours are persisted to storage
    And memory cache is populated with all non-None values
    And subsequent calls to get_contextual_lhs() for any hour use memory (no storage access)

  Scenario: Startup at midnight loads hour 0
    Given the current time is 00:15 (midnight)
    When startup() is called
    Then only hour 0 contextual LHS is loaded
    And the cache contains only hour 0 entry

  Scenario: Startup at 23:00 loads hour 23
    Given the current time is 23:45 (late evening)
    When startup() is called
    Then only hour 23 contextual LHS is loaded
    And the cache contains only hour 23 entry

  Scenario: Concurrent access to different hours after lazy load
    Given startup is complete with only current hour (10) loaded
    When multiple tasks access different hours (5, 12, 18) concurrently
    Then each hour is loaded independently from storage
    And all requested hours are cached in memory
    And subsequent calls use memory cache (no storage access)
