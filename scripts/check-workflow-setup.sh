#!/bin/bash
# Script de vérification de la configuration du workflow GitHub

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

function check_ok() {
    echo -e "${GREEN}✅ $1${NC}"
}

function check_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

function check_error() {
    echo -e "${RED}❌ $1${NC}"
}

function check_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_header "Vérification de la configuration du workflow GitHub"

# Check 1: Vérifier que gh CLI et jq sont installés
print_header "1. Outils requis"
if command -v gh &> /dev/null; then
    check_ok "GitHub CLI (gh) est installé"
    gh --version | head -1
else
    check_error "GitHub CLI (gh) n'est pas installé"
    echo "   Installation: https://cli.github.com/"
    exit 1
fi

if command -v jq &> /dev/null; then
    check_ok "jq est installé"
else
    check_error "jq n'est pas installé (requis pour parsing JSON)"
    echo "   Installation: sudo apt install jq"
    exit 1
fi

# Check 2: Vérifier l'authentification GitHub
print_header "2. Authentification GitHub"
if gh auth status &> /dev/null; then
    check_ok "Authentifié sur GitHub"
    gh auth status 2>&1 | grep "Logged in"
else
    check_error "Non authentifié sur GitHub"
    echo "   Exécutez: gh auth login"
    exit 1
fi

# Check 3: Vérifier les branches
print_header "3. Branches Git"

CURRENT_BRANCH=$(git branch --show-current)
check_info "Branche actuelle: $CURRENT_BRANCH"

if git show-ref --verify --quiet refs/heads/main; then
    check_ok "Branche 'main' existe"
else
    check_error "Branche 'main' n'existe pas"
fi

if git show-ref --verify --quiet refs/heads/integration; then
    check_ok "Branche 'integration' existe localement"
else
    check_warning "Branche 'integration' n'existe pas localement"
    echo "   Créez-la avec: git checkout -b integration && git push -u origin integration"
fi

if git ls-remote --heads origin integration &> /dev/null; then
    check_ok "Branche 'integration' existe sur origin"
else
    check_warning "Branche 'integration' n'existe pas sur origin"
    echo "   Créez-la avec: git push -u origin integration"
fi

# Check 4: Vérifier les workflows
print_header "4. GitHub Actions Workflows"

WORKFLOWS=(
    "prepare-release-candidate.yml"
    "increment-rc-version.yml"
    "promote-rc-to-release.yml"
    "feature-fix-pr.yml"
    "integration-pr.yml"
    "cleanup-branches.yml"
    "code-quality.yml"
)

for workflow in "${WORKFLOWS[@]}"; do
    if [ -f ".github/workflows/$workflow" ]; then
        check_ok "Workflow $workflow existe"
    else
        check_error "Workflow $workflow manquant"
    fi
done

# Check 5: Vérifier les fichiers de documentation
print_header "5. Documentation"

DOCS=(
    ".github/README.md"
    ".github/WORKFLOW_GUIDE.md"
    ".github/BRANCH_PROTECTION_SETUP.md"
    ".github/pull_request_template.md"
    ".github/dependabot.yml"
)

for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        check_ok "$(basename $doc) existe"
    else
        check_warning "$(basename $doc) manquant (sera créé)"
    fi
done

# Check 6: Vérifier scripts
print_header "6. Scripts Helper"

if [ -f "scripts/workflow-helper.sh" ]; then
    check_ok "workflow-helper.sh existe"
    if [ -x "scripts/workflow-helper.sh" ]; then
        check_ok "workflow-helper.sh est exécutable"
    else
        check_warning "workflow-helper.sh n'est pas exécutable"
        echo "   Exécutez: chmod +x scripts/workflow-helper.sh"
    fi
else
    check_error "workflow-helper.sh manquant"
fi

# Check 7: Vérifier le CHANGELOG
print_header "7. CHANGELOG"

if [ -f "CHANGELOG.md" ]; then
    check_ok "CHANGELOG.md existe"
    
    if grep -q "## \[Unreleased\]" CHANGELOG.md; then
        check_ok "Section [Unreleased] présente dans CHANGELOG"
    else
        check_warning "Section [Unreleased] manquante dans CHANGELOG"
        echo "   Ajoutez une section ## [Unreleased] en haut du CHANGELOG"
    fi
else
    check_error "CHANGELOG.md manquant"
fi

# Check 8: Vérifier manifest.json et hacs.json
print_header "8. Versioning (manifest.json + hacs.json)"

if [ -f "custom_components/intelligent_heating_pilot/manifest.json" ]; then
    check_ok "manifest.json existe"
    
    MANIFEST_VERSION=$(jq -r '.version' custom_components/intelligent_heating_pilot/manifest.json)
    if [ -n "$MANIFEST_VERSION" ]; then
        check_ok "Version dans manifest.json: $MANIFEST_VERSION"
    else
        check_error "Version non trouvée dans manifest.json"
    fi
else
    check_error "manifest.json manquant"
fi

if [ -f "hacs.json" ]; then
    check_ok "hacs.json existe"
    
    HACS_VERSION=$(jq -r '.version' hacs.json)
    if [ -n "$HACS_VERSION" ]; then
        check_ok "Version dans hacs.json: $HACS_VERSION"
        
        if [ "$MANIFEST_VERSION" == "$HACS_VERSION" ]; then
            check_ok "Versions synchronisées (manifest.json = hacs.json)"
        else
            check_warning "Versions NON synchronisées ! manifest=$MANIFEST_VERSION, hacs=$HACS_VERSION"
        fi
    else
        check_error "Version non trouvée dans hacs.json"
    fi
else
    check_error "hacs.json manquant"
fi

# Check 9: Protection des branches (nécessite API GitHub)
print_header "9. Protection des branches (GitHub)"

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
if [ -n "$REPO" ]; then
    check_info "Repository: $REPO"
    
    # Vérifier protection de main
    if gh api "repos/$REPO/branches/main/protection" &> /dev/null; then
        check_ok "Branche 'main' est protégée"
    else
        check_warning "Branche 'main' n'est PAS protégée"
        echo "   Configurez dans: Settings → Branches → Add branch protection rule"
        echo "   Voir: .github/BRANCH_PROTECTION_SETUP.md"
    fi
    
    # Vérifier protection de integration
    if gh api "repos/$REPO/branches/integration/protection" &> /dev/null; then
        check_ok "Branche 'integration' est protégée"
    else
        check_warning "Branche 'integration' n'est PAS protégée"
        echo "   Configurez dans: Settings → Branches → Add branch protection rule"
        echo "   Voir: .github/BRANCH_PROTECTION_SETUP.md"
    fi
else
    check_warning "Impossible de vérifier les protections (repository non détecté)"
fi

# Check 10: Vérifier les releases
print_header "10. Releases GitHub"

RELEASES_COUNT=$(gh release list --limit 100 | wc -l)
if [ "$RELEASES_COUNT" -gt "0" ]; then
    check_ok "$RELEASES_COUNT release(s) trouvée(s)"
    echo ""
    gh release list --limit 5
else
    check_info "Aucune release trouvée (ou releases existantes)"
fi

# Check 11: Vérifier Actions activées
print_header "11. GitHub Actions"

WORKFLOW_RUNS=$(gh run list --limit 1 2>/dev/null | wc -l)
if [ "$WORKFLOW_RUNS" -gt "0" ]; then
    check_ok "GitHub Actions est activé (workflows ont été exécutés)"
else
    check_info "Aucun workflow exécuté (normal avant première PR)"
fi

# Résumé final
print_header "📋 RÉSUMÉ"

echo -e "\n${BLUE}Configuration locale:${NC}"
echo "  ✅ Workflows créés"
echo "  ✅ Scripts helper disponibles"

echo -e "\n${YELLOW}À faire sur GitHub (si pas encore fait):${NC}"
echo "  1. Créer branche 'integration' (si warning ci-dessus)"
echo "  2. Configurer protections de branches"
echo "  3. Activer Dependabot (automatique via dependabot.yml)"

echo -e "\n${GREEN}Prochaines étapes:${NC}"
echo "  1. Lire: .github/BRANCH_PROTECTION_SETUP.md"
echo "  2. Configurer les protections de branches sur GitHub"
echo "  3. Tester avec: ./scripts/workflow-helper.sh feature"

echo -e "\n${BLUE}Documentation complète:${NC}"
echo "  📖 .github/README.md - Index de toute la doc"
echo "  📖 .github/WORKFLOW_GUIDE.md - Guide du workflow"
echo "  🔧 .github/BRANCH_PROTECTION_SETUP.md - Setup GitHub"

echo ""
