#!/usr/bin/env bash
# release-gates.sh — Release checks shared by the release workflows, the
# maintainer helper and the local test harness.
#
# integration-pr.yml (before the integration -> main merge) and
# promote-rc-to-release.yml (after it) must agree on what "a validated RC"
# means. Keeping a single implementation here prevents the gate from letting
# through a merge that the promotion then refuses (#196).
#
# Usage (sourced):
#   source scripts/release-gates.sh
#   gh release list --limit 100 --json tagName,isPrerelease | latest_rc_for_version 0.7.1
#
# Usage (CLI):
#   gh release list ... | scripts/release-gates.sh latest-rc 0.7.1
#   scripts/release-gates.sh version-gt 0.7.1 0.7.0

# Returns 0 when $1 is strictly greater than $2 in version order.
version_gt() {
    local greatest
    greatest=$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)
    [ "$greatest" = "$1" ] && [ "$1" != "$2" ]
}

# Reads `gh release list --json tagName,isPrerelease` JSON on stdin and prints
# the highest vVERSION-rcN pre-release tag for exactly VERSION, or nothing.
# Only pre-releases count: a bare git tag without its GitHub release is not an
# RC anyone could have tested.
latest_rc_for_version() {
    local version="$1"
    jq -r --arg v "$version" '
        [
          .[]
          | select(
              .isPrerelease == true
              and (.tagName | test("^v" + ($v | gsub("\\."; "\\.")) + "-rc[0-9]+$"))
            )
        ]
        | sort_by(.tagName | capture("-rc(?<number>[0-9]+)$").number | tonumber)
        | last
        | .tagName // empty
    '
}

# Allow running the functions directly when the file is executed, not sourced.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    set -euo pipefail
    command="${1:-}"
    case "$command" in
        latest-rc)
            latest_rc_for_version "${2:?version required}"
            ;;
        version-gt)
            version_gt "${2:?version required}" "${3:?version required}"
            ;;
        *)
            echo "Usage: $0 {latest-rc VERSION | version-gt A B}" >&2
            exit 2
            ;;
    esac
fi
