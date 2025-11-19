# GitHub Copilot Custom Agents

This directory contains custom agent configurations for GitHub Copilot to assist with specialized tasks in the Intelligent Heating Pilot (IHP) project.

## Available Agents

### 1. DDD Architecture Expert (`ddd-architect.instructions`)

**Purpose**: Specialized agent for Domain-Driven Design architecture tasks.

**Use Cases**:
- Refactoring code to follow DDD principles
- Ensuring strict separation between domain and infrastructure layers
- Migrating legacy code to clean architecture
- Reviewing code for architectural compliance
- Creating proper abstractions (value objects, interfaces, adapters)
- Writing tests that respect layer boundaries

**When to Delegate**:
- "Refactor this coordinator to follow DDD architecture"
- "Extract business logic from this infrastructure adapter"
- "Create proper interfaces for this service"
- "Review this code for DDD compliance"
- "Help me migrate this legacy class to domain layer"

**Key Responsibilities**:
- Ensure ZERO `homeassistant.*` imports in domain layer
- Create ABCs for all external interactions
- Implement thin infrastructure adapters
- Write TDD-compliant tests
- Maintain backward compatibility during migrations

---

### 2. Cloud & Weather Integration Expert (`cloud-integration-expert.instructions`)

**Purpose**: Specialized agent for weather data and cloud services integration.

**Use Cases**:
- Integrating weather APIs and sensors
- Implementing environmental corrections (cloud coverage, humidity, temperature)
- Designing weather-based prediction algorithms
- Handling weather data gracefully with fallbacks
- Optimizing API calls and caching
- Testing with various weather scenarios

**When to Delegate**:
- "Add support for weather forecast integration"
- "Improve the cloud coverage correction algorithm"
- "Create a weather data adapter for OpenWeatherMap"
- "Handle missing weather data more gracefully"
- "Add outdoor temperature impact to predictions"

**Key Responsibilities**:
- Keep weather algorithms in domain layer (pure functions)
- Implement weather providers as infrastructure adapters
- Handle API failures with sensible fallbacks
- Document weather-based formulas with citations
- Test with mocked weather data

---

## How to Use Custom Agents

### In GitHub Copilot Chat

When you need specialized help, mention the agent's expertise area in your request:

```
@workspace Please help refactor the coordinator class to follow DDD architecture.
Delegate this to the DDD architecture expert.
```

or

```
@workspace I need to integrate weather forecast data into the heating predictions.
Delegate this to the cloud integration expert.
```

### Best Practices

1. **Be Specific**: Clearly describe what you want the agent to do
2. **Provide Context**: Share relevant files, classes, or code snippets
3. **State Constraints**: Mention any specific requirements or limitations
4. **Review Output**: Always review and test the agent's suggestions
5. **Iterate**: Ask follow-up questions if needed

### Agent Capabilities

Custom agents can:
- ✅ Analyze existing code
- ✅ Suggest refactoring approaches
- ✅ Generate new code following patterns
- ✅ Create tests
- ✅ Review code for compliance
- ✅ Provide architectural guidance

Custom agents **cannot**:
- ❌ Execute code directly
- ❌ Access external APIs
- ❌ Modify files without your approval
- ❌ Run tests automatically

---

## Architecture Overview

IHP follows a strict **Domain-Driven Design** architecture:

```
custom_components/intelligent_heating_pilot/
├── domain/              # Pure business logic (NO HA dependencies)
│   ├── value_objects/   # Immutable data carriers
│   ├── entities/        # Domain entities and aggregates
│   ├── interfaces/      # Abstract base classes (ABCs)
│   └── services/        # Domain services
├── infrastructure/      # Home Assistant integration layer
│   ├── adapters/        # HA API implementations
│   └── repositories/    # Data persistence implementations
└── application/         # Orchestration and use cases
```

### Key Principles

1. **Domain Purity**: Domain layer has ZERO external dependencies
2. **Interface-Driven**: All external interactions via ABCs
3. **Thin Adapters**: Infrastructure layer just translates, no business logic
4. **Test-Driven**: Write tests before implementation
5. **Type Safety**: Complete type hints on all code

---

## Contributing New Agents

To add a new custom agent:

1. **Identify Need**: What specialized expertise is missing?
2. **Create Instructions File**: `{agent-name}.instructions`
3. **Define Expertise**: What is the agent's specialty?
4. **Document Use Cases**: When should users delegate to this agent?
5. **Provide Patterns**: Include code examples and templates
6. **Set Standards**: Define success criteria and quality bars
7. **Update README**: Add agent to this document

### Agent File Structure

```markdown
# {Agent Name}

You are a specialized expert in {domain}.

## Your Expertise
- List specific skills
- Technical knowledge areas
- Tools and frameworks

## Your Role
What you do when delegated tasks

## Project-Specific Rules
Constraints specific to IHP

## Code Patterns
Examples of correct implementations

## Success Criteria
How to know a task is complete

## Remember
Key principles to always follow
```

---

## Feedback and Improvements

If you find these agents helpful or have suggestions for improvement:

1. **Open an Issue**: Describe what worked well or what could be better
2. **Submit a PR**: Improve agent instructions or add new agents
3. **Share Examples**: Document successful delegation examples

---

## References

- [Main Copilot Instructions](../copilot-instructions.md)
- [DDD Architecture](../../DDD_ARCHITECTURE.md)
- [Migration Guide](../../MIGRATION_GUIDE.md)
- [Implementation Status](../../IMPLEMENTATION_STATUS.md)

---

*Last Updated: 2025-11-19*
