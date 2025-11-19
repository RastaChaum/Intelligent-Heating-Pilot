## Description

<!-- Provide a clear and concise description of your changes -->

## Related Issue

<!-- Link the issue this PR addresses -->
Fixes #(issue number)

## Type of Change

<!-- Mark the relevant option with an "x" -->

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 📝 Documentation update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] ✅ Test coverage improvement
- [ ] 🏗️ Infrastructure/build changes

## Changes Made

<!-- Describe the changes in detail -->

- 
- 
- 

## Testing Performed

<!-- Describe the testing you've done -->

- [ ] All existing unit tests pass
- [ ] Added new unit tests for changes
- [ ] Tested manually in Home Assistant
- [ ] Tested with multiple VTherm configurations
- [ ] Tested edge cases

### Test Details

<!-- Provide details about your testing -->

**Environment:**
- Home Assistant Version: 
- Python Version: 
- VTherm Version: 

**Test Scenarios:**
1. 
2. 
3. 

## Screenshots (if applicable)

<!-- Add screenshots to demonstrate the changes -->

## Checklist

<!-- Ensure all items are completed before submitting -->

- [ ] My code follows the project's style guidelines (PEP 8, Black formatting)
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings or errors
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published
- [ ] I have updated CHANGELOG.md in the `[Unreleased]` section
- [ ] Domain layer has NO `homeassistant.*` imports (if applicable)
- [ ] All external interactions use ABCs/interfaces (if applicable)
- [ ] Value objects are immutable with `@dataclass(frozen=True)` (if applicable)

## Architecture Compliance (for code changes)

<!-- Verify DDD architecture compliance -->

- [ ] Domain layer remains independent of Home Assistant
- [ ] Business logic is in domain services, not infrastructure
- [ ] All infrastructure changes implement existing interfaces
- [ ] No business rules in adapters
- [ ] Tests use mocks for external dependencies

## Breaking Changes

<!-- If this is a breaking change, describe the impact and migration path -->

**Impact:**
- 

**Migration Guide:**
1. 
2. 
3. 

## Additional Notes

<!-- Add any additional information that reviewers should know -->

## Reviewer Checklist

<!-- For maintainers -->

- [ ] Code follows project architecture (DDD principles)
- [ ] Tests are comprehensive and pass
- [ ] Documentation is clear and complete
- [ ] Breaking changes are clearly documented
- [ ] CHANGELOG.md is updated
- [ ] Commit messages follow Conventional Commits
