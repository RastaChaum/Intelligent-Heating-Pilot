# RC Workflows

This document describes the GitHub Actions workflows used to prepare, increment, and promote release candidates.

## Workflows

### prepare-release-candidate.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: create the first RC for a version
- Main actions: validate the version (and warn when `manifest.json` differs from it), extract release notes from `CHANGELOG.md`, delete the dev pre-release, create the `vX.Y.Z-rc1` tag, and publish the GitHub pre-release

### increment-rc-version.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: publish the next RC after fixes
- Main actions: detect the latest RC, increment the suffix, publish the new pre-release with the previous notes plus an "RC N" section, **then** delete the previous RC release (its tag is kept), and update the tracking issue
- Re-run safety: if a run pushed the new tag but failed before publishing its release, the next run publishes that tag instead of skipping a number

### update-prerelease-on-integration-merge.yml

- Trigger: every PR merged into `integration`
- Purpose: keep the `vX.Y.Z-dev` pre-release in step with `integration`
- Main actions: move the dev tag to the `integration` HEAD and refresh its notes from `[Unreleased]`
- RC phase: when an RC exists for the `manifest.json` version, nothing is changed; RC tags are immutable and their notes describe what they contain

### integration-pr.yml

- Trigger: PRs targeting `main`
- Purpose: gate the release merge (see the release gates in [RELEASE_PROCESS.md](./RELEASE_PROCESS.md))
- Also accepts the `chore/changelog-vX.Y.Z` PR opened by the promotion, if it only modifies `CHANGELOG.md`

### promote-rc-to-release.yml

- Trigger: merge from `integration` into `main`
- Purpose: promote an accepted RC to a stable release
- Main actions: require an RC for the `manifest.json` version, publish the stable GitHub release and its tag, delete the RC and dev pre-releases, open the `chore/changelog-vX.Y.Z` PR stamping the CHANGELOG on `main`, and merge that stamp into `integration`

## Typical Flow

1. Update `CHANGELOG.md` on `integration` and bump `manifest.json` and `hacs.json` to the release version.
2. Run `prepare-release-candidate.yml`.
3. Test the RC in production-like conditions.
4. Apply fixes and run `increment-rc-version.yml` if needed.
5. Merge `integration` into `main` when the RC is accepted.
6. Let `promote-rc-to-release.yml` publish the stable release.

## Maintainer Rules

- Use the workflows rather than creating RC tags manually.
- Keep `CHANGELOG.md` current before preparing an RC.
- Treat RCs as mandatory for non-trivial releases.
- Keep release notes in GitHub Releases, not in committed `GITHUB_RELEASE_*.md` files.

## Related Documentation

- [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
- [../../CHANGELOG.md](../../CHANGELOG.md)
- [../../scripts/rc-helper.sh](../../scripts/rc-helper.sh) (dispatches these workflows)
- [../../scripts/release-gates.sh](../../scripts/release-gates.sh) (RC check shared by the gate and the promotion)
