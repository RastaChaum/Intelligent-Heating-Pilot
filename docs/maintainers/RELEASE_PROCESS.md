# Release Process

This project uses a Release Candidate flow before promoting a version to a stable GitHub release.

## Source of Truth

- `CHANGELOG.md` records released changes.
- GitHub Releases hold published release notes.
- Workflow definitions live in `.github/workflows/`.

Do not commit versioned release-note markdown files at the repository root.

## Standard Flow

1. Update `CHANGELOG.md` on the integration branch.
2. Create the first RC with the workflow or helper script.
3. Test the RC in production-like conditions.
4. Fix issues on `integration` and increment the RC if needed.
5. Merge `integration` into `main` when the RC is accepted.
6. Let the promotion workflow create the final stable release.

## Helper Commands

```bash
./scripts/rc-helper.sh status
./scripts/rc-helper.sh prepare
./scripts/rc-helper.sh increment
./scripts/rc-helper.sh promote
```

## Maintainer Rules

- Keep release notes in GitHub Releases, not in committed `GITHUB_RELEASE_*.md` files.
- Keep release-process documentation under `docs/maintainers/`.
- Treat RCs as mandatory for non-trivial releases.
- Keep RC workflow reference documentation in `docs/maintainers/RC_WORKFLOWS.md`.

## Related Documentation

- [../../CHANGELOG.md](../../CHANGELOG.md)
- [RC_WORKFLOWS.md](./RC_WORKFLOWS.md)
