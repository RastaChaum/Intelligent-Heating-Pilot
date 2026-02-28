Feature: HASensorDataReader - Sensor Historical Data Access
  As the IHP system
  I need to access historical sensor data through a unified interface
  So that I can analyze temperature and humidity trends with proper synchronization

  Background:
    Given a Home Assistant instance is running
    And a RecorderAccessQueue is available
    And a sensor entity "sensor.outdoor_temperature" exists

  Scenario: HASensorDataReader requires RecorderQueue for construction
    When I create a HASensorDataReader with RecorderQueue
    Then it should be successfully instantiated
    And it should implement IHistoricalDataAdapter interface

  Scenario: Historical data fetch uses RecorderQueue for synchronization
    Given I have a HASensorDataReader with RecorderQueue
    When I call fetch_historical_data for outdoor temperature
    Then the RecorderQueue lock should be acquired
    And the lock should be released after data fetch completes
    And historical data should be returned

  Scenario: RecorderQueue is mandatory for HASensorDataReader
    When I try to create a HASensorDataReader without RecorderQueue
    Then a TypeError should be raised
    And the error should indicate missing required parameter

  Scenario: Multiple readers share the same RecorderQueue
    Given I have a RecorderQueue instance
    When I create multiple HASensorDataReader instances with the same queue
    Then all readers should use the same RecorderQueue instance
    And concurrent fetch operations should be serialized
