# 📖 Documentation Index

Welcome to Intelligent Heating Pilot's documentation! This index helps you find the right documentation for your needs.

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
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** - Guidelines for AI-assisted development
- **[.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)** - PR template with checklist
- **[.github/RELEASE_TEMPLATE.md](.github/RELEASE_TEMPLATE.md)** - Release process and template

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
→ [README.md - How IHP Works](README.md#how-ihp-works) - Overview
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Deep technical dive

#### ...report a bug
→ [Bug Report Template](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)

#### ...request a feature
→ [Feature Request Template](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=feature_request.md)

#### ...contribute code
→ [CONTRIBUTING.md](CONTRIBUTING.md) - Start here!
→ [ARCHITECTURE.md](ARCHITECTURE.md) - Understand the design

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

**Last Updated**: November 2025

For questions about documentation, please open a [Discussion](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions).
