#!/usr/bin/env bash

set -e

JSON_MODE=false
STAGE=""
FEATURE_DIR_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)
            JSON_MODE=true
            shift
            ;;
        --stage)
            STAGE="$2"
            shift 2
            ;;
        --feature-dir)
            FEATURE_DIR_OVERRIDE="$2"
            shift 2
            ;;
        --help|-h)
            cat << 'EOF'
Usage: validate-governance.sh --stage <spec|plan|tasks|implement|final> [--json] [--feature-dir DIR]

Validate YAML governance metadata and mandatory workflow sections for speckit artifacts.
EOF
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option '$1'" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$STAGE" ]]; then
    echo "ERROR: --stage is required" >&2
    exit 1
fi

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

_paths_output=$(get_feature_paths) || { echo "ERROR: Failed to resolve feature paths" >&2; exit 1; }
eval "$_paths_output"
unset _paths_output

if [[ -n "$FEATURE_DIR_OVERRIDE" ]]; then
    FEATURE_DIR="$FEATURE_DIR_OVERRIDE"
fi

PYTHON_SCRIPT="$REPO_ROOT/.specify/scripts/python/validate_governance.py"
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "ERROR: Governance validator not found: $PYTHON_SCRIPT" >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERROR: python3 or python is required to validate governance metadata" >&2
    exit 1
fi

ARGS=("$PYTHON_SCRIPT" --repo-root "$REPO_ROOT" --feature-dir "$FEATURE_DIR" --stage "$STAGE")
if $JSON_MODE; then
    ARGS+=(--json)
fi

exec "$PYTHON_BIN" "${ARGS[@]}"
