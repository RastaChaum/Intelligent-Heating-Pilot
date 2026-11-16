# RC Workflows

This document describes the GitHub Actions workflows used to prepare, increment, and promote release candidates.

## Workflows

### prepare-release-candidate.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: create the first RC for a version
- Main actions: run the [end-to-end tests](#e2e-release-candidateyml) first (a failure stops the RC), validate the version (and warn when `manifest.json` differs from it), extract release notes from `CHANGELOG.md`, create the `vX.Y.Z-rc1` tag, and publish the GitHub pre-release

### increment-rc-version.yml

- Trigger: manual workflow dispatch on `integration`
- Purpose: publish the next RC after fixes
- Main actions: run the [end-to-end tests](#e2e-release-candidateyml) first (a failure stops the RC), detect the latest RC, increment the suffix, publish the new pre-release with the previous notes plus an "RC N" section, **then** delete the previous RC release (its tag is kept), and update the tracking issue
- Re-run safety: if a run pushed the new tag but failed before publishing its release, the next run publishes that tag instead of skipping a number

### e2e-release-candidate.yml

- Trigger: called by `prepare-release-candidate.yml` and `increment-rc-version.yml`; also manual workflow dispatch, which tests the branch it is started from, with an optional Home Assistant `ha_image` to try another Home Assistant version
- Purpose: check a release candidate in a real Home Assistant before it is published, without touching a production instance
- Main actions: start the official Home Assistant image with IHP, Versatile Thermostat, HACS Scheduler and Climate Scheduler, then check that every integration loads, that IHP puts each of three rooms (native schedule, HACS Scheduler, Climate Scheduler) in the slot's preset before the slot starts, that the log holds no unexpected error, and that everything loads again after a restart
- Duration: about 15 minutes, in real time; the Home Assistant log is kept as the `home-assistant-e2e-log` artifact
- Run it locally with Docker: `IHP_E2E=1 poetry run pytest tests/e2e -v` (see `tests/e2e/README.md`)

### integration-pr.yml

- Trigger: PRs targeting `main`
- Purpose: gate the release merge (see the release gates in [RELEASE_PROCESS.md](./RELEASE_PROCESS.md))
- Also accepts the `chore/changelog-vX.Y.Z` PR opened by the promotion, if it only modifies `CHANGELOG.md`

### promote-rc-to-release.yml

- Trigger: merge from `integration` into `main`
- Purpose: promote an accepted RC to a stable release
- Main actions: require an RC for the `manifest.json` version, publish the stable GitHub release and its tag, delete the RC pre-releases, open the `chore/changelog-vX.Y.Z` PR stamping the CHANGELOG on `main`, and merge that stamp into `integration`

## Typical Flow

1. Update `CHANGELOG.md` on `integration` and bump `manifest.json` and `hacs.json` to the release version.
2. Run `prepare-release-candidate.yml`.
3. The end-to-end tests run before the RC is published; then test the RC in production-like conditions.
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
