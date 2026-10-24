# RC Workflows

This document describes the GitHub Actions workflows used to prepare, increment, and promote release candidates.

## Workflows

### prepare-release-candidate.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: create the first RC for a version
- Main actions: validate the version, extract release notes from `CHANGELOG.md`, create the `vX.Y.Z-rc1` tag, publish the GitHub pre-release, and open the tracking issue

### increment-rc-version.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: publish the next RC after fixes
- Main actions: detect the latest RC, increment the suffix, publish the new pre-release, and update the tracking issue

### promote-rc-to-release.yml

- Trigger: merge from `integration` into `main`
- Purpose: promote an accepted RC to a stable release
- Main actions: sync version metadata, create the final tag, publish the stable GitHub release, close linked issues, and remove superseded RC pre-releases

## Typical Flow

1. Update `CHANGELOG.md` on `integration`.
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
- [../../scripts/rc-helper.sh](../../scripts/rc-helper.sh)
