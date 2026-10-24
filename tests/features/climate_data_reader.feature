Feature: HAClimateDataReader - Unified Climate Data Access
  As the IHP system
  I need a unified adapter for climate data
  So that I can read both historical data and real-time state from a single VTherm entity

  Background:
    Given a Home Assistant instance is running
    And a RecorderAccessQueue is available
    And a VTherm entity "climate.living_room" exists

  Scenario: HAClimateDataReader implements both historical and real-time interfaces
    When I create a HAClimateDataReader with the VTherm entity and RecorderQueue
    Then it should implement IHistoricalDataAdapter interface
    And it should implement IClimateDataReader interface
    And it should store the VTherm entity ID

  Scenario: Historical data fetch uses RecorderQueue for synchronization
    Given I have a HAClimateDataReader with RecorderQueue
    When I call fetch_historical_data for indoor temperature
    Then the RecorderQueue lock should be acquired
    And the lock should be released after data fetch completes
    And historical data should be returned

  Scenario: Real-time slope reading does NOT use RecorderQueue
    Given I have a HAClimateDataReader with RecorderQueue
    And the VTherm has a current slope of 0.75
    When I call get_current_slope
    Then the RecorderQueue lock should NOT be acquired
    And it should return 0.75

  Scenario: Real-time heating state does NOT use RecorderQueue
    Given I have a HAClimateDataReader with RecorderQueue
    And the VTherm is actively heating
    When I call is_heating_active
    Then the RecorderQueue lock should NOT be acquired
    And it should return True

  Scenario: VTherm entity ID is accessible
    Given I have a HAClimateDataReader for "climate.bedroom"
    When I call get_vtherm_entity_id
    Then it should return "climate.bedroom"

  Scenario: RecorderQueue is mandatory for construction
    When I try to create a HAClimateDataReader without RecorderQueue
    Then a TypeError should be raised
    And the error should indicate missing required parameter
