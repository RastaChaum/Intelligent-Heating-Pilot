# .github Documentation Index

Quick reference for IHP developers. **Start here:**

## 🚀 Quick Navigation

| You Are | Start Here |
| ------- | ---------- |
| **New to IHP?** | Read [docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md) |
| **Starting a feature?** | Run the speckit workflow starting with [WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md) |
| **Writing code?** | See [CONTRIBUTOR_STANDARDS.md](./CONTRIBUTOR_STANDARDS.md) + [copilot-instructions.md](./copilot-instructions.md) |
| **Writing tests?** | See [docs/BDD_TESTING.md](../docs/BDD_TESTING.md) |
| **Reviewing code?** | See your agent instruction file in [agents/](./agents/) |

---

## 📚 Documentation by Audience

### For Contributors

- **[docs/CONTRIBUTING.md](../docs/CONTRIBUTING.md)** — Getting started (quick walkthrough)
- **[CONTRIBUTOR_STANDARDS.md](./CONTRIBUTOR_STANDARDS.md)** — Code style (type hints, docstrings, logging)
- **[docs/BDD_TESTING.md](../docs/BDD_TESTING.md)** — How to write BDD + unit tests

### For Architecture, Review, and Workflow

- **[copilot-instructions.md](./copilot-instructions.md)** — Architecture principles (DDD, SOLID, layers)
- **[WORKFLOW_MODEL.md](./WORKFLOW_MODEL.md)** — Speckit workflow diagram + iteration loops
- **[agents/README.md](./agents/README.md)** — Speckit agent overview

---

## 🎯 Speckit Agent Instructions

- **[agents/README.md](./agents/README.md)** — Speckit agent overview
- **[agents/speckit.specify.agent.md](./agents/speckit.specify.agent.md)** — Specification stage
- **[agents/speckit.plan.agent.md](./agents/speckit.plan.agent.md)** — Planning and architecture stage
- **[agents/speckit.tasks.agent.md](./agents/speckit.tasks.agent.md)** — Task generation stage
- **[agents/speckit.implement.agent.md](./agents/speckit.implement.agent.md)** — Implementation stage
- **[agents/speckit.review.agent.md](./agents/speckit.review.agent.md)** — Final critical review stage
- **[agents/speckit.docs.agent.md](./agents/speckit.docs.agent.md)** — Documentation update stage

---

## 🔄 Typical Workflow

```text
speckit.specify -> speckit.clarify
speckit.plan -> speckit.checklist
speckit.tasks -> speckit.analyze
speckit.implement -> speckit.review
speckit.docs when documentation is impacted
```

All agents commit to **same feature branch** (one PR per feature).

---

## ✅ Key Principles

- **One PR per feature** — All speckit stages iterate on same branch
- **DDD + SOLID** — Pure domain (no HA imports)
- **TDD + BDD** — Tests before code
- **Governed workflow** — YAML front matter + governance validation enforce producer/reviewer separation

---

## 🔗 External References

| Topic | Link |
| ----- | ---- |
| **HA Development** | <https://developers.home-assistant.io/> |
| **DDD** | <https://martinfowler.com/bliki/DomainDrivenDesign.html> |
| **SOLID** | <https://en.wikipedia.org/wiki/SOLID> |
| **TDD** | <https://martinfowler.com/bliki/TestDrivenDevelopment.html> |
| **Gherkin** | <https://cucumber.io/docs/gherkin/reference/> |
| **pytest-bdd** | <https://pytest-bdd.readthedocs.io/> |
| **Poetry** | <https://python-poetry.org/docs/> |

---

**Last Updated**: 2026-02-13
**Maintained By**: Speckit Workflow
