# 🔄 Migration vers le Workflow Release Candidate

## Changements apportés (Janvier 2025)

Le processus de release a été amélioré pour intégrer une **phase de Release Candidate (RC)** permettant de tester en production avant les releases finales.

### Ancien workflow (conservé pour référence)

```
integration → main (merge) → tag vX.Y.Z → pre-release automatique
```

### Nouveau workflow (recommandé)

```
integration → tag vX.Y.Z-rc1 → pre-release RC → tests
           → corrections → tag vX.Y.Z-rc2 → pre-release RC → tests
           → corrections → tag vX.Y.Z-rc3 → ...
           → stable → PR integration → main → tag vX.Y.Z → release finale
```

## Avantages du nouveau workflow

1. **Tests en production sécurisés** : Les beta-testeurs peuvent tester les RC
2. **Itérations rapides** : Corrections et nouvelles RC sans affecter main
3. **Stabilité garantie** : Seules les versions testées arrivent en production
4. **Traçabilité** : Historique complet des RC (rc1, rc2, rc3...)
5. **Automatisation complète** : Scripts et workflows pour tout gérer

## Nouveaux fichiers

### Workflows GitHub Actions
- `.github/workflows/prepare-release-candidate.yml` - Créer rc1
- `.github/workflows/increment-rc-version.yml` - Créer rc2, rc3...
- `.github/workflows/promote-rc-to-release.yml` - Promouvoir vers release finale
- `.github/workflows/create-release.yml` - **Mis à jour** pour gérer RC et releases finales

### Scripts
- `scripts/rc-helper.sh` - CLI helper pour gérer les RC facilement

### Documentation
- `AUTOMATED_RELEASE_GUIDE.md` - **Mis à jour** avec section RC
- `.github/workflows/README_RC.md` - Documentation détaillée des workflows

## Migration pour releases existantes

### Si vous avez une release en cours

**Option 1 : Continuer l'ancien workflow (déconseillé)**
Vous pouvez toujours :
- Merger integration → main
- Créer un tag vX.Y.Z
- La release sera créée automatiquement

**Option 2 : Adopter le nouveau workflow (recommandé)**
1. Créer un RC sur integration : `./scripts/rc-helper.sh prepare`
2. Tester le RC en production
3. Si OK, créer PR integration → main
4. Merger → release finale automatique

### Pour les prochaines releases

**Utilisez TOUJOURS le workflow RC** :

```bash
# Sur integration
./scripts/rc-helper.sh prepare

# Tester en production

# Si corrections nécessaires
./scripts/rc-helper.sh increment

# Quand stable
./scripts/rc-helper.sh promote
gh pr create --base main --head integration
```

## Compatibilité avec l'ancien workflow

Le workflow `create-release.yml` a été mis à jour pour :
- ✅ Détecter automatiquement les tags RC (`v0.5.0-rc1`)
- ✅ Détecter automatiquement les tags finaux (`v0.5.0`)
- ✅ Créer des pre-releases pour les RC
- ✅ Créer des releases stables pour les tags finaux
- ✅ Fermer les issues SEULEMENT pour les releases finales (pas les RC)

**Aucune action manuelle requise** si vous utilisez déjà les workflows.

## Bonnes pratiques

### À FAIRE
- ✅ Créer un RC pour TOUTES les releases non-triviales
- ✅ Tester chaque RC en production avant promotion
- ✅ Documenter les corrections dans chaque RC increment
- ✅ Utiliser `./scripts/rc-helper.sh` pour simplifier les opérations
- ✅ Garder le CHANGELOG.md à jour pendant le développement

### À ÉVITER
- ❌ Merger directement integration → main sans RC
- ❌ Créer des tags RC manuellement
- ❌ Promouvoir un RC non testé
- ❌ Créer plusieurs RC simultanément pour différentes versions
- ❌ Oublier de fermer l'issue de suivi RC après promotion

## Rollback si problème

Si le nouveau workflow pose problème, vous pouvez :

1. **Revenir temporairement à l'ancien workflow** :
   - Merger integration → main normalement
   - Créer un tag vX.Y.Z (sans -rc)
   - Le workflow `create-release.yml` créera la release

2. **Désactiver les nouveaux workflows** :
   - Renommer les fichiers workflow en `.yml.disabled`
   - Utiliser seulement `create-release.yml`

## Support

En cas de problème :
1. Consulter [AUTOMATED_RELEASE_GUIDE.md](../AUTOMATED_RELEASE_GUIDE.md)
2. Consulter [.github/workflows/README_RC.md](.github/workflows/README_RC.md)
3. Exécuter `./scripts/rc-helper.sh help`
4. Vérifier l'onglet Actions sur GitHub pour les logs

## Questions fréquentes

**Q: Dois-je migrer mes releases en cours ?**
R: Non, finissez avec l'ancien workflow. Utilisez le nouveau pour les prochaines.

**Q: Puis-je créer un tag vX.Y.Z directement sans RC ?**
R: Oui, techniquement. Mais c'est déconseillé sauf pour des hotfixes critiques.

**Q: Que faire si j'ai oublié de créer un RC ?**
R: Créez un RC maintenant, même si vous pensez que c'est stable. Mieux vaut prévenir.

**Q: Les RC comptent-ils comme des releases ?**
R: Non, ce sont des pre-releases. Seules les releases finales sont marquées "latest".

**Q: Combien de RC puis-je créer ?**
R: Autant que nécessaire (rc1, rc2, rc3...). Pas de limite.

**Q: Faut-il supprimer les RC après la release finale ?**
R: Le workflow `promote-rc-to-release.yml` le fait automatiquement.

---

**Date de migration** : Janvier 2025
**Version minimale supportée** : v0.5.0+
**Compatibilité** : Rétrocompatible avec l'ancien workflow
