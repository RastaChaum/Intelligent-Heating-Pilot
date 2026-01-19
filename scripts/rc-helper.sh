#!/usr/bin/env bash

# Script helper pour gérer les Release Candidates
# Usage: ./scripts/rc-helper.sh [command] [options]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Couleurs pour l'affichage
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonctions d'affichage
info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

# Fonction pour extraire la version du manifest.json
get_current_version() {
    grep -oP '"version":\s*"\K[^"]+' "$PROJECT_ROOT/custom_components/intelligent_heating_pilot/manifest.json"
}

# Fonction pour vérifier si on est sur la branche integration
check_integration_branch() {
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$CURRENT_BRANCH" != "integration" ]; then
        error "Vous devez être sur la branche 'integration' pour cette opération"
    fi
}

# Fonction pour vérifier que le working directory est propre
check_clean_working_directory() {
    if [ -n "$(git status --porcelain)" ]; then
        error "Le working directory n'est pas propre. Committez ou stashez vos changements."
    fi
}

# Commande: prepare
# Prépare une nouvelle release candidate
cmd_prepare() {
    info "Préparation d'une nouvelle Release Candidate..."
    
    check_integration_branch
    check_clean_working_directory
    
    # Demander la version
    read -p "Version de la release (ex: 0.5.0): " VERSION
    
    if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        error "Format de version invalide. Utilisez X.Y.Z"
    fi
    
    RC_TAG="v${VERSION}-rc1"
    
    # Vérifier si le RC existe déjà
    if git rev-parse "$RC_TAG" >/dev/null 2>&1; then
        error "Le tag $RC_TAG existe déjà. Utilisez 'increment' pour créer rc2, rc3, etc."
    fi
    
    info "Vérification du CHANGELOG..."
    if ! grep -q "## \[Unreleased\]" CHANGELOG.md; then
        error "Section [Unreleased] manquante dans CHANGELOG.md"
    fi
    
    # Extraire les changements du CHANGELOG
    CHANGELOG_CONTENT=$(awk '/## \[Unreleased\]/,/## \[/' CHANGELOG.md | sed '1d;$d')
    if [ -z "$CHANGELOG_CONTENT" ]; then
        error "Aucun changement dans la section [Unreleased] du CHANGELOG.md"
    fi
    
    info "Création du fichier GITHUB_RELEASE_v${VERSION}.md..."
    cat > "GITHUB_RELEASE_v${VERSION}.md" << EOF
# Release v${VERSION} - Release Candidate

## 🧪 Release Candidate
Cette version est une **release candidate** destinée aux tests en production et aux beta-testeurs.

${CHANGELOG_CONTENT}

---

## ⚠️ Important
Cette version est en phase de test. Veuillez remonter tout problème via les Issues GitHub.
EOF
    
    success "Fichier de release notes créé"
    
    # Demander confirmation
    warning "Prêt à créer le RC ${RC_TAG}"
    echo "Fichiers à committer:"
    echo "  - GITHUB_RELEASE_v${VERSION}.md"
    echo ""
    read -p "Continuer? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Opération annulée"
    fi
    
    # Committer et créer le tag
    git add "GITHUB_RELEASE_v${VERSION}.md"
    git commit -m "chore(release): prepare RC for v${VERSION}"
    git push origin integration
    
    git tag -a "$RC_TAG" -m "Release Candidate v${VERSION}-rc1"
    git push origin "$RC_TAG"
    
    success "Release Candidate créée: $RC_TAG"
    info "Une pre-release GitHub sera créée automatiquement par le workflow"
    info "Surveillez: https://github.com/$(git config remote.origin.url | sed 's/.*://;s/.git$//')/actions"
}

# Commande: increment
# Incrémente le numéro de RC
cmd_increment() {
    info "Incrémentation du numéro de RC..."
    
    check_integration_branch
    check_clean_working_directory
    
    # Demander la version de base
    read -p "Version de base (ex: 0.5.0): " VERSION
    
    # Trouver le dernier RC
    LAST_RC=$(git tag -l "v${VERSION}-rc*" | sort -V | tail -1)
    
    if [ -z "$LAST_RC" ]; then
        error "Aucun RC trouvé pour v${VERSION}. Utilisez 'prepare' d'abord."
    fi
    
    # Extraire et incrémenter le numéro RC
    LAST_RC_NUM=$(echo "$LAST_RC" | grep -oP 'rc\K\d+')
    NEXT_RC_NUM=$((LAST_RC_NUM + 1))
    NEXT_RC_TAG="v${VERSION}-rc${NEXT_RC_NUM}"
    
    info "Dernier RC: $LAST_RC"
    info "Prochain RC: $NEXT_RC_TAG"
    
    # Demander description des corrections
    echo ""
    echo "Décrivez les corrections apportées dans ce RC:"
    echo "(Terminez avec une ligne vide)"
    FIX_DESCRIPTION=""
    while IFS= read -r line; do
        [ -z "$line" ] && break
        FIX_DESCRIPTION="${FIX_DESCRIPTION}${line}\n"
    done
    
    if [ -z "$FIX_DESCRIPTION" ]; then
        error "Description des corrections requise"
    fi
    
    # Mettre à jour le fichier de release notes
    cat >> "GITHUB_RELEASE_v${VERSION}.md" << EOF

---

## 🔧 RC ${NEXT_RC_NUM} - $(date +%Y-%m-%d)

$(echo -e "$FIX_DESCRIPTION")
EOF
    
    success "Release notes mises à jour"
    
    # Demander confirmation
    warning "Prêt à créer le RC ${NEXT_RC_TAG}"
    read -p "Continuer? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Opération annulée"
    fi
    
    # Committer et créer le tag
    git add "GITHUB_RELEASE_v${VERSION}.md"
    git commit -m "chore(release): update RC notes for v${VERSION}-rc${NEXT_RC_NUM}"
    git push origin integration
    
    git tag -a "$NEXT_RC_TAG" -m "Release Candidate v${VERSION}-rc${NEXT_RC_NUM}

$(echo -e "$FIX_DESCRIPTION")"
    git push origin "$NEXT_RC_TAG"
    
    success "Release Candidate incrémentée: $NEXT_RC_TAG"
    info "Une nouvelle pre-release sera créée automatiquement"
}

# Commande: status
# Affiche le statut des RC actuels
cmd_status() {
    info "Statut des Release Candidates..."
    
    CURRENT_VERSION=$(get_current_version)
    info "Version actuelle (manifest.json): $CURRENT_VERSION"
    
    echo ""
    echo "Release Candidates pour v${CURRENT_VERSION}:"
    RC_TAGS=$(git tag -l "v${CURRENT_VERSION}-rc*" | sort -V)
    
    if [ -z "$RC_TAGS" ]; then
        warning "Aucun RC trouvé pour v${CURRENT_VERSION}"
    else
        echo "$RC_TAGS" | while read tag; do
            DATE=$(git log -1 --format=%ai "$tag" | cut -d' ' -f1)
            echo "  📌 $tag (créé le $DATE)"
        done
        
        LATEST_RC=$(echo "$RC_TAGS" | tail -1)
        success "Dernier RC: $LATEST_RC"
    fi
    
    # Vérifier si le fichier de release notes existe
    NOTES_FILE="GITHUB_RELEASE_v${CURRENT_VERSION}.md"
    if [ -f "$NOTES_FILE" ]; then
        success "Fichier de release notes: $NOTES_FILE"
    else
        warning "Fichier de release notes absent: $NOTES_FILE"
    fi
}

# Commande: promote
# Prépare la promotion vers release finale
cmd_promote() {
    info "Préparation pour la promotion en release finale..."
    
    check_integration_branch
    check_clean_working_directory
    
    CURRENT_VERSION=$(get_current_version)
    info "Version actuelle: $CURRENT_VERSION"
    
    # Vérifier qu'un RC existe
    RC_TAGS=$(git tag -l "v${CURRENT_VERSION}-rc*" | sort -V)
    if [ -z "$RC_TAGS" ]; then
        error "Aucun RC trouvé pour v${CURRENT_VERSION}"
    fi
    
    LATEST_RC=$(echo "$RC_TAGS" | tail -1)
    success "Dernier RC: $LATEST_RC"
    
    # Vérifier le fichier de release notes
    NOTES_FILE="GITHUB_RELEASE_v${CURRENT_VERSION}.md"
    if [ ! -f "$NOTES_FILE" ]; then
        error "Fichier de release notes manquant: $NOTES_FILE"
    fi
    
    echo ""
    warning "Checklist avant promotion:"
    echo "  [ ] Tous les tests RC passés avec succès"
    echo "  [ ] Aucun bug critique restant"
    echo "  [ ] Documentation à jour"
    echo "  [ ] CHANGELOG.md contient tous les changements"
    echo "  [ ] Versions synchronisées dans tous les fichiers"
    echo ""
    read -p "Tous les critères sont-ils remplis? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        error "Vérifiez d'abord tous les critères"
    fi
    
    info "Pour promouvoir en release finale:"
    echo "  1. Créez une Pull Request: integration → main"
    echo "  2. Le merge déclenchera automatiquement le workflow de release"
    echo "  3. Le workflow va:"
    echo "     - Mettre à jour le CHANGELOG"
    echo "     - Créer le tag v${CURRENT_VERSION}"
    echo "     - Créer la release finale GitHub"
    echo "     - Fermer les issues référencées"
    echo "     - Nettoyer les pre-releases RC"
    echo ""
    success "Utilisez: gh pr create --base main --head integration"
}

# Commande: help
cmd_help() {
    cat << EOF
🚀 RC Helper - Gestionnaire de Release Candidates

Usage: $0 [command]

Commands:
  prepare   Préparer une nouvelle Release Candidate (rc1)
  increment Incrémenter le numéro de RC (rc2, rc3, ...)
  status    Afficher le statut des RC actuels
  promote   Préparer la promotion en release finale
  help      Afficher cette aide

Workflow typique:
  1. Sur 'integration', développer les fonctionnalités
  2. ./scripts/rc-helper.sh prepare → Créer rc1
  3. Tester en production
  4. Si corrections nécessaires:
     - Faire les corrections sur 'integration'
     - ./scripts/rc-helper.sh increment → Créer rc2, rc3, ...
  5. Quand tout OK:
     - ./scripts/rc-helper.sh promote
     - Créer PR integration → main
     - Le merge déclenche la release finale

Documentation:
  Voir AUTOMATED_RELEASE_GUIDE.md pour plus de détails
EOF
}

# Point d'entrée principal
main() {
    cd "$PROJECT_ROOT"
    
    COMMAND="${1:-help}"
    
    case "$COMMAND" in
        prepare)
            cmd_prepare
            ;;
        increment)
            cmd_increment
            ;;
        status)
            cmd_status
            ;;
        promote)
            cmd_promote
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            error "Commande inconnue: $COMMAND (utilisez 'help' pour l'aide)"
            ;;
    esac
}

main "$@"
