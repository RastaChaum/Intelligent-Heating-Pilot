# Custom Agents Quick Reference Card

Quick commands for delegating to specialized agents in the Intelligent Heating Pilot project.

## 🏛️ DDD Architecture Expert

**When to use:** Domain refactoring, architectural compliance, interface design

### Quick Commands

```bash
# Refactor to DDD
"@workspace Refactor [CLASS_NAME] to follow DDD architecture. Delegate to DDD Expert."

# Create interface
"@workspace Create domain interface for [FUNCTIONALITY]. Delegate to DDD Expert."

# Extract business logic
"@workspace Extract business logic from [FILE] to domain layer. Delegate to DDD Expert."

# Code review
"@workspace Review [FILE] for DDD compliance. Delegate to DDD Expert."

# Fix architecture violation
"@workspace Remove Home Assistant imports from domain layer in [FILE]. Delegate to DDD Expert."
```

### Checklist for DDD Expert Tasks
- [ ] No `homeassistant.*` imports in domain layer
- [ ] Interfaces defined as ABCs
- [ ] Value objects are immutable (`frozen=True`)
- [ ] Complete type hints
- [ ] Business logic in domain, not infrastructure
- [ ] Tests exist and pass

---

## ☁️ Cloud Integration Expert

**When to use:** Weather integration, environmental sensors, API optimization

### Quick Commands

```bash
# Add weather sensor
"@workspace Add [SENSOR_TYPE] support to environment reader. Delegate to Cloud Expert."

# Weather algorithm
"@workspace Implement [WEATHER_FACTOR] correction in predictions. Delegate to Cloud Expert."

# API integration
"@workspace Integrate [WEATHER_API] for forecast data. Delegate to Cloud Expert."

# Optimize calls
"@workspace Add caching to [ADAPTER_NAME] to reduce API calls. Delegate to Cloud Expert."

# Handle failures
"@workspace Improve error handling in [WEATHER_ADAPTER]. Delegate to Cloud Expert."
```

### Checklist for Cloud Expert Tasks
- [ ] Weather algorithms in domain layer (pure functions)
- [ ] Adapters in infrastructure layer
- [ ] Graceful fallback for missing data
- [ ] API rate limiting/caching implemented
- [ ] Tests with mocked weather data
- [ ] Formulas documented with citations

---

## 🎯 Common Scenarios

### Scenario 1: New Environmental Factor
```
Step 1 (DDD Expert): Add value object and domain algorithm
Step 2 (Cloud Expert): Implement infrastructure adapter
Step 3 (DDD Expert): Review for compliance
```

### Scenario 2: Refactor Legacy Code
```
Step 1 (DDD Expert): Analyze violations
Step 2 (DDD Expert): Create interfaces
Step 3 (DDD Expert): Extract domain logic
Step 4 (DDD Expert): Implement adapters
Step 5 (DDD Expert): Verify tests
```

### Scenario 3: Add Weather Forecast
```
Step 1 (Cloud Expert): Design forecast integration
Step 2 (Cloud Expert): Implement adapter
Step 3 (Cloud Expert): Add prediction algorithm
Step 4 (DDD Expert): Review architecture
```

### Scenario 4: Performance Optimization
```
Step 1 (Cloud Expert): Add caching strategy
Step 2 (Cloud Expert): Implement rate limiting
Step 3 (DDD Expert): Ensure no architecture violations
```

---

## 📋 Agent Capabilities Matrix

| Task | DDD Expert | Cloud Expert |
|------|------------|--------------|
| Domain refactoring | ✅ Primary | ❌ |
| Interface design | ✅ Primary | ❌ |
| Weather integration | ❌ | ✅ Primary |
| API optimization | ❌ | ✅ Primary |
| Environmental algorithms | ✅ Primary | ✅ Support |
| Code review (architecture) | ✅ Primary | ❌ |
| Code review (weather) | ❌ | ✅ Primary |
| Test design | ✅ All layers | ✅ Weather tests |
| Migration planning | ✅ Primary | ❌ |
| Error handling | ✅ Domain | ✅ API/Weather |

---

## 🚀 Pro Tips

### Tip 1: Be Specific
❌ "Fix the code"
✅ "Remove HA imports from domain/services/prediction_service.py"

### Tip 2: One Task per Agent
❌ "Refactor everything and add weather support"
✅ First: "Refactor to DDD" → Then: "Add weather support"

### Tip 3: Provide Context
Always mention:
- Specific files
- Current problem
- Desired outcome
- Constraints

### Tip 4: Sequential for Complex Tasks
```
1. Design domain model (DDD Expert)
2. Create interfaces (DDD Expert)
3. Implement adapters (appropriate expert)
4. Review (DDD Expert)
```

### Tip 5: Verify Results
After delegation:
- [ ] Review the code
- [ ] Run tests
- [ ] Check edge cases
- [ ] Ensure it fits your needs

---

## ⚠️ Common Pitfalls

### Pitfall 1: Wrong Agent
❌ Asking DDD Expert to implement weather API
✅ DDD Expert for domain logic, Cloud Expert for weather API

### Pitfall 2: Vague Request
❌ "Make it better"
✅ "Extract calculation logic to PredictionService following DDD"

### Pitfall 3: Too Much at Once
❌ "Refactor all coordinators and add all weather features"
✅ Break into smaller, focused tasks

### Pitfall 4: No Context
❌ "Fix the bug"
✅ "Fix temperature calculation in prediction_service.py line 45"

### Pitfall 5: Not Reviewing Output
❌ Blindly accepting code
✅ Review, test, understand, then accept

---

## 📚 Reference Links

- [Full Agent Documentation](./README.md)
- [Detailed Usage Examples](./USAGE_EXAMPLES.md)
- [DDD Architecture Guide](../../DDD_ARCHITECTURE.md)
- [Project Instructions](../copilot-instructions.md)

---

## 🆘 Need Help?

### Agent Not Understanding?
→ Provide more context and specific files

### Code Doesn't Work?
→ Review for your specific setup and ask for refinements

### Not Sure Which Agent?
→ Check the Capabilities Matrix above

### Need Both Agents?
→ Delegate sequentially (domain first, then infrastructure)

---

**Remember:** Agents are assistants, not automation. Always review their suggestions! 🧠
