# 📖 Documentation Index

Welcome to Intelligent Heating Pilot's documentation! This index helps you find the right documentation for your needs.

## 🗺️ Documentation Map

```
🏠 INTELLIGENT HEATING PILOT
│
├─── 👥 FOR USERS (Installation & Usage)
│    │
│    ├─── 📄 README.md ⭐ START HERE!
│    │    ├─ What is IHP?
│    │    ├─ Features
│    │    ├─ Installation (HACS/Manual)
│    │    ├─ Configuration
│    │    ├─ Usage & Sensors
│    │    ├─ How IHP Works (simplified)
│    │    └─ Troubleshooting
│    │
│    ├─── 📄 CHANGELOG.md
│    │    └─ Version history & changes
│    │
│    └─── 🌐 GitHub Releases
│         └─ Download & release notes
│
├─── 💻 FOR CONTRIBUTORS (Development)
│    │
│    ├─── 📄 CONTRIBUTING.md ⭐ START HERE!
│    │    ├─ How to contribute
│    │    ├─ Git branching strategy
│    │    ├─ Dev environment setup
│    │    ├─ Testing guide
│    │    ├─ Code standards
│    │    ├─ PR process
│    │    └─ Commit conventions
│    │
│    ├─── 📄 ARCHITECTURE.md
│    │    ├─ DDD principles
│    │    ├─ Layer structure
│    │    ├─ Value objects
│    │    ├─ Interfaces & services
│    │    ├─ Data flow
│    │    ├─ Testing strategies
│    │    └─ Best practices
│    │
│    ├─── 📁 .github/
│    │    ├─ copilot-instructions.md (AI guidelines)
│    │    ├─ AGENT_QUICKSTART.md (TDD quick start)
│    │    ├─ AGENT_WORKFLOW.md (Complete workflow)
│    │    ├─ PULL_REQUEST_TEMPLATE.md
│    │    ├─ RELEASE_TEMPLATE.md
│    │    └─ ISSUE_TEMPLATE/
│    │         ├─ bug_report.md
│    │         ├─ feature_request.md
│    │         └─ config.yml
│    │
│    └─── 🧪 tests/
│         └─ Unit & integration tests
│
└─── 🗺️ NAVIGATION
     │
     └─── 📄 DOCS_INDEX.md (You are here!)
          └─ Complete documentation index
```

---

## 👥 For End Users

If you want to **install and use** IHP:

### Getting Started
- **[README.md](README.md)** - Start here! Installation, configuration, and usage guide
  - Features overview
  - Installation via HACS or manual
  - Configuration through Home Assistant UI
  - Sensor descriptions
  - Troubleshooting tips

### Releases & Updates
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes
- **[GitHub Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)** - Download specific versions with full release notes
- **[AUTOMATED_RELEASE_GUIDE.md](AUTOMATED_RELEASE_GUIDE.md)** - Quick reference for maintainers (automated release process)

### Getting Help
- **[Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)** - Ask questions and get community support
- **[Bug Reports](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)** - Report issues
- **[Feature Requests](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=feature_request.md)** - Suggest improvements

---

## 💻 For Contributors

If you want to **contribute code or documentation**:

### Essential Reading
1. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Start here for contributors!
   - How to report bugs and request features
   - Development environment setup
   - Code standards and style guide
   - Testing requirements
   - Pull request process
   - Commit message conventions

2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture documentation
   - Domain-Driven Design (DDD) principles
   - Layer structure and responsibilities
   - Value objects, interfaces, and services
   - Data flow examples
   - Testing strategies
   - Best practices and anti-patterns

### Development Resources

**🚀 Agent-Driven Development** (TDD + DDD):
- **[.github/AGENT_QUICKSTART.md](.github/AGENT_QUICKSTART.md)** - ⭐ **5-minute quick start guide**
- **[.github/AGENT_WORKFLOW.md](.github/AGENT_WORKFLOW.md)** - Complete orchestrated workflow
- **[.github/agents/README.md](.github/agents/README.md)** - Agent system overview

**🤖 Specialized Agents**:
- **[software_architect.agent.md](.github/agents/software_architect.agent.md)** - Design interfaces and types
- **[qa_engineer.agent.md](.github/agents/qa_engineer.agent.md)** - TDD Red phase (write tests)
- **[developer.agent.md](.github/agents/developer.agent.md)** - TDD Green (implement code)
- **[tech_lead.agent.md](.github/agents/tech_lead.agent.md)** - Review and refactor
- **[documentation_agent.agent.md](.github/agents/documentation_agent.agent.md)** - Update docs

**📋 General Development**:
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - AI-assisted development guidelines
- **[.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)** - PR template with checklist
- **[.github/RELEASE_TEMPLATE.md](.github/RELEASE_TEMPLATE.md)** - Release process and template
- **[AUTOMATED_RELEASE_GUIDE.md](AUTOMATED_RELEASE_GUIDE.md)** - Automated releases quick reference

### Project Structure

```
intelligent-heating-pilot/
├── README.md                    # User guide (you are here)
├── CHANGELOG.md                 # Version history
├── CONTRIBUTING.md              # Contributor guide
├── ARCHITECTURE.md              # Technical architecture
├── LICENSE                      # MIT License
│
├── .github/
│   ├── copilot-instructions.md  # AI development guidelines
│   ├── PULL_REQUEST_TEMPLATE.md # PR template
│   ├── RELEASE_TEMPLATE.md      # Release process
│   └── ISSUE_TEMPLATE/          # Issue templates
│       ├── bug_report.md
│       ├── feature_request.md
│       └── config.yml
│
├── custom_components/
│   └── intelligent_heating_pilot/
│       ├── domain/              # Pure business logic
│       ├── infrastructure/      # Home Assistant integration
│       └── application/         # Use case orchestration
│
└── tests/
    └── unit/                    # Unit tests
        ├── domain/              # Domain logic tests
        └── infrastructure/      # Infrastructure tests
```

---

## 🎯 Quick Navigation

### I want to...

#### ...use IHP in my Home Assistant
→ [README.md](README.md) - Installation and usage

#### ...understand how IHP works
→ [README.md - Understanding IHP](README.md#understanding-ihp) - Overview
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Deep technical dive

#### ...report a bug
→ [Bug Report Template](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)

#### ...request a feature
→ [Feature Request Template](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=feature_request.md)

#### ...contribute code
→ [CONTRIBUTING.md](CONTRIBUTING.md) - ⭐ **Start here!** Complete contributor guide (setup, Git workflow, standards)
→ [.github/AGENT_QUICKSTART.md](.github/AGENT_QUICKSTART.md) - Quick start with TDD agents (5 minutes)
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Understand the DDD design

#### ...create a release
→ [.github/RELEASE_TEMPLATE.md](.github/RELEASE_TEMPLATE.md) - Release process

#### ...understand the DDD architecture
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Complete guide
→ [.github/copilot-instructions.md](.github/copilot-instructions.md) - Quick reference

---

## 📊 Documentation Quality Standards

All documentation follows these principles:

✅ **Clear Audience**: Each document has a specific target audience (users vs contributors)
✅ **Consistent Format**: Uses standard templates and formatting
✅ **Keep Current**: Updated with each release
✅ **Examples**: Includes practical examples where helpful
✅ **Searchable**: Well-structured with clear headings
✅ **Links**: Cross-references to related documentation

---

## 🌍 Language

All project documentation is in **English** to ensure maximum accessibility for the international community.

---

## 📝 Documentation Contributions

Documentation improvements are always welcome! If you find:
- Typos or errors
- Unclear explanations
- Missing information
- Outdated content

Please open an issue or submit a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📚 External Resources

### Home Assistant
- [Home Assistant Documentation](https://www.home-assistant.io/docs/)
- [Developer Documentation](https://developers.home-assistant.io/)

### Related Integrations
- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)
- [HACS Scheduler](https://github.com/nielsfaber/scheduler-component)

### Software Design
- [Domain-Driven Design](https://martinfowler.com/tags/domain%20driven%20design.html)
- [Test-Driven Development](https://martinfowler.com/bliki/TestDrivenDevelopment.html)
- [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📊 Documentation Quality Standards

All documentation follows these principles:

✅ **DRY Principle**: Single source of truth - no duplicate information
✅ **Clear Audience**: Each document targets specific readers (users vs contributors)
✅ **Consistent Format**: Standard templates and formatting throughout
✅ **Keep Current**: Updated with each release
✅ **Examples**: Practical examples where helpful
✅ **Searchable**: Well-structured with clear headings
✅ **Cross-referenced**: Links to related documentation

---

**Last Updated**: November 2025

For questions about documentation, please open a [Discussion](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions).
