Feature: Memory Cache Eviction Strategy
  As a long-running IHP instance
  I want memory cache to be automatically evicted when it grows too large
  So that I prevent unbounded memory growth

  Background:
    Given a HeatingCycleLifecycleManager is configured
    And MAX_MEMORY_CACHE_ENTRIES is set to 50

  Scenario: No eviction when under limit
    Given memory cache contains 40 cycles
    When a new cycle is added to the cache
    Then no eviction should occur
    And cache size should be 41

  Scenario: Cache eviction when limit exceeded
    Given memory cache is full with 50 cycles
    When a new cycle is added (exceeding the limit)
    Then eviction should be triggered
    And exactly 1 entry should be removed to bring cache back to 50
    And cache size should return to MAX_MEMORY_CACHE_ENTRIES

  Scenario: Eviction selects oldest entries by date
    Given memory cache contains 50 cycles with dates ranging from oldest to newest
    When a new cycle with the newest date is added (exceeding limit)
    Then eviction is triggered
    And the oldest cycle (by date) should be removed
    And all newer cycles should be preserved in the cache
    And the cache maintains FIFO (First In, First Out) order

  Scenario: Evicted data can be reloaded from persistent storage
    Given memory cache contains 50 cycles
    And a cycle from "2025-01-05" is evicted
    When the cycle from "2025-01-05" is requested again
    Then it should be loaded from IHeatingCycleStorage
    And it should be added back to memory cache
