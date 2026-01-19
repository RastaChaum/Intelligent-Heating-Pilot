#!/bin/bash
# Script helper pour gérer le workflow de développement

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

function print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

function print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

function print_error() {
    echo -e "${RED}❌ $1${NC}"
}

function create_feature_branch() {
    print_header "Création d'une branche feature"
    
    read -p "Nom de la feature (sans 'feature-'): " feature_name
    
    # Assurez-vous d'être sur integration
    git checkout integration
    git pull origin integration
    
    # Créez la branche
    git checkout -b "feature-$feature_name"
    
    print_success "Branche feature-$feature_name créée à partir de integration"
    print_warning "N'oubliez pas de mettre à jour le CHANGELOG.md !"
}

function create_fix_branch() {
    print_header "Création d'une branche fix"
    
    read -p "Nom du fix (sans 'fix-'): " fix_name
    
    # Assurez-vous d'être sur integration
    git checkout integration
    git pull origin integration
    
    # Créez la branche
    git checkout -b "fix-$fix_name"
    
    print_success "Branche fix-$fix_name créée à partir de integration"
    print_warning "N'oubliez pas de mettre à jour le CHANGELOG.md !"
}

function prepare_release() {
    print_header "Préparation d'une RC (Release Candidate)"
    
    # Vérifier qu'on est sur integration
    CURRENT_BRANCH=$(git branch --show-current)
    if [ "$CURRENT_BRANCH" != "integration" ]; then
        print_error "Vous devez être sur la branche integration"
        exit 1
    fi
    
    print_warning "Utiliser le script dedié : ./scripts/rc-helper.sh"
    echo ""
    echo "Pour préparer une RC :"
    echo "  $ ./scripts/rc-helper.sh prepare"
    echo ""
    echo "Pour voir le statut actuel :"
    echo "  $ ./scripts/rc-helper.sh status"
    echo ""
    echo "Pour incrémenter la RC (après corrections) :"
    echo "  $ ./scripts/rc-helper.sh increment"
    echo ""
    echo "Workflow RC complet :"
    echo "  1. Préparez RC1 : ./scripts/rc-helper.sh prepare"
    echo "  2. Testez sur votre instance HA"
    echo "  3. Si corrections : créez des branches fix-* vers integration"
    echo "  4. Incrémentez RC : ./scripts/rc-helper.sh increment"
    echo "  5. Retestez"
    echo "  6. Quand prêt : créez PR integration → main"
    echo "  7. Mergez PR → Release stable automatiquement"
}

function check_changelog() {
    print_header "Vérification du CHANGELOG"
    
    if ! git diff --cached --name-only | grep -q "CHANGELOG.md"; then
        print_error "CHANGELOG.md n'a pas été modifié"
        echo ""
        echo "Ajoutez une entrée dans la section [Unreleased]:"
        echo ""
        echo "### Added (pour features)"
        echo "- [Description orientée utilisateur]"
        echo ""
        echo "### Fixed (pour fixes)"
        echo "- [Description du problème corrigé]"
        exit 1
    fi
    
    print_success "CHANGELOG.md a été modifié"
}

function show_workflow() {
    cat << 'EOF'

📋 WORKFLOW DE DÉVELOPPEMENT - INTELLIGENT HEATING PILOT (RC Model)
════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│  1. NOUVELLE FONCTIONNALITÉ                                 │
└─────────────────────────────────────────────────────────────┘
   
   $ ./scripts/workflow-helper.sh feature
   
   → Créez votre branche feature-* depuis integration
   → Développez avec TDD (tests d'abord!)
   → Mettez à jour CHANGELOG.md (section [Unreleased])
   → Créez une PR vers integration
   → Les checks automatiques vérifient:
     - Nommage de branche (feature/*)
     - CHANGELOG mis à jour
     - Tests passent
     - Documentation (si nécessaire)

┌─────────────────────────────────────────────────────────────┐
│  2. CORRECTION DE BUG                                       │
└─────────────────────────────────────────────────────────────┘
   
   $ ./scripts/workflow-helper.sh fix
   
   → Créez votre branche fix-* depuis integration
   → Corrigez avec TDD (tests de régression!)
   → Mettez à jour CHANGELOG.md (section [Unreleased])
   → Créez une PR vers integration
   → Mêmes checks automatiques (fix/*)

┌─────────────────────────────────────────────────────────────┐
│  3. CYCLE DE RELEASE - PHASE RC (Release Candidate)        │
└─────────────────────────────────────────────────────────────┘
   
   a) PRÉPARER RC1
   
      $ ./scripts/rc-helper.sh prepare
      
      → Choisissez le type (major/minor/patch)
      → Version incrémentée (v0.4.4 → v0.5.0-rc1)
      → GITHUB_RELEASE_v0.5.0-rc1.md créé
      → Tag v0.5.0-rc1 créé
      → Pre-release GitHub créée
      → Issue de suivi créée
   
   b) TESTER RC1
   
      → Déployez sur votre instance Home Assistant
      → Testez toutes les nouvelles features
      → Signaler bugs sur l'issue de suivi
   
   c) CORRECTIONS PENDANT LES RCs
   
      $ git checkout integration
      $ ./scripts/workflow-helper.sh fix
      → Corrigez le bug
      → Créez PR vers integration
      → Mergez PR
      → Créez PR vide vers main (pour déclencher les checks)
      $ ./scripts/rc-helper.sh increment
      → Crée rc2, puis rc3, etc.
   
   d) RETESTEZ
   
      → Testez la nouvelle RC
      → Répétez jusqu'à satisfaction

┌─────────────────────────────────────────────────────────────┐
│  4. PUBLIER LA RELEASE STABLE                               │
└─────────────────────────────────────────────────────────────┘
   
   Quand la RC est stable:
   
      $ git checkout integration
      $ git pull origin integration
   
      → Créez une PR: integration → main
      → Titre: "chore: release v0.5.0"
      → Les checks vérifient:
        - Version incrémentée
        - CHANGELOG contient des entrées
        - RC pre-release existe
        - Tous les tests passent
   
      → Mergez la PR (sans squash!)
      → AUTOMATIQUEMENT:
        - Version finale créée (v0.5.0)
        - CHANGELOG mis à jour avec date
        - Release stable publiée
        - RCs nettoyées
        - HACS détecte la version

┌─────────────────────────────────────────────────────────────┐
│  5. COMMANDES UTILES                                        │
└─────────────────────────────────────────────────────────────┘
   
   Voir l'état de la RC actuelle :
      $ ./scripts/rc-helper.sh status
   
   Voir les versions disponibles :
      $ git tag | grep -v rc | tail -5
   
   Préparer une nouvelle RC :
      $ ./scripts/rc-helper.sh prepare
   
   Incrémenter RC après corrections :
      $ ./scripts/rc-helper.sh increment

┌─────────────────────────────────────────────────────────────┐
│  📚 DOCUMENTATION COMPLÈTE                                  │
└─────────────────────────────────────────────────────────────┘
   
   Workflow RC :     ./scripts/rc-helper.sh (version interactive)
   Workflow Dev :    ./scripts/workflow-helper.sh workflow
   Vérif Setup :     ./scripts/check-workflow-setup.sh

EOF
}

# Menu principal
case "${1:-}" in
    feature)
        create_feature_branch
        ;;
    fix)
        create_fix_branch
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
        echo "  feature          Créer une nouvelle branche feature"
        echo "  fix              Créer une nouvelle branche fix"
        echo "  prepare-release  Préparer une nouvelle release"
        echo "  check-changelog  Vérifier que le CHANGELOG est à jour"
        echo "  workflow         Afficher le workflow complet"
        echo ""
        echo "Pour les releases, utiliser : ./scripts/rc-helper.sh"
        echo ""
        echo "Pour plus d'aide: $0 workflow"
        ;;
esac
