# 🤖 Automated Release Process - Quick Reference

## Overview

The Intelligent Heating Pilot project uses **GitHub Actions** to automate release creation with a **Release Candidate (RC)** workflow for production testing before final releases.

**Two-phase release workflow:**
1. **RC Phase**: Test in production with `v0.5.0-rc1`, `v0.5.0-rc2`, etc. (pre-releases)
2. **Final Release**: Promote tested RC to stable `v0.5.0` release

---

## 🚀 Release Candidate (RC) Workflow

### Phase 1: Create Initial RC on `integration` branch

#### Option A: Using the Helper Script (Recommended)

```bash
# Sur la branche integration
./scripts/rc-helper.sh prepare
# Entrez la version (ex: 0.5.0)
# Le script vérifie le CHANGELOG, crée GITHUB_RELEASE_v0.5.0.md et le tag v0.5.0-rc1
```

#### Option B: Using GitHub Workflow Manually

1. Go to [Actions → Prepare Release Candidate](../../actions/workflows/prepare-release-candidate.yml)
2. Click "Run workflow"
3. Enter version (e.g., `0.5.0`)
4. Workflow creates:
   - `GITHUB_RELEASE_v0.5.0.md` on `integration`
   - Tag `v0.5.0-rc1`
   - GitHub pre-release
   - Tracking issue for RC testing

### Phase 2: Test in Production

**Deploy the RC to your production environment:**
- Install from pre-release in HACS or manually
- Beta-testers can test the RC
- Report issues in the RC tracking issue

### Phase 3: Fix Issues and Increment RC

**If bugs are found:**

```bash
# Faire les corrections sur integration
git add .
git commit -m "fix: correction problème X"
git push origin integration

# Créer une nouvelle RC (rc2, rc3, etc.)
./scripts/rc-helper.sh increment
# Entrez la version de base (0.5.0)
# Décrivez les corrections apportées
```

**Or via GitHub Workflow:**
1. Fix bugs on `integration` branch
2. Go to [Actions → Increment RC Version](../../actions/workflows/increment-rc-version.yml)
3. Run workflow with version and fix description
4. Workflow creates `v0.5.0-rc2`, updates release notes, creates new pre-release

### Phase 4: Promote to Final Release

**When RC is stable and ready:**

```bash
# Vérifier que tout est OK
./scripts/rc-helper.sh promote

# Créer la PR integration → main
gh pr create --base main --head integration --title "Release v0.5.0" --body "Promote RC to stable release"
```

**When PR is merged to `main`:**
- Workflow automatically:
  - Updates CHANGELOG.md with release date
  - Syncs version numbers in all files
  - Creates final tag `v0.5.0`
  - Creates GitHub Release (NOT pre-release)
  - Closes referenced issues
  - Deletes RC pre-releases
  - Closes RC tracking issue

---

## 📋 Quick Reference Commands

```bash
# Check RC status
./scripts/rc-helper.sh status

# Prepare first RC (on integration)
./scripts/rc-helper.sh prepare

# Increment RC after fixes (on integration)
./scripts/rc-helper.sh increment

# Prepare for final release promotion
./scripts/rc-helper.sh promote

# Show help
./scripts/rc-helper.sh help
```

---

## 🔄 Legacy: Direct Release Process (Not Recommended)

**This section kept for reference. Use RC workflow above instead.**

### 1️⃣ Prepare Release Documentation

#### A. Update CHANGELOG.md

```bash
# Move [Unreleased] content to versioned release
## [0.4.0] - 2025-11-25

### Added
- New feature descriptions...

### Changed
- Modifications...

### Fixed
- Bug fixes with issue references...

# Add version comparison link at bottom
[0.4.0]: https://github.com/RastaChaum/Intelligent-Heating-Pilot/compare/v0.3.0...v0.4.0
```

#### B. Create Release Notes File

**Filename**: `GITHUB_RELEASE_v0.4.0.md` (in project root)

**Template**: Use `.github/RELEASE_TEMPLATE.md` as starting point

**CRITICAL**: Reference issues using markdown links for auto-closure:
```markdown
✅ Good:  [#16](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/16)
❌ Bad:   #16 (won't auto-close)
```

Example:
```markdown
# Release v0.4.0 - Feature Name

## 🐛 Bug Fixes

### Issue #16: Description
Fixed pre-heating revert logic ([#16](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/16))
```

#### C. Update Version Numbers

Files to update:
- `custom_components/intelligent_heating_pilot/manifest.json` → `"version": "0.4.0"`
- `custom_components/intelligent_heating_pilot/const.py` → `VERSION = "0.4.0"`
- `hacs.json` → `"version": "0.4.0"` (if present)
- `README.md` → Update version badge

### 2️⃣ Merge and Tag

```bash
# 1. Ensure you're on integration branch with latest changes
git checkout integration
git pull origin integration

# 2. Merge to main
git checkout main
git pull origin main
git merge integration --no-ff -m "chore(release): merge for v0.4.0

Closes #16, #17, #19"

# 3. Create annotated tag
git tag -a v0.4.0 -m "Release v0.4.0 - Brief Description

Key highlights:
- Feature 1
- Feature 2
- Bug fix #16"

# 4. Push everything
git push origin main
git push origin v0.4.0
```

### 3️⃣ Wait for Automation (1-2 minutes)

**GitHub Actions will automatically**:

1. ✅ Detect tag push (`v0.4.0`)
2. ✅ Read `GITHUB_RELEASE_v0.4.0.md`
3. ✅ Extract issue numbers from `[#123](...)` links
4. ✅ Create GitHub Pre-Release:
   - Title: `v0.4.0 - Beta Release`
   - Body from your release notes
   - Append "Closes #X" for each issue
   - Mark as pre-release
5. ✅ Close all referenced issues
6. ✅ Add "released" label
7. ✅ Update project board

**Watch progress**: [Actions Tab](https://github.com/RastaChaum/Intelligent-Heating-Pilot/actions)

### 4️⃣ Verify and Publish

1. Go to [Releases](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)
2. Review the auto-created release:
   - ✅ Title correct?
   - ✅ Body complete?
   - ✅ Issues closed?
   - ✅ Marked as pre-release?
3. If everything OK:
   - Keep as pre-release (for beta)
   - Or edit and uncheck "pre-release" (for stable)
4. Announce release (Community Forum, Discussions)

### 5️⃣ Post-Release Cleanup

```bash
# Reset CHANGELOG.md [Unreleased] section
## [Unreleased]

### Added

### Changed

### Fixed

# Optionally delete release notes file
git rm GITHUB_RELEASE_v0.4.0.md
git commit -m "chore: cleanup release notes file after v0.4.0"
git push origin main
```

---

## 🔧 GitHub Action Configuration

**File**: `.github/workflows/create-release.yml`

**Trigger**: Push to `v*.*.*` tags

**Permissions**:
- `contents: write` - Create releases
- `issues: write` - Close issues

**Key Steps**:
1. Checkout code with full history
2. Extract version from tag
3. Check if `GITHUB_RELEASE_vX.Y.Z.md` exists
4. Generate release body (from file or CHANGELOG)
5. Create GitHub Release as pre-release
6. Extract and close issues from markdown links
7. Update project board

**Fallback**: If release notes file missing, uses CHANGELOG.md

---

## 📋 Pre-Release Checklist

Use this before pushing the tag:

```markdown
### Documentation
- [ ] CHANGELOG.md [Unreleased] → [X.Y.Z] with date
- [ ] GITHUB_RELEASE_vX.Y.Z.md created
- [ ] Issue references use [#123](URL) format
- [ ] README.md updated with new features
- [ ] All doc links verified

### Version Numbers
- [ ] manifest.json → "version": "X.Y.Z"
- [ ] const.py → VERSION = "X.Y.Z"
- [ ] hacs.json → "version": "X.Y.Z"
- [ ] README.md → version badge updated

### Code Quality
- [ ] All tests passing
- [ ] No linting errors
- [ ] Code examples in docs tested
- [ ] Breaking changes documented with migration guide

### Git
- [ ] Integration branch merged to main
- [ ] Tag created: vX.Y.Z
- [ ] Tag pushed to GitHub
```

---

## 🐛 Troubleshooting

### Issue: GitHub Action didn't trigger

**Check**:
1. Tag format correct? Must be `v1.2.3` (with `v` prefix)
2. Tag pushed to GitHub? `git push origin vX.Y.Z`
3. Workflow file exists? `.github/workflows/create-release.yml`
4. Check [Actions Tab](https://github.com/RastaChaum/Intelligent-Heating-Pilot/actions) for errors

**Fix**:
- Delete and recreate tag if format wrong
- Check workflow YAML syntax
- Verify repository permissions

### Issue: Release created but issues not closed

**Check**:
1. Issue references in `GITHUB_RELEASE_vX.Y.Z.md` use `[#123](URL)` format?
2. Issues are open (not already closed)?
3. GitHub token has `issues: write` permission?

**Fix**:
- Manually close issues: `gh issue close 123 --comment "Fixed in v0.4.0"`
- Update workflow to grant correct permissions

### Issue: Release notes incomplete

**Check**:
1. `GITHUB_RELEASE_vX.Y.Z.md` exists in project root?
2. Filename matches tag exactly? (case-sensitive)
3. File committed and pushed before creating tag?

**Fix**:
- Edit release manually on GitHub
- Or delete release, fix file, re-tag

### Issue: Want to create release manually

**Steps**:
1. Go to [New Release](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/new)
2. Select tag: `vX.Y.Z`
3. Title: `vX.Y.Z - Description`
4. Copy content from `GITHUB_RELEASE_vX.Y.Z.md`
5. Append:
   ```markdown
   ---

   **Issues Fixed:**
   Closes #16
   Closes #17
   ```
6. ✅ Check "Set as a pre-release"
7. Publish

---

## 💡 Tips & Best Practices

### ✅ Do's

- **Test locally first**: Run tests, verify docs before tagging
- **Use descriptive titles**: `v0.4.0 - Multi-zone Support` not just `v0.4.0`
- **Reference issues properly**: Always use `[#123](URL)` format for auto-closure
- **Review before publishing**: GitHub Action creates draft-like pre-release first
- **Keep CHANGELOG current**: Update as you develop, not just at release
- **Version bump correctly**: Follow [Semantic Versioning](https://semver.org/)

### ❌ Don'ts

- **Don't skip CHANGELOG**: Even if you have release notes, update CHANGELOG
- **Don't use plain #123**: Won't auto-close issues (use markdown links)
- **Don't forget version comparison links**: Add at bottom of CHANGELOG
- **Don't rush**: Double-check version numbers everywhere
- **Don't break SemVer**: Major.Minor.Patch has meaning

---

## 🎯 Example Release

**Scenario**: Releasing v0.4.0 with 2 bug fixes

### 1. CHANGELOG.md
```markdown
## [0.4.0] - 2025-11-25

### Fixed
- Issue [#20](https://github.com/RastaChaum/IHP/issues/20): Sensor update lag
- Issue [#21](https://github.com/RastaChaum/IHP/issues/21): Config validation

[0.4.0]: https://github.com/RastaChaum/IHP/compare/v0.3.0...v0.4.0
```

### 2. GITHUB_RELEASE_v0.4.0.md
```markdown
# Release v0.4.0 - Bug Fix Release

## 🐛 Fixes
- [#20](https://github.com/RastaChaum/IHP/issues/20): Sensor updates now real-time
- [#21](https://github.com/RastaChaum/IHP/issues/21): Config validation improved
```

### 3. Git Commands
```bash
git checkout main
git merge integration --no-ff -m "chore(release): v0.4.0"
git tag -a v0.4.0 -m "v0.4.0 - Bug fixes"
git push origin main v0.4.0
```

### 4. Result
- ✅ Release created automatically
- ✅ Issues #20 and #21 closed
- ✅ Project board updated
- ✅ Ready for announcement

---

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Keep a Changelog](https://keepachangelog.com/)
- [Semantic Versioning](https://semver.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

**Last Updated**: Janvier 2025
**Automation Files**:
- `.github/workflows/prepare-release-candidate.yml` - Create initial RC
- `.github/workflows/increment-rc-version.yml` - Increment RC version
- `.github/workflows/promote-rc-to-release.yml` - Promote RC to final release
- `scripts/rc-helper.sh` - CLI helper for RC management

**Documentation**: `.github/agents/documentation_specialist.agent.md`

---

## 📊 RC Workflow Summary

```
┌─────────────────────────────────────────────────────────────┐
│  INTEGRATION BRANCH                                         │
│                                                             │
│  1. Develop features                                        │
│  2. Update CHANGELOG.md [Unreleased]                        │
│  3. ./scripts/rc-helper.sh prepare → v0.5.0-rc1            │
│  4. Test in production                                      │
│  5. Fix bugs if needed                                      │
│  6. ./scripts/rc-helper.sh increment → v0.5.0-rc2, rc3...  │
│  7. Repeat until stable                                     │
│                                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ PR integration → main
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  MAIN BRANCH                                                │
│                                                             │
│  Merge triggers automatic:                                 │
│  ✅ CHANGELOG.md update                                     │
│  ✅ Version sync in all files                               │
│  ✅ Tag v0.5.0 creation                                     │
│  ✅ GitHub Release (stable, not pre-release)                │
│  ✅ Issues closure                                          │
│  ✅ RC pre-releases cleanup                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 Best Practices

### ✅ Do's

- **Always test RC in production** before final release
- **Use semantic versioning**: Major.Minor.Patch
- **Document all changes** in CHANGELOG.md as you develop
- **Reference issues** with `[#123](URL)` format for auto-closure
- **Keep integration clean**: Only merge tested features
- **One RC at a time**: Don't create multiple concurrent RCs

### ❌ Don'ts

- **Don't skip RC phase** for non-trivial releases
- **Don't merge to main** without successful RC testing
- **Don't forget to sync versions** in all files before RC
- **Don't create RC tags manually** on main branch
- **Don't promote untested RCs** to production

## 🔧 Troubleshooting

### RC workflow didn't trigger

**Check:**
- Workflow files exist in `.github/workflows/`
- You have workflow execution permissions
- Check [Actions tab](../../actions) for errors

**Fix:**
- Re-run workflow manually
- Check YAML syntax
- Verify GitHub token permissions

### Multiple RCs created accidentally

**Fix:**
```bash
# Delete unwanted RC releases
gh release delete v0.5.0-rc3 --yes
git push origin :refs/tags/v0.5.0-rc3
```

### Want to restart RC process

**Steps:**
1. Delete all RC tags for the version
2. Delete RC pre-releases on GitHub
3. Close RC tracking issue
4. Start fresh with `./scripts/rc-helper.sh prepare`

### RC promoted but issues not closed

**Check:**
- Issue references use `[#123](URL)` format in release notes
- Issues are open (not already closed)
- Workflow has `issues: write` permission

**Fix manually:**
```bash
gh issue close 123 --comment "Fixed in v0.5.0"
gh issue edit 123 --add-label "released"
```
