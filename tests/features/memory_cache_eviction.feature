Feature: Memory Cache Eviction Strategy
  As a long-running IHP instance
  I want memory cache to be automatically evicted when it grows too large
  So that I prevent unbounded memory growth

  Background:
    Given a HeatingCycleLifecycleManager is configured
    And MAX_MEMORY_CACHE_ENTRIES is set to 50

  Scenario: Cache eviction when limit exceeded
    Given memory cache contains 50 cycles at the limit
    When a new cycle is added to the cache
    Then oldest cycle should be evicted
    And cache size should remain at 50
    And eviction should be logged

  Scenario: No eviction when under limit
    Given memory cache contains 40 cycles
    When a new cycle is added to the cache
    Then no eviction should occur
    And cache size should be 41

  Scenario: Eviction selects oldest entries by date
    Given memory cache contains 50 cycles
    And oldest cycle is from "2025-01-01"
    And newest cycle is from "2025-01-30"
    When a new cycle from "2025-02-01" is added
    Then cycle from "2025-01-01" should be evicted first
    And cycle from "2025-01-30" should remain in cache

  Scenario: Evicted data can be reloaded from persistent storage
    Given memory cache contains 50 cycles
    And a cycle from "2025-01-05" is evicted
    When the cycle from "2025-01-05" is requested again
    Then it should be loaded from IHeatingCycleStorage
    And it should be added back to memory cache
