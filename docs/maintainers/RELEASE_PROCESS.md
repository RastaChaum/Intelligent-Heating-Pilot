# Release Process

This project uses a Release Candidate flow before promoting a version to a stable GitHub release.

## Source of Truth

- `CHANGELOG.md` records released changes.
- GitHub Releases hold published release notes.
- Workflow definitions live in `.github/workflows/`.

Do not commit versioned release-note markdown files at the repository root.

## Standard Flow

1. Update `CHANGELOG.md` on the integration branch.
2. Bump the version in `manifest.json` and `hacs.json` on `integration` to the release version.
3. Create the first RC with the workflow or helper script.
4. Test the RC in production-like conditions.
5. Fix issues on `integration` and increment the RC if needed.
6. Merge `integration` into `main` when the RC is accepted.
7. Let the promotion workflow create the final stable release.
8. Approve and merge the `chore/changelog-vX.Y.Z` PR it opens to stamp the CHANGELOG on `main`.

## Release Gates

The `integration` → `main` PR (`integration-pr.yml`) passes only when:

- the `manifest.json` version is greater than the one on `main`, and equals the `hacs.json` version;
- `CHANGELOG.md` has entries under `[Unreleased]`;
- a GitHub pre-release `vX.Y.Z-rcN` exists for **exactly** the `manifest.json` version.

The promotion workflow requires the same RC. Both use `scripts/release-gates.sh`, tested by `scripts/test-rc-check.sh`, so a merge the gate accepts can always be promoted.

The same check accepts one other source branch: the `chore/changelog-vX.Y.Z` PR opened by the promotion workflow, as long as it only modifies `CHANGELOG.md`. A PR opened with `GITHUB_TOKEN` does not trigger workflows: set the optional `RELEASE_PR_TOKEN` secret (fine-grained PAT or GitHub App token with "Pull requests: write") to have its checks run automatically, or close and reopen the PR.

## Helper Commands

`rc-helper.sh` dispatches the release workflows and reads GitHub Releases; it never pushes tags itself.

```bash
./scripts/rc-helper.sh status                       # RC pre-releases of the integration version
./scripts/rc-helper.sh prepare [VERSION]            # dispatches 'Prepare Release Candidate'
./scripts/rc-helper.sh increment [VERSION] [FIXES]  # dispatches 'Increment RC Version'
./scripts/rc-helper.sh promote                      # checks the release gates before the main PR
```

## Maintainer Rules

- Keep release notes in GitHub Releases, not in committed `GITHUB_RELEASE_*.md` files.
- Keep release-process documentation under `docs/maintainers/`.
- Treat RCs as mandatory for non-trivial releases.
- Keep RC workflow reference documentation in `docs/maintainers/RC_WORKFLOWS.md`.

## Related Documentation

- [../../CHANGELOG.md](../../CHANGELOG.md)
- [RC_WORKFLOWS.md](./RC_WORKFLOWS.md)
