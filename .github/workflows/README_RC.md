# Release Candidate (RC) Workflow

Ce dossier contient les workflows GitHub Actions pour gérer les Release Candidates.

## Workflows

### 1. `prepare-release-candidate.yml`
**Déclenchement**: Manuel (workflow_dispatch)
**Branche**: `integration`
**Objectif**: Créer la première Release Candidate (rc1) pour une nouvelle version

**Actions**:
- Valide le format de version
- Extrait les changements du CHANGELOG.md
- Crée le fichier `GITHUB_RELEASE_vX.Y.Z.md`
- Crée le tag `vX.Y.Z-rc1`
- Crée une pre-release GitHub
- Crée une issue de suivi pour les tests

**Usage**:
- Via GitHub Actions UI: Actions → Prepare Release Candidate → Run workflow
- Via CLI: `./scripts/rc-helper.sh prepare`

### 2. `increment-rc-version.yml`
**Déclenchement**: Manuel (workflow_dispatch)
**Branche**: `integration`
**Objectif**: Incrémenter le numéro de RC après corrections (rc2, rc3, etc.)

**Actions**:
- Trouve le dernier RC pour la version
- Incrémente le numéro (rc1 → rc2)
- Met à jour `GITHUB_RELEASE_vX.Y.Z.md` avec les corrections
- Crée le nouveau tag
- Supprime l'ancienne pre-release
- Crée une nouvelle pre-release
- Commente sur l'issue de suivi

**Usage**:
- Via GitHub Actions UI: Actions → Increment RC Version → Run workflow
- Via CLI: `./scripts/rc-helper.sh increment`

### 3. `promote-rc-to-release.yml`
**Déclenchement**: Automatique (PR merge `integration` → `main`)
**Branche**: `main`
**Objectif**: Promouvoir un RC testé en release finale stable

**Actions**:
- Extrait la version du manifest.json
- Met à jour CHANGELOG.md avec la date de release
- Synchronise les numéros de version dans tous les fichiers
- Crée le tag final `vX.Y.Z`
- Crée la release GitHub stable (non pre-release)
- Ferme les issues référencées
- Supprime les pre-releases RC
- Ferme l'issue de suivi RC

**Usage**: Automatique lors du merge de la PR `integration → main`

## Flux de travail typique

```
┌─────────────────────┐
│   INTEGRATION       │
│                     │
│  1. Develop         │
│  2. Update CHANGELOG│
│  3. prepare RC      │  ← ./scripts/rc-helper.sh prepare
│     v0.5.0-rc1      │
└──────────┬──────────┘
           │
           │ Test in production
           │
           ▼
      ┌─────────┐
      │ Bugs?   │
      └─────────┘
           │
    ┌──────┴──────┐
    │             │
   YES           NO
    │             │
    ▼             ▼
┌──────────┐  ┌────────────────┐
│ Fix bugs │  │ Create PR      │
│ Increment│  │ integration    │
│ RC       │  │    ↓           │
│ v0.5.0-  │  │  main          │
│   rc2    │  └────────────────┘
└────┬─────┘         │
     │               │
     │               ▼
     │      ┌────────────────────┐
     │      │ Merge triggers:    │
     │      │ - Update CHANGELOG │
     │      │ - Create v0.5.0    │
     │      │ - Delete RCs       │
     │      │ - Close issues     │
     └──────┤ → FINAL RELEASE    │
            └────────────────────┘
```

## Bonnes pratiques

1. **Toujours créer un RC** pour les releases non-triviales
2. **Tester en production** avant de merger vers main
3. **Documenter les corrections** lors de l'incrémentation des RC
4. **Ne pas créer de tags manuellement** - utiliser les workflows
5. **Garder le CHANGELOG à jour** pendant le développement

## Sécurité

Les workflows nécessitent les permissions suivantes:
- `contents: write` - Pour créer tags et releases
- `issues: write` - Pour créer/fermer issues
- `pull-requests: write` - Pour commenter sur les PRs

## Dépannage

### Le workflow ne se déclenche pas
- Vérifiez que vous êtes sur la bonne branche (`integration` pour prepare/increment)
- Vérifiez les permissions du workflow
- Consultez l'onglet Actions pour les erreurs

### Plusieurs RCs créés par erreur
```bash
# Supprimer un RC
gh release delete v0.5.0-rc3 --yes
git push origin :refs/tags/v0.5.0-rc3
```

### Redémarrer le processus RC
1. Supprimer tous les tags RC pour la version
2. Supprimer les pre-releases sur GitHub
3. Fermer l'issue de suivi
4. Recommencer avec `prepare`

## Voir aussi

- [AUTOMATED_RELEASE_GUIDE.md](../../AUTOMATED_RELEASE_GUIDE.md) - Guide complet
- [scripts/rc-helper.sh](../../scripts/rc-helper.sh) - Script CLI helper
- [CHANGELOG.md](../../CHANGELOG.md) - Historique des versions
