# 🚀 Quick Start: Agent-Driven Development

## Welcome to Intelligent Heating Pilot Development!

This project uses **specialized GitHub Copilot agents** to ensure high-quality, test-driven development following Domain-Driven Design principles.

---

## ⚡ Super Simple: Just Talk to the Project Manager!

**You don't need to manage multiple agents!** 

Just invoke the **Project Manager** agent, and it will automatically coordinate all the other agents for you:

```markdown
@project-manager

Fix Issue #45: Pre-heating starts too early in humid weather.
```

The Project Manager will:
1. ✅ Automatically invoke Testing Specialist to write tests
2. ✅ Automatically invoke Tech Lead to implement code
3. ✅ Ask you to review
4. ✅ Automatically invoke Documentation Specialist after approval
5. ✅ Report completion

**That's it!** One command, complete workflow.

---

## 🎯 The 4-Agent System (Orchestrated)

```
┌─────────────────────────────────────────────────────────────┐
│                  Feature/Bug Fix Request                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │  1️⃣  Testing Specialist Agent    │
        │      Write Tests FIRST (TDD)      │
        │                                    │
        │  📝 Input:  Issue requirements     │
        │  📤 Output: Failing tests (RED)    │
        └────────────┬───────────────────────┘
                     │ Tests ready
                     ▼
        ┌────────────────────────────────────┐
        │  2️⃣  Tech Lead Agent              │
        │      Implement Clean Code          │
        │                                    │
        │  📝 Input:  Failing tests          │
        │  📤 Output: Passing tests (GREEN)  │
        └────────────┬───────────────────────┘
                     │ Code ready
                     ▼
        ┌────────────────────────────────────┐
        │  👤  User Code Review              │
        │                                    │
        │  ✅ Approved  →  Continue          │
        │  ❌ Changes   →  Back to Agent 1   │
        └────────────┬───────────────────────┘
                     │ Approved
                     ▼
        ┌────────────────────────────────────┐
        │  3️⃣  Documentation Specialist    │
        │      Update All Docs               │
        │                                    │
        │  📝 Input:  Approved code          │
        │  📤 Output: Updated documentation  │
        └────────────┬───────────────────────┘
                     │ Docs ready
                     ▼
        ┌────────────────────────────────────┐
        │        🎉 Merge PR                │
        └────────────────────────────────────┘
```

---

## ⚡ 5-Minute Quick Start

### 1. You Have an Issue to Fix

Example: **Issue #45** - "Pre-heating starts too early in humid weather"

### 2. Invoke Testing Specialist

```markdown
@testing-specialist

Please write tests for Issue #45: Pre-heating too early in humid weather.

The problem: LHS calculation doesn't account for humidity, causing 
pre-heating to start 30-45 minutes too early when humidity > 70%.

Write tests to verify:
1. LHS adjusts upward when humidity is high (>60%)
2. Adjustment is proportional (linear 0-60%)
3. Missing humidity sensor doesn't break predictions
4. Extreme humidity values (99%) are capped reasonably
```

**Agent Response**:
```
✅ Tests ready for Issue #45
- 4 tests written (domain layer)
- All tests failing (RED phase)
- Files: tests/unit/domain/test_lhs_humidity_fix.py
- Ready for @tech-lead
```

### 3. Tech Lead Implements → Review → Documentation Updates

The Project Manager handles steps 3-6 automatically! Just review when asked.

**Done!** 🎉

---

## 📚 Next Steps

### For Complete Workflow Details

See **[AGENT_WORKFLOW.md](AGENT_WORKFLOW.md)** for:
- Detailed agent coordination
- Complete examples with all phases
- Troubleshooting guide
- Advanced patterns

### For Agent System Overview

See **[agents/README.md](agents/README.md)** for:
- How each agent works internally
- Configuration and customization
- Best practices per agent

### For Development Setup

See **[../CONTRIBUTING.md](../CONTRIBUTING.md)** for:
- Environment setup
- Git workflow
- Testing requirements
- Code standards

### For Architecture Understanding

See **[../ARCHITECTURE.md](../ARCHITECTURE.md)** for:
- Domain-Driven Design principles
- Layer structure details
- Best practices and anti-patterns

---

## 🎓 Key Principles (Quick Reference)

### TDD: Red → Green → Refactor
```
🔴 Write failing tests  →  🟢 Make them pass  →  🔵 Clean up code
```

### DDD: Keep Domain Pure
```
domain/          ← Pure business logic (NO Home Assistant imports!)
infrastructure/  ← HA integration (thin adapters)
application/     ← Orchestration
```

See [ARCHITECTURE.md](../ARCHITECTURE.md) for complete details.

---

## 🚨 Common Pitfalls

❌ **Don't skip the Project Manager** - Let it orchestrate everything  
❌ **Don't import HA in domain layer** - Use interfaces only  
❌ **Don't skip documentation** - Project Manager handles this automatically

✅ **Do trust the workflow** - It ensures quality  
✅ **Do be specific** - Clear requirements = better results  
✅ **Do review carefully** - You approve before docs update

---

## 🎉 You're Ready!

Just remember: **@project-manager** + clear description = complete workflow!

For deeper understanding, see [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md).

---

**Last Updated**: November 2025  
**Workflow Version**: 1.0  
**Questions?** Open a [Discussion](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)
