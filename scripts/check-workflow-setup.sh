#!/bin/bash
# Checks the local and GitHub setup of the development and release workflows.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

MANIFEST="custom_components/intelligent_heating_pilot/manifest.json"

function print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

function check_ok() { echo -e "${GREEN}✅ $1${NC}"; }
function check_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
function check_error() { echo -e "${RED}❌ $1${NC}"; }
function check_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

print_header "GitHub workflow setup check"

# Check 1: required tools
print_header "1. Required tools"
if command -v gh &> /dev/null; then
    check_ok "GitHub CLI (gh) is installed"
    gh --version | head -1
else
    check_error "GitHub CLI (gh) is not installed"
    echo "   Install: https://cli.github.com/"
    exit 1
fi

if command -v jq &> /dev/null; then
    check_ok "jq is installed"
else
    check_error "jq is not installed (required to parse JSON)"
    echo "   Install: sudo apt install jq"
    exit 1
fi

# Check 2: GitHub authentication
print_header "2. GitHub authentication"
if gh auth status &> /dev/null; then
    check_ok "Authenticated on GitHub"
    gh auth status 2>&1 | grep "Logged in"
else
    check_error "Not authenticated on GitHub"
    echo "   Run: gh auth login"
    exit 1
fi

# Check 3: branches
print_header "3. Git branches"

CURRENT_BRANCH=$(git branch --show-current)
check_info "Current branch: $CURRENT_BRANCH"

if git show-ref --verify --quiet refs/heads/main; then
    check_ok "Branch 'main' exists"
else
    check_error "Branch 'main' does not exist"
fi

if git show-ref --verify --quiet refs/heads/integration; then
    check_ok "Branch 'integration' exists locally"
else
    check_warning "Branch 'integration' does not exist locally"
    echo "   Create it with: git checkout -b integration && git push -u origin integration"
fi

if [ -n "$(git ls-remote --heads origin integration 2>/dev/null)" ]; then
    check_ok "Branch 'integration' exists on origin"
else
    check_warning "Branch 'integration' does not exist on origin"
    echo "   Create it with: git push -u origin integration"
fi

# Check 4: workflows
print_header "4. GitHub Actions workflows"

WORKFLOWS=(
    "ci.yml"
    "code-quality.yml"
    "feature-fix-pr.yml"
    "integration-pr.yml"
    "prepare-release-candidate.yml"
    "increment-rc-version.yml"
    "update-prerelease-on-integration-merge.yml"
    "promote-rc-to-release.yml"
    "cleanup-branches.yml"
    "workflow-lint.yml"
)

for workflow in "${WORKFLOWS[@]}"; do
    if [ -f ".github/workflows/$workflow" ]; then
        check_ok "Workflow $workflow exists"
    else
        check_error "Workflow $workflow missing"
    fi
done

# Check 5: documentation
print_header "5. Documentation"

DOCS=(
    "docs/maintainers/RELEASE_PROCESS.md"
    "docs/maintainers/RC_WORKFLOWS.md"
    "docs/contributors/WORKFLOW_MODEL.md"
    ".github/pull_request_template.md"
    ".github/dependabot.yml"
)

for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        check_ok "$doc exists"
    else
        check_warning "$doc missing"
    fi
done

# Check 6: helper scripts
print_header "6. Helper scripts"

for script in workflow-helper.sh rc-helper.sh release-gates.sh; do
    if [ ! -f "scripts/$script" ]; then
        check_error "$script missing"
    elif [ -x "scripts/$script" ]; then
        check_ok "$script exists and is executable"
    else
        check_warning "$script is not executable"
        echo "   Run: chmod +x scripts/$script"
    fi
done

# Check 7: CHANGELOG
print_header "7. CHANGELOG"

if [ -f "CHANGELOG.md" ]; then
    check_ok "CHANGELOG.md exists"

    if grep -q "^## \[Unreleased\]$" CHANGELOG.md; then
        check_ok "[Unreleased] section present in CHANGELOG"
    else
        check_warning "[Unreleased] section missing in CHANGELOG"
        echo "   Add a ## [Unreleased] section at the top of the CHANGELOG"
    fi
else
    check_error "CHANGELOG.md missing"
fi

# Check 8: manifest.json and hacs.json
print_header "8. Versioning (manifest.json + hacs.json)"

MANIFEST_VERSION=""
if [ -f "$MANIFEST" ]; then
    check_ok "manifest.json exists"

    MANIFEST_VERSION=$(jq -r '.version' "$MANIFEST")
    if [ -n "$MANIFEST_VERSION" ]; then
        check_ok "manifest.json version: $MANIFEST_VERSION"
    else
        check_error "No version in manifest.json"
    fi
else
    check_error "manifest.json missing"
fi

if [ -f "hacs.json" ]; then
    check_ok "hacs.json exists"

    HACS_VERSION=$(jq -r '.version' hacs.json)
    if [ -n "$HACS_VERSION" ]; then
        check_ok "hacs.json version: $HACS_VERSION"

        if [ "$MANIFEST_VERSION" == "$HACS_VERSION" ]; then
            check_ok "Versions in sync (manifest.json = hacs.json)"
        else
            check_warning "Versions NOT in sync! manifest=$MANIFEST_VERSION, hacs=$HACS_VERSION"
        fi
    else
        check_error "No version in hacs.json"
    fi
else
    check_error "hacs.json missing"
fi

# Check 9: branch rules (GitHub API)
print_header "9. Branch rules (GitHub)"

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
if [ -n "$REPO" ]; then
    check_info "Repository: $REPO"

    for branch in main integration; do
        RULE_TYPES=$(gh api "repos/$REPO/rules/branches/$branch" --jq '[.[].type] | unique | join(", ")' 2>/dev/null || echo "")
        if [ -n "$RULE_TYPES" ]; then
            check_ok "Branch '$branch' has rules: $RULE_TYPES"
        else
            check_warning "Branch '$branch' has NO rules"
            echo "   Configure them in: Settings → Rules → Rulesets (see ./scripts/setup-workflow.sh)"
        fi
    done
else
    check_warning "Cannot check branch rules (repository not detected)"
fi

# Check 10: releases
print_header "10. GitHub releases"

RELEASES_COUNT=$(gh release list --limit 100 | wc -l)
if [ "$RELEASES_COUNT" -gt "0" ]; then
    check_ok "$RELEASES_COUNT release(s) found"
    echo ""
    gh release list --limit 5
else
    check_info "No release found"
fi

# Check 11: GitHub Actions enabled
print_header "11. GitHub Actions"

WORKFLOW_RUNS=$(gh run list --limit 1 2>/dev/null | wc -l)
if [ "$WORKFLOW_RUNS" -gt "0" ]; then
    check_ok "GitHub Actions is enabled (workflows have run)"
else
    check_info "No workflow run yet (expected before the first PR)"
fi

# Summary
print_header "📋 SUMMARY"

echo -e "\n${YELLOW}To do on GitHub (if not done yet):${NC}"
echo "  1. Create the 'integration' branch (if warned above)"
echo "  2. Configure the branch rulesets (see ./scripts/setup-workflow.sh)"
echo "  3. Enable Dependabot (automatic through dependabot.yml)"

echo -e "\n${GREEN}Next steps:${NC}"
echo "  1. Read: docs/maintainers/RELEASE_PROCESS.md"
echo "  2. Try: ./scripts/workflow-helper.sh feature"

echo ""
