#!/bin/bash
# Quick start - one-command initial setup of the development workflow

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🚀 Intelligent Heating Pilot - GitHub workflow          ║
║   Automatic initial setup                                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}\n"

echo -e "${GREEN}This script sets up:${NC}"
echo "  1. The integration branch"
echo "  2. Its synchronisation with main"
echo "  3. Its push to origin"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo -e "${BLUE}━━━ Step 1/4: Check the main branch ━━━${NC}"
git checkout main
git pull origin main
echo -e "${GREEN}✅ main is up to date${NC}"

echo ""
echo -e "${BLUE}━━━ Step 2/4: Create or update the integration branch ━━━${NC}"
if git show-ref --verify --quiet refs/heads/integration; then
    echo "The integration branch already exists locally"
    git checkout integration
    git merge main --no-edit || true
else
    echo "Creating the integration branch from main"
    git checkout -b integration
fi
echo -e "${GREEN}✅ integration branch ready${NC}"

echo ""
echo -e "${BLUE}━━━ Step 3/4: Push to origin ━━━${NC}"
git push -u origin integration
echo -e "${GREEN}✅ integration branch pushed to GitHub${NC}"

echo ""
echo -e "${BLUE}━━━ Step 4/4: Final check ━━━${NC}"
./scripts/check-workflow-setup.sh | grep -E "✅|⚠️|❌" | head -20

echo ""
echo -e "${GREEN}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ✅ Local setup complete!                                ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}⚠️  ACTION REQUIRED on GitHub:${NC}"
echo ""
echo "  Go to: https://github.com/RastaChaum/Intelligent-Heating-Pilot/settings/rules"
echo ""
echo "  📋 See docs/maintainers/RELEASE_PROCESS.md for the release process."
echo ""
cat << 'EOF'

  ┌─────────────────────────────────────────────┐
  │  Ruleset for MAIN                           │
  └─────────────────────────────────────────────┘

  1. Target branch: main
  2. ✅ Require a pull request before merging (1 approval)
  3. ✅ Allowed merge methods: merge commit only
  4. ✅ Require status checks to pass: validate-integration-pr
     It passes for the 'integration' branch (release gates) and for
     the 'chore/changelog-vX.Y.Z' PR the release workflow opens to
     stamp the CHANGELOG (only CHANGELOG.md may change in it). Every
     other source branch fails it.
  5. ✅ Block force pushes
  6. Save changes

  A PR opened with GITHUB_TOKEN does not trigger workflows. To have
  the CHANGELOG stamp PR checked automatically, add a RELEASE_PR_TOKEN
  repository secret (fine-grained PAT or GitHub App token with
  "Pull requests: write"). Without it, close and reopen that PR to
  run its checks.

  ┌─────────────────────────────────────────────┐
  │  Ruleset for INTEGRATION                    │
  └─────────────────────────────────────────────┘

  1. Target branch: integration
  2. ✅ Require a pull request before merging
  3. ✅ Require status checks to pass: validate-pr
  4. ✅ Allow GitHub Actions to bypass (the release workflow pushes
     the CHANGELOG stamp merge to integration)
  5. Save changes

EOF

echo ""
echo -e "${GREEN}📚 Documentation:${NC}"
echo "  📖 docs/maintainers/RELEASE_PROCESS.md - Release process"
echo "  📖 docs/maintainers/RC_WORKFLOWS.md - RC workflows"
echo "  📖 docs/contributors/WORKFLOW_MODEL.md - One PR per feature"
echo ""
echo -e "${GREEN}🎯 Start developing:${NC}"
echo "  ./scripts/workflow-helper.sh feature"
echo ""
