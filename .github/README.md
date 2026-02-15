# .github Documentation Index

Quick reference for IHP developers. **Start here:**

## 🚀 Quick Navigation

| You Are | Start Here |
|---------|-----------|
| **New to IHP?** | Read [docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md) |
| **Starting a feature?** | Invoke `@project-manager` + read [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md) |
| **Writing code?** | See [CONTRIBUTOR_STANDARDS.md](./CONTRIBUTOR_STANDARDS.md) + [copilot-instructions.md](./copilot-instructions.md) |
| **Writing tests?** | See [docs/BDD_TESTING.md](../docs/BDD_TESTING.md) |
| **Reviewing code?** | See your agent instruction file in [agents/](./agents/) |

---

## 📚 Documentation by Audience

### For Contributors
- **[docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md)** — Getting started (quick walkthrough)
- **[CONTRIBUTOR_STANDARDS.md](./CONTRIBUTOR_STANDARDS.md)** — Code style (type hints, docstrings, logging)
- **[docs/BDD_TESTING.md](../docs/BDD_TESTING.md)** — How to write BDD + unit tests

### For Architects & Tech Leads
- **[copilot-instructions.md](./copilot-instructions.md)** — Architecture principles (DDD, SOLID, layers)
- **[WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md)** — How agents collaborate (workflow diagram + iteration loops)
- **[agents/](./agents/)** — Role-specific instructions (each agent has specific duties)

---

## 🎯 Agent Instructions

Agent-specific roles (read if you're working with agents):

- **[agents/README.md](./agents/README.md)** — Agent overview
- **[agents/project_manager.agent.md](./agents/project_manager.agent.md)** — Orchestrates workflow
- **[agents/software_architect.agent.md](./agents/software_architect.agent.md)** — Phase 1: Design + interfaces
- **[agents/qa_engineer.agent.md](./agents/qa_engineer.agent.md)** — Phase 2: BDD + unit tests
- **[agents/developer.agent.md](./agents/developer.agent.md)** — Phase 3: Implementation
- **[agents/tech_lead.agent.md](./agents/tech_lead.agent.md)** — Phase 4: Review + merge
- **[agents/documentation_agent.agent.md](./agents/documentation_agent.agent.md)** — Phase 5: Documentation

---

## 🔄 Typical Workflow

```
@project-manager Issue #42: Add cache for heating slopes

Phase 1: @software-architect designs interfaces
Phase 2: @qa-engineer writes BDD + unit tests (RED)
Phase 3: @developer implements code (GREEN)
Phase 4: @tech-lead peer reviews + refactors + merges
Phase 5: @documentation-agent updates CHANGELOG
```

All agents commit to **same feature branch** (one PR per feature).

---

## ✅ Key Principles

- **One PR per feature** — All agents iterate on same branch
- **DDD + SOLID** — Pure domain (no HA imports)
- **TDD + BDD** — Tests before code
- **Living standards** — [CONTRIBUTOR_STANDARDS.md](./CONTRIBUTOR_STANDARDS.md) is maintainedby Software Architect

---

## 🔗 External References

| Topic | Link |
|-------|------|
| **HA Development** | https://developers.home-assistant.io/ |
| **DDD** | https://martinfowler.com/bliki/DomainDrivenDesign.html |
| **SOLID** | https://en.wikipedia.org/wiki/SOLID |
| **TDD** | https://martinfowler.com/bliki/TestDrivenDevelopment.html |
| **Gherkin** | https://cucumber.io/docs/gherkin/reference/ |
| **pytest-bdd** | https://pytest-bdd.readthedocs.io/ |
| **Poetry** | https://python-poetry.org/docs/ |

---

**Last Updated**: 2026-02-13
**Maintained By**: Software Architect
