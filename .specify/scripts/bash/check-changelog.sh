#!/usr/bin/env bash
# Validates that CHANGELOG.md contains a non-empty [Unreleased] section.
#
# Usage: check-changelog.sh [OPTIONS]
#
# OPTIONS:
#   --json          Output results in JSON format
#   --check-diff    Also verify CHANGELOG.md was modified compared to origin/integration
#   --repo-root DIR Override the repository root (defaults to git root)
#   --help, -h      Show this help message
#
# EXIT CODES:
#   0  All checks passed
#   1  One or more errors found

set -euo pipefail

JSON_MODE=false
CHECK_DIFF=false
REPO_ROOT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_MODE=true; shift ;;
        --check-diff) CHECK_DIFF=true; shift ;;
        --repo-root) REPO_ROOT="$2"; shift 2 ;;
        --help | -h)
            cat << 'EOF'
Usage: check-changelog.sh [--json] [--check-diff] [--repo-root DIR]

Validates that CHANGELOG.md contains a non-empty [Unreleased] section.

OPTIONS:
  --json          Output results in JSON format
  --check-diff    Also verify CHANGELOG.md was modified vs origin/integration
  --repo-root DIR Override the repository root directory
  --help, -h      Show this help message

EXIT CODES:
  0  All checks passed
  1  One or more errors found
EOF
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option '$1'" >&2
            exit 1
            ;;
    esac
done

# Resolve repository root
if [[ -z "$REPO_ROOT" ]]; then
    if git rev-parse --show-toplevel >/dev/null 2>&1; then
        REPO_ROOT="$(git rev-parse --show-toplevel)"
    else
        echo "ERROR: Not in a git repository and --repo-root not provided" >&2
        exit 1
    fi
fi

CHANGELOG="$REPO_ROOT/CHANGELOG.md"
ERRORS=()
WARNINGS=()

# Check CHANGELOG.md exists
if [[ ! -f "$CHANGELOG" ]]; then
    ERRORS+=("CHANGELOG.md not found at $CHANGELOG")
else
    # Check [Unreleased] section exists
    if ! grep -q "^## \[Unreleased\]" "$CHANGELOG"; then
        ERRORS+=("CHANGELOG.md is missing the [Unreleased] section (expected '## [Unreleased]')")
    else
        # Check [Unreleased] section has meaningful content
        UNRELEASED_CONTENT=$(awk '/^## \[Unreleased\]/{found=1; next} found && /^## \[/{exit} found{print}' \
            "$CHANGELOG" | grep -v "^[[:space:]]*$" || true)
        if [[ -z "$UNRELEASED_CONTENT" ]]; then
            ERRORS+=("The [Unreleased] section in CHANGELOG.md is empty. Add an entry describing your change under '## [Unreleased]'.")
        fi
    fi

    # Check CHANGELOG was modified vs integration branch
    if $CHECK_DIFF; then
        if git rev-parse --verify origin/integration >/dev/null 2>&1; then
            if ! git diff origin/integration --name-only | grep -q "^CHANGELOG.md$"; then
                ERRORS+=("CHANGELOG.md has not been modified compared to origin/integration. Update the [Unreleased] section before merging.")
            fi
        else
            WARNINGS+=("Cannot verify diff against origin/integration (branch not found locally). Skipping diff check.")
        fi
    fi
fi

HAS_ERRORS="${#ERRORS[@]}"

# Output results
if $JSON_MODE; then
    error_json="["
    for err in "${ERRORS[@]+"${ERRORS[@]}"}"; do
        err_escaped="${err//\\/\\\\}"
        err_escaped="${err_escaped//\"/\\\"}"
        error_json+="\"$err_escaped\","
    done
    error_json="${error_json%,}]"

    warning_json="["
    for warn in "${WARNINGS[@]+"${WARNINGS[@]}"}"; do
        warn_escaped="${warn//\\/\\\\}"
        warn_escaped="${warn_escaped//\"/\\\"}"
        warning_json+="\"$warn_escaped\","
    done
    warning_json="${warning_json%,}]"

    ok=$([[ $HAS_ERRORS -eq 0 ]] && echo "true" || echo "false")
    echo "{\"ok\":$ok,\"errors\":$error_json,\"warnings\":$warning_json}"
else
    for err in "${ERRORS[@]+"${ERRORS[@]}"}"; do
        echo "ERROR: $err" >&2
    done
    for warn in "${WARNINGS[@]+"${WARNINGS[@]}"}"; do
        echo "WARNING: $warn"
    done
    if [[ $HAS_ERRORS -eq 0 ]]; then
        echo "✅ CHANGELOG.md [Unreleased] section is present and contains content"
    fi
fi

exit $((HAS_ERRORS > 0 ? 1 : 0))
