#!/usr/bin/env bash
# test-rc-check.sh — Local test harness for the RC detection logic used in
# integration-pr.yml.
#
# Exercises mock `gh release list` JSON payloads to validate that the workflow
# correctly identifies whether a valid RC pre-release (any version newer than
# main) exists before allowing integration→main merge.
#
# New logic (integration-pr.yml):
#   LATEST_RC=$(jq -r '.[] | select(.isPrerelease and
#     (.tagName | test("^v[0-9]+\\.[0-9]+\\.[0-9]+-rc[0-9]+$"))) | .tagName'
#     | sort -V | tail -1)
#   RC_VERSION=$(echo "$LATEST_RC" | sed 's/^v//; s/-rc[0-9]*$//')
#   → allow if LATEST_RC is non-empty AND RC_VERSION > MAIN_VERSION
#
# Usage:
#   bash scripts/test-rc-check.sh
#
# Exit code: 0 if all scenarios pass, 1 if any scenario fails.
set -euo pipefail

PASS=0
FAIL=0
MAIN_VERSION="1.2.0"

# Returns true (exit 0) when $1 is strictly greater than $2 per semver ordering.
version_gt() {
    local gt
    gt=$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)
    [ "$gt" = "$1" ] && [ "$1" != "$2" ]
}

# ---------------------------------------------------------------------------
# Helper: run the jq RC expression against a mock JSON payload.
# Returns the latest RC tag (version-sorted), or empty string if none found.
# ---------------------------------------------------------------------------
find_latest_rc() {
    local payload="$1"
    printf '%s' "$payload" \
        | jq -r '.[] | select(.isPrerelease and (.tagName | test("^v[0-9]+\\.[0-9]+\\.[0-9]+-rc[0-9]+$"))) | .tagName' \
        | sort -V | tail -1
}

# Strip tag prefix/suffix to extract the semver: v1.3.0-rc2 → 1.3.0
rc_version() {
    echo "$1" | sed 's/^v//; s/-rc[0-9]*$//'
}

# ---------------------------------------------------------------------------
# assert_blocked: no valid RC found → check should exit 1 (block merge)
# ---------------------------------------------------------------------------
assert_blocked() {
    local scenario="$1"
    local payload="$2"

    local latest_rc rc_ver
    latest_rc=$(find_latest_rc "$payload")
    rc_ver=$(rc_version "$latest_rc")

    if [ -z "$latest_rc" ] || ! version_gt "$rc_ver" "$MAIN_VERSION"; then
        echo "PASS [$scenario]: no qualifying RC → would block (latest_rc='$latest_rc')"
        PASS=$((PASS + 1))
    else
        echo "FAIL [$scenario]: expected block but found qualifying RC '$latest_rc'"
        FAIL=$((FAIL + 1))
    fi
}

# ---------------------------------------------------------------------------
# assert_allowed: valid RC found → check should allow merge
# ---------------------------------------------------------------------------
assert_allowed() {
    local scenario="$1"
    local payload="$2"
    local expected_tag="$3"

    local latest_rc rc_ver
    latest_rc=$(find_latest_rc "$payload")
    rc_ver=$(rc_version "$latest_rc")

    if [ -n "$latest_rc" ] && version_gt "$rc_ver" "$MAIN_VERSION" && [ "$latest_rc" = "$expected_tag" ]; then
        echo "PASS [$scenario]: found qualifying RC '$latest_rc' → would allow"
        PASS=$((PASS + 1))
    else
        echo "FAIL [$scenario]: expected tag '$expected_tag' but got '$latest_rc' (rc_ver='$rc_ver')"
        FAIL=$((FAIL + 1))
    fi
}

# ---------------------------------------------------------------------------
# Fixture payloads (mock of `gh release list --json tagName,isPrerelease`)
# ---------------------------------------------------------------------------

# (a) Empty release list
assert_blocked \
    "a: empty release list" \
    '[]'

# (b) Dev pre-release only — no RC suffix
assert_blocked \
    "b: dev pre-release only (no -rcN suffix)" \
    '[{"tagName":"v1.3.0-dev","isPrerelease":true}]'

# (c) RC for same version as main — not a real increment
assert_blocked \
    "c: RC version equals main version (v${MAIN_VERSION}-rc1 → no increment)" \
    '[{"tagName":"v1.2.0-rc1","isPrerelease":true}]'

# (d) RC for newer version — happy path (matches real-world scenario: manifest not bumped yet)
assert_allowed \
    "d: RC for next version (v1.3.0-rc2 while main=v${MAIN_VERSION})" \
    '[{"tagName":"v1.3.0-rc1","isPrerelease":true},{"tagName":"v1.3.0-rc2","isPrerelease":true},{"tagName":"v1.2.0","isPrerelease":false}]' \
    "v1.3.0-rc2"

# (e) Multiple versions of RCs — latest RC wins via sort -V
assert_allowed \
    "e: multiple RC versions, latest selected (v1.4.0-rc1 > v1.3.0-rc2)" \
    '[{"tagName":"v1.3.0-rc2","isPrerelease":true},{"tagName":"v1.4.0-rc1","isPrerelease":true}]' \
    "v1.4.0-rc1"

# (f) RC for a version older than main — must be blocked (older < main, not a valid increment)
assert_blocked \
    "f: RC version older than main (v1.1.0-rc3 while main=v${MAIN_VERSION})" \
    '[{"tagName":"v1.1.0-rc3","isPrerelease":true}]'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
