#!/usr/bin/env bash
# test-rc-check.sh — Local test harness for the jq RC count expression used in
# integration-pr.yml and promote-rc-to-release.yml.
#
# Exercises four mock `gh release list` JSON payloads to validate that the
# expression correctly identifies the presence or absence of RC pre-releases
# for a given version.
#
# Usage:
#   bash scripts/test-rc-check.sh
#
# Exit code: 0 if all scenarios pass, 1 if any scenario fails.
set -euo pipefail

PASS=0
FAIL=0
VERSION="1.2.0"

# ---------------------------------------------------------------------------
# Helper: run the jq RC count expression against a mock JSON payload
# Returns the integer count of matching RC releases.
# ---------------------------------------------------------------------------
count_rc() {
    local payload="$1"
    printf '%s' "$payload" \
        | jq --arg v "$VERSION" \
            '[.[] | select(.isPrerelease and (.tagName | test("^v" + $v + "-rc[0-9]+$")))] | length'
}

# ---------------------------------------------------------------------------
# assert_count_zero: expect count == 0 (no RC → check should block)
# ---------------------------------------------------------------------------
assert_count_zero() {
    local scenario="$1"
    local payload="$2"

    local count
    count=$(count_rc "$payload")
    if [ "$count" -eq 0 ]; then
        echo "PASS [$scenario]: count=$count (correctly zero → would block)"
        PASS=$((PASS + 1))
    else
        echo "FAIL [$scenario]: expected count=0 but got count=$count"
        FAIL=$((FAIL + 1))
    fi
}

# ---------------------------------------------------------------------------
# assert_count_nonzero: expect count >= 1 (RC exists → check should allow)
# ---------------------------------------------------------------------------
assert_count_nonzero() {
    local scenario="$1"
    local payload="$2"

    local count
    count=$(count_rc "$payload")
    if [ "$count" -ge 1 ]; then
        echo "PASS [$scenario]: count=$count (correctly non-zero → would allow)"
        PASS=$((PASS + 1))
    else
        echo "FAIL [$scenario]: expected count>=1 but got count=0"
        FAIL=$((FAIL + 1))
    fi
}

# ---------------------------------------------------------------------------
# Fixture payloads (mock of `gh release list --json tagName,isPrerelease`)
# ---------------------------------------------------------------------------

# (a) Empty release list
PAYLOAD_EMPTY='[]'
assert_count_zero \
    "a: empty release list" \
    "$PAYLOAD_EMPTY"

# (b) One dev pre-release only — no RC (tagName contains "-dev", not "-rcN")
PAYLOAD_DEV_ONLY=$(cat <<'HEREDOC'
[
  { "tagName": "v1.2.0-dev", "isPrerelease": true }
]
HEREDOC
)
assert_count_zero \
    "b: one dev pre-release only (no rcN suffix)" \
    "$PAYLOAD_DEV_ONLY"

# (c) One RC pre-release for the target version — happy path
PAYLOAD_ONE_RC=$(cat <<'HEREDOC'
[
  { "tagName": "v1.2.0-rc1", "isPrerelease": true }
]
HEREDOC
)
assert_count_nonzero \
    "c: one RC pre-release (happy path)" \
    "$PAYLOAD_ONE_RC"

# (d) Multiple RCs — all match; also RC for unrelated version must not inflate count
PAYLOAD_MULTI_RC=$(cat <<'HEREDOC'
[
  { "tagName": "v1.2.0-rc1", "isPrerelease": true },
  { "tagName": "v1.2.0-rc2", "isPrerelease": true },
  { "tagName": "v1.1.0-rc1", "isPrerelease": true },
  { "tagName": "v1.2.0",     "isPrerelease": false }
]
HEREDOC
)
assert_count_nonzero \
    "d: multiple RCs (only v${VERSION} RCs counted)" \
    "$PAYLOAD_MULTI_RC"

# Extra edge case — RC for a different version must not count
PAYLOAD_WRONG_VERSION=$(cat <<'HEREDOC'
[
  { "tagName": "v1.1.0-rc1", "isPrerelease": true },
  { "tagName": "v1.3.0-rc1", "isPrerelease": true }
]
HEREDOC
)
assert_count_zero \
    "extra: RC exists but for wrong version (v1.1 and v1.3, not v${VERSION})" \
    "$PAYLOAD_WRONG_VERSION"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
