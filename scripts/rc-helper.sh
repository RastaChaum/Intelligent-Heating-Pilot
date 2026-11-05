#!/usr/bin/env bash

# Release candidate helper.
#
# The release workflows are the single implementation of the RC process: this
# script only dispatches them and reads GitHub Releases, the source of truth
# the release gates check (#198). It never pushes tags or commits release-note
# files itself.
#
# Usage: ./scripts/rc-helper.sh [command] [options]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="custom_components/intelligent_heating_pilot/manifest.json"
RELEASE_BRANCH="integration"
RELEASE_LIST_LIMIT=100

# shellcheck source=scripts/release-gates.sh
source "$SCRIPT_DIR/release-gates.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; exit 1; }

require_tools() {
    command -v gh >/dev/null 2>&1 || error "The GitHub CLI (gh) is required: https://cli.github.com"
    command -v jq >/dev/null 2>&1 || error "jq is required"
    gh auth status >/dev/null 2>&1 || error "gh is not authenticated: run 'gh auth login'"
}

# Version of manifest.json on the remote integration branch, which is what
# the workflows read.
get_integration_version() {
    git fetch --quiet origin "$RELEASE_BRANCH"
    git show "origin/$RELEASE_BRANCH:$MANIFEST" | jq -r '.version'
}

get_main_version() {
    git fetch --quiet origin main
    git show "origin/main:$MANIFEST" | jq -r '.version'
}

list_releases() {
    gh release list --limit "$RELEASE_LIST_LIMIT" --json tagName,isPrerelease
}

validate_version() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || error "Invalid version format '$1'. Use X.Y.Z"
}

confirm() {
    local reply
    read -r -p "$1 (y/N): " -n 1 reply
    echo
    [[ "$reply" =~ ^[Yy]$ ]] || error "Cancelled"
}

show_runs_hint() {
    info "Follow the run with: gh run watch \$(gh run list --workflow $1 --limit 1 --json databaseId --jq '.[0].databaseId')"
}

# Command: prepare [VERSION]
cmd_prepare() {
    require_tools
    local version="${1:-}"
    if [ -z "$version" ]; then
        read -r -p "Release version (e.g. 0.5.0): " version
    fi
    validate_version "$version"

    local manifest_version
    manifest_version=$(get_integration_version)
    if [ "$manifest_version" != "$version" ]; then
        warning "manifest.json on $RELEASE_BRANCH is $manifest_version, not $version."
        warning "Bump manifest.json and hacs.json to $version before the $RELEASE_BRANCH → main PR."
    fi

    confirm "Dispatch 'Prepare Release Candidate' for v${version}-rc1 on $RELEASE_BRANCH?"
    gh workflow run prepare-release-candidate.yml --ref "$RELEASE_BRANCH" -f version="$version"
    success "Workflow dispatched: it creates the v${version}-rc1 tag and its GitHub pre-release"
    show_runs_hint prepare-release-candidate.yml
}

# Command: increment [VERSION] [DESCRIPTION]
cmd_increment() {
    require_tools
    local version="${1:-}"
    local description="${2:-}"
    if [ -z "$version" ]; then
        read -r -p "Base version (e.g. 0.5.0): " version
    fi
    validate_version "$version"

    local current_rc
    current_rc=$(list_releases | latest_rc_for_version "$version")
    [ -n "$current_rc" ] || error "No RC pre-release found for v${version}. Use 'prepare' first."
    info "Current RC: $current_rc"

    if [ -z "$description" ]; then
        echo "Describe the fixes in this RC (end with an empty line):"
        local line
        while IFS= read -r line; do
            [ -z "$line" ] && break
            description+="${line}"$'\n'
        done
    fi
    [ -n "$description" ] || error "A description of the fixes is required"

    confirm "Dispatch 'Increment RC Version' for v${version} on $RELEASE_BRANCH?"
    gh workflow run increment-rc-version.yml --ref "$RELEASE_BRANCH" \
        -f version="$version" -f fix_description="$description"
    success "Workflow dispatched: it publishes the next RC, then deletes $current_rc's release"
    show_runs_hint increment-rc-version.yml
}

# Command: status
cmd_status() {
    require_tools
    local version releases current_rc
    version=$(get_integration_version)
    info "Version on $RELEASE_BRANCH (manifest.json): $version"
    info "Version on main: $(get_main_version)"

    releases=$(list_releases)
    echo ""
    echo "Pre-releases for v${version}:"
    printf '%s' "$releases" | jq -r --arg v "$version" \
        '.[] | select(.isPrerelease and (.tagName | startswith("v" + $v + "-"))) | "  📌 " + .tagName'

    current_rc=$(printf '%s' "$releases" | latest_rc_for_version "$version")
    if [ -n "$current_rc" ]; then
        success "Current RC: $current_rc"
    else
        warning "No RC pre-release for v${version}"
    fi
}

# Command: promote
cmd_promote() {
    require_tools
    local version main_version current_rc
    version=$(get_integration_version)
    main_version=$(get_main_version)
    info "Version: $main_version (main) → $version ($RELEASE_BRANCH)"

    version_gt "$version" "$main_version" \
        || error "manifest.json on $RELEASE_BRANCH ($version) must be greater than main ($main_version)"

    current_rc=$(list_releases | latest_rc_for_version "$version")
    [ -n "$current_rc" ] || error "No RC pre-release found for v${version}"
    success "Current RC: $current_rc"

    echo ""
    warning "Checklist before promotion:"
    echo "  [ ] All RC tests passed"
    echo "  [ ] No critical bug left"
    echo "  [ ] Documentation up to date"
    echo "  [ ] CHANGELOG.md lists every change under [Unreleased]"
    echo "  [ ] manifest.json and hacs.json both at $version"
    echo ""
    confirm "Are all criteria met?"

    info "To promote to a final release:"
    echo "  1. Open a pull request: $RELEASE_BRANCH → main"
    echo "  2. Merging it triggers the 'Promote RC to Final Release' workflow, which:"
    echo "     - creates the v${version} tag and the final GitHub release"
    echo "     - deletes the RC and dev pre-releases"
    echo "     - opens the chore/changelog-v${version} PR stamping the CHANGELOG on main"
    echo ""
    success "Use: gh pr create --base main --head $RELEASE_BRANCH"
}

cmd_help() {
    cat << EOF
🚀 RC Helper - Release candidate manager

Usage: $0 [command] [options]

Commands:
  prepare [VERSION]                Dispatch 'Prepare Release Candidate' (rc1)
  increment [VERSION] [FIXES]      Dispatch 'Increment RC Version' (rc2, rc3, ...)
  status                           Show the RC pre-releases of the current version
  promote                          Check the release gates before the final release
  help                             Show this help

Typical workflow:
  1. Merge features and fixes into '$RELEASE_BRANCH'
  2. Bump manifest.json and hacs.json to the release version
  3. ./scripts/rc-helper.sh prepare → create rc1
  4. Test in production
  5. If fixes are needed:
     - Merge the fixes into '$RELEASE_BRANCH'
     - ./scripts/rc-helper.sh increment → create rc2, rc3, ...
  6. When everything is OK:
     - ./scripts/rc-helper.sh promote
     - Open the $RELEASE_BRANCH → main PR; its merge triggers the final release

Documentation:
    See docs/maintainers/RELEASE_PROCESS.md
EOF
}

main() {
    cd "$PROJECT_ROOT"

    local command="${1:-help}"
    shift || true

    case "$command" in
        prepare) cmd_prepare "$@" ;;
        increment) cmd_increment "$@" ;;
        status) cmd_status ;;
        promote) cmd_promote ;;
        help|--help|-h) cmd_help ;;
        *) error "Unknown command: $command (use 'help')" ;;
    esac
}

main "$@"
