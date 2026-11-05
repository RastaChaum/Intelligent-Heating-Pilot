#!/usr/bin/env bash
# test-rc-check.sh — Local test harness for the release gates shared by
# integration-pr.yml and promote-rc-to-release.yml (scripts/release-gates.sh).
#
# The integration -> main merge is allowed only when:
#   1. the integration manifest version is strictly greater than main's, and
#   2. a GitHub pre-release vX.Y.Z-rcN exists for exactly that version.
# promote-rc-to-release.yml then requires the same RC, so a merge accepted by
# the gate can always be promoted (#196).
#
# Usage:
#   bash scripts/test-rc-check.sh
#
# Exit code: 0 if all scenarios pass, 1 if any scenario fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/release-gates.sh
source "$SCRIPT_DIR/release-gates.sh"

PASS=0
FAIL=0
MAIN_VERSION="1.2.0"

pass() { echo "PASS [$1]: $2"; PASS=$((PASS + 1)); }
fail() { echo "FAIL [$1]: $2"; FAIL=$((FAIL + 1)); }

# Prints the RC tag the gate accepts, or nothing when the merge is blocked.
gate_result() {
    local manifest_version="$1"
    local payload="$2"
    if ! version_gt "$manifest_version" "$MAIN_VERSION"; then
        return 0
    fi
    printf '%s' "$payload" | latest_rc_for_version "$manifest_version"
}

assert_blocked() {
    local scenario="$1" manifest_version="$2" payload="$3"
    local rc
    rc=$(gate_result "$manifest_version" "$payload")
    if [ -z "$rc" ]; then
        pass "$scenario" "blocked"
    else
        fail "$scenario" "expected block but the gate accepted '$rc'"
    fi
}

assert_allowed() {
    local scenario="$1" manifest_version="$2" payload="$3" expected_tag="$4"
    local rc
    rc=$(gate_result "$manifest_version" "$payload")
    if [ "$rc" = "$expected_tag" ]; then
        pass "$scenario" "allowed with '$rc'"
    else
        fail "$scenario" "expected '$expected_tag' but got '$rc'"
    fi
}

# ---------------------------------------------------------------------------
# Fixture payloads (mock of `gh release list --json tagName,isPrerelease`)
# ---------------------------------------------------------------------------

assert_blocked \
    "a: empty release list" \
    "1.3.0" '[]'

assert_blocked \
    "b: dev pre-release only (no -rcN suffix)" \
    "1.3.0" '[{"tagName":"v1.3.0-dev","isPrerelease":true}]'

assert_blocked \
    "c: RC for the next version but manifest not bumped (still ${MAIN_VERSION})" \
    "$MAIN_VERSION" '[{"tagName":"v1.3.0-rc2","isPrerelease":true}]'

assert_allowed \
    "d: RC matching the bumped manifest version" \
    "1.3.0" \
    '[{"tagName":"v1.3.0-rc1","isPrerelease":true},{"tagName":"v1.3.0-rc2","isPrerelease":true},{"tagName":"v1.2.0","isPrerelease":false}]' \
    "v1.3.0-rc2"

assert_blocked \
    "e: only an RC for another newer version (v1.4.0-rc1 while manifest=1.3.0)" \
    "1.3.0" '[{"tagName":"v1.4.0-rc1","isPrerelease":true}]'

assert_blocked \
    "f: manifest version older than main" \
    "1.1.0" '[{"tagName":"v1.1.0-rc3","isPrerelease":true}]'

assert_allowed \
    "g: RC numbers compared numerically (rc10 > rc9)" \
    "1.3.0" \
    '[{"tagName":"v1.3.0-rc10","isPrerelease":true},{"tagName":"v1.3.0-rc9","isPrerelease":true}]' \
    "v1.3.0-rc10"

assert_blocked \
    "h: dots in the version are literal (v1x3x0-rc1 is not v1.3.0)" \
    "1.3.0" '[{"tagName":"v1x3x0-rc1","isPrerelease":true}]'

assert_blocked \
    "i: an RC tag published as a final release is not a pre-release" \
    "1.3.0" '[{"tagName":"v1.3.0-rc1","isPrerelease":false}]'

assert_blocked \
    "j: longer version sharing the prefix (v1.3.01-rc1)" \
    "1.3.0" '[{"tagName":"v1.3.01-rc1","isPrerelease":true}]'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
