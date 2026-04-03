#!/usr/bin/env bash
# test-changelog-check.sh — Local test harness for the two-pass CHANGELOG diff logic.
#
# Exercises five fixture scenarios to validate the algorithm from plan.md Decision 1
# before and after editing .github/workflows/feature-fix-pr.yml.
#
# Usage:
#   bash scripts/test-changelog-check.sh
#
# Exit code: 0 if all scenarios pass, 1 if any scenario fails.
set -euo pipefail

PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helper: run the two-pass diff logic against two strings (HEAD and BASE)
# Returns exit code 0 if NEW_LINES > 0, 1 if NEW_LINES == 0
# ---------------------------------------------------------------------------
run_check() {
    local head_changelog="$1"
    local base_changelog="$2"

    HEAD_UNRELEASED=$(printf '%s' "$head_changelog" \
        | awk '/## \[Unreleased\]/{flag=1;next} /^## \[/{flag=0} flag{print}' \
        | grep -v '^[[:space:]]*$' || true)

    BASE_UNRELEASED=$(printf '%s' "$base_changelog" \
        | awk '/## \[Unreleased\]/{flag=1;next} /^## \[/{flag=0} flag{print}' \
        | grep -v '^[[:space:]]*$' || true)

    NEW_LINES=$(diff <(printf '%s\n' "$BASE_UNRELEASED") <(printf '%s\n' "$HEAD_UNRELEASED") \
        | grep '^>' | wc -l)

    if [ "$NEW_LINES" -eq 0 ]; then
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# assert_check_fails: expect the check to exit 1 (scenario should block the PR)
# ---------------------------------------------------------------------------
assert_check_fails() {
    local scenario="$1"
    local head_changelog="$2"
    local base_changelog="$3"

    if run_check "$head_changelog" "$base_changelog"; then
        echo "FAIL [$scenario]: expected check to FAIL (exit 1) but it PASSED"
        FAIL=$((FAIL + 1))
    else
        echo "PASS [$scenario]"
        PASS=$((PASS + 1))
    fi
}

# ---------------------------------------------------------------------------
# assert_check_passes: expect the check to exit 0 (scenario should allow the PR)
# ---------------------------------------------------------------------------
assert_check_passes() {
    local scenario="$1"
    local head_changelog="$2"
    local base_changelog="$3"

    if run_check "$head_changelog" "$base_changelog"; then
        echo "PASS [$scenario]"
        PASS=$((PASS + 1))
    else
        echo "FAIL [$scenario]: expected check to PASS (exit 0) but it FAILED"
        FAIL=$((FAIL + 1))
    fi
}

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_CHANGELOG_STANDARD=$(cat <<'HEREDOC'
# Changelog

## [Unreleased]

## [1.0.0] - 2025-01-01
### Added
- Initial release
HEREDOC
)

# (a) No CHANGELOG.md change — HEAD identical to BASE
assert_check_fails \
    "a: no CHANGELOG.md change (identical)" \
    "$BASE_CHANGELOG_STANDARD" \
    "$BASE_CHANGELOG_STANDARD"

# (b) Change only OUTSIDE [Unreleased] — new entry in a versioned section
HEAD_OUTSIDE=$(cat <<'HEREDOC'
# Changelog

## [Unreleased]

## [1.0.0] - 2025-01-01
### Added
- Initial release
- Extra line added outside Unreleased
HEREDOC
)
assert_check_fails \
    "b: change only outside [Unreleased]" \
    "$HEAD_OUTSIDE" \
    "$BASE_CHANGELOG_STANDARD"

# (c) Valid addition INSIDE [Unreleased] — should PASS
HEAD_VALID=$(cat <<'HEREDOC'
# Changelog

## [Unreleased]

### Added
- New predictive preheating feature

## [1.0.0] - 2025-01-01
### Added
- Initial release
HEREDOC
)
assert_check_passes \
    "c: valid addition inside [Unreleased] (happy path)" \
    "$HEAD_VALID" \
    "$BASE_CHANGELOG_STANDARD"

# (d) [Unreleased] section absent entirely from HEAD
HEAD_NO_UNRELEASED=$(cat <<'HEREDOC'
# Changelog

## [1.0.0] - 2025-01-01
### Added
- Initial release
HEREDOC
)
assert_check_fails \
    "d: [Unreleased] section absent from HEAD" \
    "$HEAD_NO_UNRELEASED" \
    "$BASE_CHANGELOG_STANDARD"

# (e) Only blank lines added inside [Unreleased]
HEAD_BLANK_ONLY=$(cat <<'HEREDOC'
# Changelog

## [Unreleased]



## [1.0.0] - 2025-01-01
### Added
- Initial release
HEREDOC
)
assert_check_fails \
    "e: only blank lines added inside [Unreleased]" \
    "$HEAD_BLANK_ONLY" \
    "$BASE_CHANGELOG_STANDARD"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
