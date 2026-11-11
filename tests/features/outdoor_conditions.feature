Feature: Outdoor conditions reach the preheating prediction
  As a user who configured an outdoor source
  I want IHP to read outdoor conditions from a sensor or a weather entity
  So that the preheating prediction sees the weather it was configured with

  Scenario: An outdoor temperature sensor is used by the prediction
    Given the outdoor temperature source is "sensor.outdoor_temperature"
    And "sensor.outdoor_temperature" reports 5.0 "°C"
    When IHP reads the current environment
    Then the outdoor temperature is 5.0 °C

  Scenario: A weather entity feeds every outdoor value
    Given the outdoor temperature source is "weather.home"
    And the outdoor humidity source is "weather.home"
    And the cloud coverage source is "weather.home"
    And "weather.home" is "cloudy" with temperature 7.5 "°C", humidity 80 and cloud coverage 90
    When IHP reads the current environment
    Then the outdoor temperature is 7.5 °C
    And the outdoor humidity is 80
    And the cloud coverage is 90

  Scenario: A Fahrenheit weather entity is converted to Celsius
    Given the outdoor temperature source is "weather.home"
    And "weather.home" is "sunny" with temperature 41.0 "°F", humidity 50 and cloud coverage 0
    When IHP reads the current environment
    Then the outdoor temperature is 5.0 °C

  Scenario: Without an outdoor source the outdoor temperature stays unknown
    When IHP reads the current environment
    Then the outdoor temperature is unknown

  Scenario: Each heating cycle records the outdoor temperature it ran in
    Given the outdoor temperature source is "sensor.outdoor_temperature"
    And its history reads 4.0 °C from 05:30 then 6.0 °C from 06:20
    And the room heated from 06:10 to 06:35
    When IHP extracts the heating cycles
    Then the cycle records an average outdoor temperature of 5.2 °C

  Scenario: A cold morning does not make IHP start heating hours early
    Given the room is at 18.0 °C and must reach 21.0 °C in 2 hours
    And the learned heating slope is 2.0 °C per hour
    When it is 0.0 °C outside
    Then IHP waits instead of starting to heat now

  Scenario: Outdoor temperature changes do not trigger a recalculation
    Given the outdoor temperature source is "sensor.outdoor_temperature"
    And the outdoor humidity source is "sensor.outdoor_humidity"
    When IHP starts monitoring its outdoor sources
    Then IHP listens to "sensor.outdoor_humidity"
    And IHP does not listen to "sensor.outdoor_temperature"

  Scenario: A cooling weather entity does not trigger a recalculation
    Given IHP monitors the outdoor source "weather.home"
    When "weather.home" goes from 10.0 °C to 2.0 °C with the same humidity and cloud coverage
    Then no recalculation is triggered
