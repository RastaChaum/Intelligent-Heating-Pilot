# Release Checklist and Template

This template is for creating GitHub Releases. Use this as a guide when preparing release notes.

---

## Release Title Format

```
v{version} - {short description}
```

Examples:
- `v0.3.0 - Multi-Zone Support and Performance Improvements`
- `v0.2.2 - Bug Fixes and Stability`
- `v1.0.0 - First Stable Release`

---

## Release Description Template

```markdown
## 🎉 What's New in v{version}

{Brief overview of the release - 2-3 sentences highlighting the main improvements}

---

## ✨ New Features

<!-- List new features with brief descriptions -->

- **Feature Name**: Description of what it does and why it's useful
  - Additional details or usage notes
  - Related configuration changes (if any)

## 🐛 Bug Fixes

<!-- List bug fixes -->

- **Fixed**: Description of what was fixed (#issue-number)
  - Impact and how it improves user experience

## 🔧 Improvements

<!-- List enhancements and improvements -->

- **Improved**: Description of the improvement
  - Performance impact or benefit

## 📝 Documentation

<!-- List documentation changes -->

- Updated README with new feature examples
- Added architecture documentation for contributors
- Improved troubleshooting guide

## ⚠️ Breaking Changes

<!-- Only if applicable - describe breaking changes and migration path -->

**BREAKING**: Description of the breaking change

**Migration Guide:**
1. Step 1 to migrate
2. Step 2 to migrate
3. What users need to update in their configuration

**Impact:** Who is affected and how

## 📦 Dependencies

<!-- If dependencies were updated -->

- Updated `dependency-name` from v1.0 to v2.0
- Added `new-dependency` v1.5

## 🔗 Full Changelog

See the [CHANGELOG.md](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/main/CHANGELOG.md) for a complete list of changes.

**Full Diff**: [`v{previous}...v{current}`](https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v{previous}...v{current})

---

## 📥 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to Integrations
3. Search for "Intelligent Heating Pilot"
4. Click "Update" (or "Download" for new installations)
5. Restart Home Assistant

### Manual Installation

1. Download `intelligent_heating_pilot.zip` from the Assets below
2. Extract to `config/custom_components/intelligent_heating_pilot/`
3. Restart Home Assistant

---

## 🆘 Getting Help

- **Documentation**: [README.md](https://github.com/RastaChaum/Intelligent-Heating-Pilot/blob/main/README.md)
- **Issues**: [Report a bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md)
- **Discussions**: [Ask questions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions)

---

## 🙏 Acknowledgements

<!-- Thank contributors -->

Special thanks to:
- @username for their contribution to...
- Everyone who reported bugs and provided feedback

---

## 📊 Release Statistics

<!-- Optional: Add some stats -->

- **Issues Closed**: X
- **Pull Requests Merged**: X
- **Contributors**: X
```

---

## Pre-Release Checklist

Before creating a release, ensure:

### Code Quality
- [ ] All tests pass (`pytest tests/unit/`)
- [ ] No linting errors (`black --check .`)
- [ ] No type errors (`mypy custom_components/intelligent_heating_pilot/`)
- [ ] Code review completed for all merged PRs

### Documentation
- [ ] CHANGELOG.md updated with all changes
- [ ] README.md updated (if needed)
- [ ] Version number updated in:
  - [ ] `manifest.json`
  - [ ] `const.py`
  - [ ] `hacs.json`
- [ ] Breaking changes documented clearly
- [ ] Migration guide written (if breaking changes)

### Testing
- [ ] Tested in Home Assistant (dev environment)
- [ ] Tested upgrade path from previous version
- [ ] Tested fresh installation
- [ ] Breaking changes verified
- [ ] Edge cases tested

### Release Notes
- [ ] Release notes drafted (use template above)
- [ ] GitHub Release created with proper tag
- [ ] Assets attached (if applicable)
- [ ] Release marked as pre-release (if beta/alpha)

### Communication
- [ ] Announcement prepared for discussions
- [ ] Known issues documented
- [ ] Upgrade instructions clear

---

## Version Numbering (Semantic Versioning)

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (v1.0.0): Incompatible API changes or breaking changes
- **MINOR** (v0.1.0): New features, backwards compatible
- **PATCH** (v0.0.1): Bug fixes, backwards compatible

### Pre-Release Tags

- **Alpha** (v0.1.0-alpha.1): Early development, experimental
- **Beta** (v0.1.0-beta.1): Feature complete, testing phase
- **RC** (v0.1.0-rc.1): Release candidate, final testing

---

## GitHub Release Creation

1. Go to [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)
2. Click "Draft a new release"
3. **Tag**: `v{version}` (e.g., `v0.3.0`)
4. **Target**: `main` (or release branch)
5. **Title**: Use title format above
6. **Description**: Use template above, customize for your release
7. **Assets**: Attach any necessary files
8. **Options**:
   - [ ] Check "Set as a pre-release" (for alpha/beta)
   - [ ] Check "Set as the latest release" (for stable)
9. Click "Publish release"

---

## Post-Release Tasks

- [ ] Verify release appears on GitHub
- [ ] Update HACS repository (if applicable)
- [ ] Post announcement in Discussions
- [ ] Update project documentation links
- [ ] Monitor for issues related to new release
- [ ] Respond to user feedback

---

## Example Release Notes

See previous releases for examples:
- [v0.2.0](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.2.0)
- [v0.1.0](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/tag/v0.1.0)
