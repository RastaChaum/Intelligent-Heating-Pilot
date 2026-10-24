Feature: HAWeatherDataReader - Weather Historical Data Access
  As the IHP system
  I need to access historical weather data through a unified interface
  So that I can analyze outdoor conditions with proper synchronization

  Background:
    Given a Home Assistant instance is running
    And a RecorderAccessQueue is available
    And a weather entity "weather.home" exists

  Scenario: HAWeatherDataReader requires RecorderQueue for construction
    When I create a HAWeatherDataReader with RecorderQueue
    Then it should be successfully instantiated
    And it should implement IHistoricalDataAdapter interface

  Scenario: Historical data fetch uses RecorderQueue for synchronization
    Given I have a HAWeatherDataReader with RecorderQueue
    When I call fetch_historical_data for outdoor temperature
    Then the RecorderQueue lock should be acquired
    And the lock should be released after data fetch completes
    And historical data should be returned

  Scenario: RecorderQueue is mandatory for HAWeatherDataReader
    When I try to create a HAWeatherDataReader without RecorderQueue
    Then a TypeError should be raised
    And the error should indicate missing required parameter

  Scenario: RecorderQueue serializes access across all weather readers
    Given I have a RecorderQueue instance
    When I create multiple HAWeatherDataReader instances with the same queue
    Then all readers should use the same RecorderQueue instance
    And concurrent fetch operations should be serialized in FIFO order
