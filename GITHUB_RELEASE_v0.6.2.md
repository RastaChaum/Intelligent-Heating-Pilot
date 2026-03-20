# Release v0.6.2 - Release Candidate

## 🧪 Release Candidate
This version is a **release candidate** for production validation and beta testing.


### Changed
- **CI/CD Workflow overhaul** – Eliminated duplicate quality checks, standardized Poetry install, and corrected branch naming convention
  - Quality checks no longer run twice when a PR is open on a feature branch
  - Branch naming validation now enforces the documented `feature/issue-XXX` slash format
  - All workflows now use `snok/install-poetry@v1` with dependency caching for faster runs
  - RC pre-release detection uses the GitHub Releases API instead of git tags (ground truth)
  - Fixed `-beta` vs `-rcN` inconsistency: integration PR check and release promotion now correctly target RC releases
  - RC release notes are generated on-the-fly — no `GITHUB_RELEASE_*.md` files committed to the repository
  - New workflow: GitHub pre-release (dev or RC) is automatically created and updated on every merge to `integration`, keeping it in sync with the CHANGELOG `[Unreleased]` section
- **Agent workflow documentation** – All agent files and workflow docs now explicitly require feature branches to be created from `integration`, not `main`

### Added
- **Configurable Preheating Revert Time Delta** – Added a new integration option to control when active preheating can be canceled and rescheduled during anticipation recalculation.
  - New option: `anticipation_recalc_tolerance_minutes` (default: 15, range: 1-60)
  - Exposed in both initial setup and options flow

### Fixed
- **Dead Time Thresholds for Floor Heating** – Corrected two default parameters in `_calculate_dead_time_cycle()` that caused all dead time measurements to be silently discarded on floor heating systems:
  - `temp_change_threshold`: `0.1°C` → `0.2°C` to avoid false positives from sensor noise
  - `max_dead_time_minutes`: `60 min` → `180 min` to correctly capture cold-start delays inherent to floor heating (realistic range: 60–120 min)
  - Systems affected were falling back to the configured default dead time on every cycle instead of learning from historical data

---

## ⚠️ Important
This version is in test phase. Please report issues via GitHub Issues.
