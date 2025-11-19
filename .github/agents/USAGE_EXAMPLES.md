# Custom Agent Usage Examples

This document provides real-world examples of how to effectively delegate tasks to the custom agents in the Intelligent Heating Pilot project.

## Example 1: Refactoring Legacy Code with DDD Architecture Expert

### Scenario
You have a legacy coordinator class that mixes business logic with Home Assistant integration code, and you want to refactor it to follow DDD principles.

### How to Delegate

**In GitHub Copilot Chat:**
```
@workspace I need to refactor the IntelligentHeatingPilotCoordinator class to follow 
strict DDD architecture. Currently, it has Home Assistant dependencies mixed with 
business logic. Please:

1. Identify all business logic in the coordinator
2. Extract it to appropriate domain services
3. Create necessary interfaces for external dependencies
4. Implement infrastructure adapters
5. Keep the coordinator as a thin orchestration layer

Delegate this to the DDD Architecture Expert agent.
```

### Expected Agent Actions

The DDD Architecture Expert would:
1. Analyze the coordinator code
2. Identify business logic (e.g., anticipation calculations, scheduling decisions)
3. Create domain interfaces for dependencies
4. Extract pure business logic to domain services
5. Create infrastructure adapters implementing interfaces
6. Refactor coordinator to just wire dependencies
7. Provide tests for each layer
8. Ensure zero `homeassistant.*` imports in domain

### Result
- Clean separation of concerns
- Testable business logic without HA
- Maintainable infrastructure adapters
- Backward compatible refactoring

---

## Example 2: Adding Weather Forecast Support with Cloud Integration Expert

### Scenario
You want to add weather forecast integration to improve heating predictions by anticipating weather changes in the next 6 hours.

### How to Delegate

**In GitHub Copilot Chat:**
```
@workspace I want to add weather forecast integration to predict heating needs 
based on upcoming weather changes. The system should:

1. Integrate with Home Assistant weather entities
2. Read 6-hour weather forecast
3. Adjust anticipation time based on predicted temperature drops
4. Handle missing/stale forecast data gracefully
5. Add appropriate tests

Delegate this to the Cloud Integration Expert agent.
```

### Expected Agent Actions

The Cloud Integration Expert would:
1. Create `WeatherForecast` value object in domain layer
2. Define `IWeatherForecastProvider` interface
3. Implement `HAWeatherForecastAdapter` in infrastructure
4. Add forecast-based correction algorithm to `PredictionService`
5. Handle API failures with sensible fallbacks
6. Add configuration option for weather entity
7. Create tests with mocked forecast data
8. Document the forecast algorithm with formulas

### Result
- Weather forecast integration following DDD
- Graceful degradation if forecast unavailable
- Well-tested with various weather scenarios
- Optional feature (doesn't break existing setups)

---

## Example 3: Creating a New Environmental Factor with Both Agents

### Scenario
You want to add wind speed as a new environmental factor affecting heating predictions (wind increases heat loss).

### How to Delegate

**Step 1 - Domain Logic (DDD Expert):**
```
@workspace I need to add wind speed as an environmental factor in heating predictions.
Please:

1. Add wind_speed to EnvironmentState value object
2. Create algorithm in PredictionService to calculate wind correction factor
3. Add unit tests for the wind correction algorithm
4. Document the formula with physical reasoning

Delegate to the DDD Architecture Expert.
```

**Step 2 - Infrastructure Integration (Cloud Expert):**
```
@workspace Now that we have the domain logic for wind speed, I need to integrate
it with Home Assistant. Please:

1. Update HAEnvironmentReader to read wind speed from HA entity
2. Add wind_speed_entity configuration option
3. Handle missing wind speed data gracefully (use default)
4. Add infrastructure tests with mocked HA entities

Delegate to the Cloud Integration Expert.
```

### Expected Results

**From DDD Expert:**
- Updated `EnvironmentState` dataclass
- Wind correction algorithm in `PredictionService`
- Domain tests for wind calculations
- Formula documentation

**From Cloud Expert:**
- Updated `HAEnvironmentReader` adapter
- Configuration flow changes
- Infrastructure tests
- Fallback handling

### Result
- Complete end-to-end feature
- Proper layer separation maintained
- Comprehensive testing
- Graceful degradation

---

## Example 4: Code Review with DDD Architecture Expert

### Scenario
You've made changes to the domain layer and want to ensure they comply with DDD principles before submitting a PR.

### How to Delegate

**In GitHub Copilot Chat:**
```
@workspace Please review my recent changes to the domain/services/prediction_service.py
file for DDD compliance. Check for:

1. No Home Assistant imports
2. Pure business logic only
3. Proper interface usage
4. Type hints completeness
5. Test coverage

Delegate to the DDD Architecture Expert for review.
```

### Expected Agent Actions

The agent would:
1. Scan for `homeassistant.*` imports
2. Identify any infrastructure concerns in domain code
3. Check that all external interactions use interfaces
4. Verify type hints are complete
5. Check if corresponding tests exist
6. Provide specific feedback on violations
7. Suggest improvements

### Result
- Comprehensive architectural review
- Clear list of issues to fix
- Suggestions for improvement
- Confidence in DDD compliance

---

## Example 5: Optimizing Weather API Calls with Cloud Integration Expert

### Scenario
Your weather integration is making too many API calls and you need to implement proper caching.

### How to Delegate

**In GitHub Copilot Chat:**
```
@workspace The HAWeatherAdapter is making too many API calls. Please implement
a caching strategy that:

1. Caches weather data for 5 minutes minimum
2. Handles stale cache gracefully
3. Logs cache hits/misses
4. Provides cache statistics
5. Tests the caching behavior

Delegate to the Cloud Integration Expert.
```

### Expected Agent Actions

The agent would:
1. Add cache mechanism to adapter
2. Implement time-based cache invalidation
3. Add logging for debugging
4. Handle edge cases (None values, errors)
5. Create tests for cache behavior
6. Document caching strategy
7. Ensure thread safety if needed

### Result
- Reduced API calls
- Better performance
- Proper cache management
- Tested caching behavior

---

## Best Practices for Delegation

### 1. Be Specific
❌ **Bad:** "Fix the code"
✅ **Good:** "Refactor HASchedulerReader to implement ISchedulerReader interface and move business logic to domain layer"

### 2. Provide Context
Always mention:
- Which files are involved
- What the current problem is
- What the desired outcome should be
- Any specific constraints

### 3. Break Down Complex Tasks
For large refactorings:
1. Start with interfaces (DDD Expert)
2. Then adapters (appropriate expert)
3. Then integration (both if needed)
4. Finally, tests and documentation

### 4. Use Multiple Agents When Appropriate
Some tasks span multiple domains:
- **Domain logic** → DDD Expert
- **Weather integration** → Cloud Expert
- **API optimization** → Cloud Expert
- **Architecture review** → DDD Expert

### 5. Review Agent Output
Always:
- ✅ Review the suggested code
- ✅ Run tests
- ✅ Check for edge cases
- ✅ Ensure it fits your specific needs
- ✅ Ask follow-up questions if unclear

### 6. Iterate
If the first response isn't perfect:
- Provide more context
- Ask clarifying questions
- Request specific improvements
- Try rephrasing your request

---

## Common Delegation Patterns

### Pattern 1: New Feature (Full Stack)
```
1. DDD Expert: Design domain model and business logic
2. DDD Expert: Create interfaces for external dependencies
3. Cloud Expert (if weather-related): Implement adapters
4. DDD Expert: Review for architectural compliance
```

### Pattern 2: Bug Fix in Domain
```
1. DDD Expert: Analyze the bug in domain logic
2. DDD Expert: Fix the algorithm with tests
3. DDD Expert: Ensure no architecture violations introduced
```

### Pattern 3: Performance Optimization
```
1. Cloud Expert: Analyze API call patterns
2. Cloud Expert: Implement caching/optimization
3. DDD Expert: Ensure optimization doesn't violate DDD
```

### Pattern 4: Legacy Code Refactoring
```
1. DDD Expert: Analyze current architecture violations
2. DDD Expert: Plan migration strategy
3. DDD Expert: Execute refactoring incrementally
4. DDD Expert: Verify tests and backward compatibility
```

---

## Troubleshooting

### Agent Not Understanding Context
**Solution:** Provide more specific files and code snippets

### Agent Violating Architecture
**Solution:** Explicitly mention architectural constraints in your request

### Agent's Code Doesn't Work
**Solution:** 
1. Check if you provided enough context
2. Review the code for your specific setup
3. Ask the agent to fix specific issues
4. Consider if you need a different agent

### Need Both Agents
**Solution:** Delegate sequentially - domain logic first, then infrastructure

---

## Remember

Custom agents are assistants, not replacements for your judgment. Always:
- Review their suggestions critically
- Test thoroughly
- Ensure the solution fits your needs
- Don't blindly accept code without understanding it
- Iterate and refine until you're satisfied

Happy delegating! 🚀
