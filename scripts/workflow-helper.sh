#!/bin/bash
# Development workflow helper.
#
# Branch names must match what the CI accepts (#198):
#   - feature-fix-pr.yml requires '(copilot/)?(feature|fix)/issue-NNN' or 'NNN-description';
#   - ci.yml only runs on pushes to 'feature/**' and 'fix/**'.
# This helper therefore creates 'feature/issue-NNN[-slug]' and 'fix/issue-NNN[-slug]'.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BASE_BRANCH="integration"

print_header() { echo -e "${BLUE}=== $1 ===${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# Builds '<kind>/issue-<number>[-<slug>]' from the user's answers.
# Usage: build_branch_name KIND ISSUE_NUMBER [DESCRIPTION]
build_branch_name() {
    local kind="$1" issue="$2" description="${3:-}"
    local slug
    slug=$(printf '%s' "$description" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
    if [ -n "$slug" ]; then
        echo "${kind}/issue-${issue}-${slug}"
    else
        echo "${kind}/issue-${issue}"
    fi
}

create_branch() {
    local kind="$1"
    print_header "Create a $kind branch"

    local issue description
    read -r -p "GitHub issue number: " issue
    if [[ ! "$issue" =~ ^[0-9]+$ ]]; then
        print_error "The issue number must be digits only (got '$issue')"
        exit 1
    fi
    read -r -p "Short description (optional, e.g. 'setup lifecycle'): " description

    local branch
    branch=$(build_branch_name "$kind" "$issue" "$description")

    git checkout "$BASE_BRANCH"
    git pull origin "$BASE_BRANCH"
    git checkout -b "$branch"

    print_success "Branch $branch created from $BASE_BRANCH"
    print_warning "Remember to update CHANGELOG.md under [Unreleased]!"
}

prepare_release() {
    print_header "Prepare a release candidate"
    print_warning "Use the dedicated script: ./scripts/rc-helper.sh"
    echo ""
    echo "Prepare an RC (dispatches the 'Prepare Release Candidate' workflow):"
    echo "  $ ./scripts/rc-helper.sh prepare"
    echo ""
    echo "Show the current status:"
    echo "  $ ./scripts/rc-helper.sh status"
    echo ""
    echo "Increment the RC after fixes (dispatches 'Increment RC Version'):"
    echo "  $ ./scripts/rc-helper.sh increment"
}

check_changelog() {
    print_header "CHANGELOG check"

    if ! git diff --cached --name-only | grep -q "CHANGELOG.md"; then
        print_error "CHANGELOG.md has not been modified"
        echo ""
        echo "Add an entry under the [Unreleased] section:"
        echo ""
        echo "### Added (for features)"
        echo "- [User-facing description]"
        echo ""
        echo "### Fixed (for fixes)"
        echo "- [Description of the fixed problem]"
        exit 1
    fi

    print_success "CHANGELOG.md has been modified"
}

show_workflow() {
    cat << 'EOF'

📋 DEVELOPMENT WORKFLOW - INTELLIGENT HEATING PILOT (RC model)
════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│  1. NEW FEATURE                                             │
└─────────────────────────────────────────────────────────────┘

   $ ./scripts/workflow-helper.sh feature

   → Creates feature/issue-NNN[-slug] from integration
   → Develop with TDD (tests first!)
   → Update CHANGELOG.md ([Unreleased] section)
   → Open a PR to integration
   → Automatic checks verify:
     - Branch naming (feature/issue-NNN, fix/issue-NNN or NNN-description)
     - CHANGELOG updated
     - Tests pass
     - Documentation (reminder for features)

┌─────────────────────────────────────────────────────────────┐
│  2. BUG FIX                                                 │
└─────────────────────────────────────────────────────────────┘

   $ ./scripts/workflow-helper.sh fix

   → Creates fix/issue-NNN[-slug] from integration
   → Fix with TDD (regression tests!)
   → Update CHANGELOG.md ([Unreleased] section)
   → Open a PR to integration
   → Same automatic checks

┌─────────────────────────────────────────────────────────────┐
│  3. RELEASE CYCLE - RC (release candidate) PHASE            │
└─────────────────────────────────────────────────────────────┘

   a) PREPARE RC1

      → Bump manifest.json and hacs.json to the release version
      $ ./scripts/rc-helper.sh prepare
      → Dispatches 'Prepare Release Candidate':
        tag vX.Y.Z-rc1 and its GitHub pre-release

   b) TEST RC1

      → Deploy on your Home Assistant instance
      → Test every new feature
      → Report bugs on the tracking issue

   c) FIXES DURING THE RC PHASE

      $ ./scripts/workflow-helper.sh fix
      → Fix the bug, open a PR to integration, merge it
      $ ./scripts/rc-helper.sh increment
      → Dispatches 'Increment RC Version': rc2, then rc3, etc.

   d) RETEST

      → Test the new RC
      → Repeat until satisfied

┌─────────────────────────────────────────────────────────────┐
│  4. PUBLISH THE STABLE RELEASE                              │
└─────────────────────────────────────────────────────────────┘

   When the RC is stable:

      $ ./scripts/rc-helper.sh promote

      → Open a PR: integration → main
      → Checks verify:
        - Version greater than main (manifest.json = hacs.json)
        - CHANGELOG has entries
        - An RC pre-release exists for exactly that version
        - All tests pass

      → Merge the PR (merge commit, no squash!)
      → AUTOMATICALLY:
        - Final release published (vX.Y.Z)
        - RC pre-releases deleted
        - chore/changelog-vX.Y.Z PR opened to stamp the CHANGELOG
          (approve and merge it)
        - HACS detects the version

┌─────────────────────────────────────────────────────────────┐
│  5. USEFUL COMMANDS                                         │
└─────────────────────────────────────────────────────────────┘

   Current RC status:
      $ ./scripts/rc-helper.sh status

   Available versions:
      $ gh release list --exclude-pre-releases --limit 5

┌─────────────────────────────────────────────────────────────┐
│  📚 DOCUMENTATION                                           │
└─────────────────────────────────────────────────────────────┘

   Release process:  docs/maintainers/RELEASE_PROCESS.md
   RC workflows:     docs/maintainers/RC_WORKFLOWS.md
   Setup check:      ./scripts/check-workflow-setup.sh

EOF
}

case "${1:-}" in
    feature)
        create_branch feature
        ;;
    fix)
        create_branch fix
        ;;
    prepare-release)
        prepare_release
        ;;
    check-changelog)
        check_changelog
        ;;
    workflow|help|--help|-h)
        show_workflow
        ;;
    *)
        echo "Intelligent Heating Pilot - Workflow Helper"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  feature          Create a feature/issue-NNN branch"
        echo "  fix              Create a fix/issue-NNN branch"
        echo "  prepare-release  Show how to prepare a release candidate"
        echo "  check-changelog  Check that CHANGELOG.md is staged"
        echo "  workflow         Show the full workflow"
        echo ""
        echo "For releases, use: ./scripts/rc-helper.sh"
        ;;
esac
