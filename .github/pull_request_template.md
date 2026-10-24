# Description

<!-- Décrivez clairement ce que fait cette PR, du point de vue de l'utilisateur -->

## Type de changement

- [ ] 🐛 Correction de bug (fix)
- [ ] ✨ Nouvelle fonctionnalité (feature)
- [ ] 📚 Documentation uniquement
- [ ] 🔧 Amélioration technique (refactoring, performance)
- [ ] ⚠️ Breaking change (modification majeure)

## CHANGELOG

- [ ] J'ai mis à jour le CHANGELOG.md dans la section `[Unreleased]`
- [ ] L'entrée du CHANGELOG est orientée utilisateur (pas de détails techniques)

```markdown
<!-- Copiez ici l'entrée que vous avez ajoutée au CHANGELOG -->

```

## Documentation

- [ ] La documentation utilisateur a été mise à jour (README.md, docs/)
- [ ] Aucune mise à jour de documentation nécessaire (correction interne)

## Tests

- [ ] Les tests unitaires passent (`poetry run pytest tests/unit`)
- [ ] J'ai ajouté des tests pour couvrir mes changements
- [ ] Les tests d'intégration passent (`poetry run pytest tests/integration`)
- [ ] J'ai testé sur une instance Home Assistant réelle

## Versioning (pour release)

- [ ] Version incrémentée dans `manifest.json`
- [ ] Version incrémentée dans `hacs.json` (doit correspondre à manifest.json)

## Checklist

- [ ] Mon code respecte les principes DDD (Domain-Driven Design)
- [ ] J'ai suivi le principe TDD (tests écrits avant le code)
- [ ] Toutes mes fonctions ont des type hints
- [ ] J'ai ajouté des docstrings pour les nouvelles fonctions/classes
- [ ] Le logging est approprié (INFO pour entry/exit, DEBUG pour détails)
- [ ] Aucun import de `homeassistant.*` dans la couche domain
- [ ] J'ai utilisé Poetry pour toutes les commandes (`poetry run`)

## Détails supplémentaires

<!-- Ajoutez tout contexte supplémentaire, captures d'écran, exemples, etc. -->

---

**Pour les reviewers :**

- [ ] Le code respecte l'architecture DDD
- [ ] Les tests sont suffisants et pertinents
- [ ] Le CHANGELOG est clair et orienté utilisateur
- [ ] La documentation est à jour si nécessaire
- [ ] Les versions sont synchronisées (manifest.json = hacs.json)
