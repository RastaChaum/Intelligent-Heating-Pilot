#!/bin/bash
# Quick Start - Configuration initiale du workflow en une commande

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🚀 Intelligent Heating Pilot - Workflow GitHub         ║
║   Configuration Initiale Automatique                     ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}\n"

echo -e "${GREEN}Ce script va configurer automatiquement :${NC}"
echo "  1. Branche integration"
echo "  2. Synchronisation avec main"
echo "  3. Push vers origin"
echo ""

read -p "Continuer ? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Annulé."
    exit 0
fi

echo ""
echo -e "${BLUE}━━━ Étape 1/4 : Vérification branche main ━━━${NC}"
git checkout main
git pull origin main
echo -e "${GREEN}✅ Branche main à jour${NC}"

echo ""
echo -e "${BLUE}━━━ Étape 2/4 : Création/mise à jour branche integration ━━━${NC}"
if git show-ref --verify --quiet refs/heads/integration; then
    echo "Branche integration existe déjà localement"
    git checkout integration
    git merge main --no-edit || true
else
    echo "Création de la branche integration depuis main"
    git checkout -b integration
fi
echo -e "${GREEN}✅ Branche integration prête${NC}"

echo ""
echo -e "${BLUE}━━━ Étape 3/4 : Push vers origin ━━━${NC}"
git push -u origin integration
echo -e "${GREEN}✅ Branche integration poussée sur GitHub${NC}"

echo ""
echo -e "${BLUE}━━━ Étape 4/4 : Vérification finale ━━━${NC}"
./scripts/check-workflow-setup.sh | grep -E "✅|⚠️|❌" | head -20

echo ""
echo -e "${GREEN}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ✅ Configuration locale terminée !                      ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}⚠️  ACTION REQUISE sur GitHub :${NC}"
echo ""
echo "  Allez sur : https://github.com/RastaChaum/Intelligent-Heating-Pilot/settings/branches"
echo ""
echo "  📋 Suivez les instructions dans :"
echo "     .github/RC_MIGRATION_GUIDE.md"
echo ""
echo "  Ou lisez directement :"
cat << 'EOF'

  ┌─────────────────────────────────────────────┐
  │  Configuration Branch Protection pour MAIN │
  └─────────────────────────────────────────────┘

  1. Cliquez "Add branch protection rule"
  2. Branch name pattern: main
  3. ✅ Require a pull request before merging
  4. ✅ Do not allow bypassing the above settings
  5. ✅ Restrict who can push (add: integration)
  6. ✅ Require status checks to pass: integration-pr
  7. ❌ NE PAS activer "Require linear history"
  8. Save changes

  ┌────────────────────────────────────────────────────┐
  │  Configuration Branch Protection pour INTEGRATION │
  └────────────────────────────────────────────────────┘

  1. Cliquez "Add branch protection rule"
  2. Branch name pattern: integration
  3. ✅ Require a pull request before merging
  4. ✅ Require status checks to pass: feature-fix-pr
  5. ✅ Allow force pushes
  6. Save changes

EOF

echo ""
echo -e "${GREEN}📚 Documentation complète :${NC}"
echo "  📖 .github/README.md - Point d'entrée"
echo "  📖 .github/WORKFLOW_GUIDE.md - Guide détaillé"
echo "  🔧 .github/BRANCH_PROTECTION_SETUP.md - Setup GitHub"
echo ""
echo -e "${GREEN}🎯 Commencer à développer :${NC}"
echo "  ./scripts/workflow-helper.sh feature"
echo ""
