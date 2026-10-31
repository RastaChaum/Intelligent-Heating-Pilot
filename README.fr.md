# Intelligent Heating Pilot (IHP)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/RastaChaum/Intelligent-Heating-Pilot?label=version&color=blue)](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases/latest)
![Status](https://img.shields.io/badge/status-beta-yellow)

🇬🇧 [English version](README.md)

> **Le cerveau adaptatif de Versatile Thermostat**

Une intégration Home Assistant qui apprend le comportement de votre chauffage et le démarre automatiquement au bon moment, sans aucun réglage manuel.

> ℹ️ La documentation détaillée vers laquelle pointe cette page est en anglais.

---

## Ce que fait IHP

```text
📅 Prochain chauffage : 18:00 (cible 21°C)
🧠 Pente apprise : 2,3°C/heure
⏰ Démarrage : 16:42 (calculé automatiquement)
✅ La pièce atteint 21°C pile à 18:00
```

IHP surveille votre VTherm, apprend à quelle vitesse votre pièce chauffe et déclenche votre planificateur au moment idéal : vous retrouvez une maison chaude, à chaque fois.

---

## ⚡ Démarrage rapide

### 1. Installer via HACS

```text
HACS → Intégrations → ⋮ → Dépôts personnalisés
→ Ajouter : https://github.com/RastaChaum/Intelligent-Heating-Pilot
→ Rechercher « Intelligent Heating Pilot » → Télécharger → Redémarrer HA
```

**[Guide d'installation complet →](docs/users/INSTALLATION.md)**

### 2. Configurer

```text
Paramètres → Appareils et services → + Ajouter une intégration
→ Rechercher « Intelligent Heating Pilot »
→ Sélectionner le VTherm et le planificateur → Valider
```

**[Guide de configuration complet →](docs/users/CONFIGURATION.md)**

### 3. Le laisser apprendre

- 5 premiers cycles : prudent (démarre en avance)
- Au-delà de 20 cycles : prédictions très précises
- Aucune intervention manuelle nécessaire

**[Comment fonctionne IHP →](docs/users/HOW_IT_WORKS.md)**

---

## 🎯 Fonctionnalités

### Actuelles

- ✅ **Préchauffage intelligent** - Calcule automatiquement l'heure de démarrage optimale à partir des performances de chauffe apprises
- ✅ **Apprentissage du temps mort** - Tient compte du délai avant que la température ne réagisse, pour des prédictions plus précises
- ✅ **Interrupteur d'activation** - Active ou désactive le préchauffage en conservant les données apprises
- ✅ **Seuil d'annulation configurable** - Un préchauffage en cours n'est annulé que si le démarrage anticipé recule au-delà d'un délai configurable
- ✅ **Détection des cycles** - Apprend à partir des vrais cycles de chauffe, pas des pentes du thermostat
- ✅ **Paramètres de détection configurables** - Ajustez finement la détection des cycles à votre installation
- ✅ **Apprentissage selon l'heure** - Des vitesses de chauffe différentes selon le moment de la journée
- ✅ **Planificateur optionnel** - Fonctionne avec ou sans HACS Scheduler grâce à des appels de service dynamiques
- ✅ **Plannings natifs** - Les helpers `schedule.*` disposent d'un capteur d'heure de démarrage anticipé pour construire votre propre automatisation
- ✅ **Source extérieure** - Capteur extérieur ou entité `weather.*`, enregistrée avec chaque cycle de chauffe
- ✅ **Cache incrémental** - Réduit la charge de la base de données de HA pour l'apprentissage à long terme
- ✅ **Mode sans rétention** - Option pour désactiver le stockage de l'historique sur les installations minimales
- ✅ **Compatible VTherm v8+** - Fonctionne avec les dernières versions de Versatile Thermostat
- ✅ **Démarrage optimisé** - Le chargement différé et le filtrage intelligent évitent les timeouts du watchdog de HA
- ✅ **Prêt pour les vacances** - S'arrête automatiquement quand le planificateur est désactivé

### Vision

- 🔮 Abaissement anticipé (baisser la température avant la fin d'un créneau de confort, en profitant de l'inertie de la pièce)
- 🔮 Planification selon l'occupation
- 🔮 Coordination multizone
- 🔮 Optimisation du coût énergétique

---

## 📚 Documentation

| Pour | Commencer ici |
| --- | --- |
| **Nouveaux utilisateurs** | [Guide utilisateur](docs/users/USER_GUIDE.md) - Vue d'ensemble et navigation |
| **Installation** | [Guide d'installation](docs/users/INSTALLATION.md) - HACS ou installation manuelle |
| **Configuration** | [Guide de configuration](docs/users/CONFIGURATION.md) - Choix des entités et options |
| **Comprendre** | [Fonctionnement d'IHP](docs/users/HOW_IT_WORKS.md) - Détection des cycles et prédiction |
| **Problèmes** | [Dépannage](docs/users/TROUBLESHOOTING.md) - Problèmes courants et solutions |
| **Contributeurs** | [Guide de contribution](docs/contributors/CONTRIBUTING.md) - Workflow de développement et standards |
| **Hub de documentation** | [docs/README.md](docs/README.md) - Toute la documentation utilisateurs, contributeurs et mainteneurs |

**Liens rapides :** [Changelog](CHANGELOG.md) · [Signaler un bug](https://github.com/RastaChaum/Intelligent-Heating-Pilot/issues/new?template=bug_report.md) · [Discussions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/discussions) · [Versions](https://github.com/RastaChaum/Intelligent-Heating-Pilot/releases)

---

## 💡 Concepts clés

**Pente de chauffe apprise** - La vitesse à laquelle votre pièce chauffe (°C/heure)

- Calculée à partir des cycles de chauffe détectés (température de départ → température d'arrivée)
- Affinée au fil du temps par une moyenne tronquée
- Utilisée pour prédire l'heure exacte de démarrage du prochain créneau

**Exemple :** pour gagner 3°C à 2°C/heure → démarrer 90 minutes en avance ✅

**Mode vacances** - Rien à faire !

- IHP s'arrête automatiquement quand le planificateur est désactivé
- Il reprend quand vous réactivez le planificateur
- Les données apprises sont conservées pendant les vacances

---

Les contributions sont les bienvenues ! Signalez des bugs, proposez des fonctionnalités ou soumettez des améliorations de code.

**[Lire le guide de contribution →](docs/contributors/CONTRIBUTING.md)**

Pour l'architecture technique : [Vue d'ensemble de l'architecture](docs/architecture/OVERVIEW.md)

Pour toute la documentation détaillée : [Hub de documentation](docs/README.md)

---

## 📝 Licence

Licence MIT - voir le fichier [LICENSE](LICENSE) pour les détails.

## 👏 Remerciements

- [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) par @jmcollin78
- [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) par @nielsfaber
- La communauté Home Assistant

---

**⭐ Si IHP vous est utile, mettez une étoile au projet !**

[![Star History Chart](https://api.star-history.com/svg?repos=RastaChaum/Intelligent-Heating-Pilot&type=Date)](https://star-history.com/#RastaChaum/Intelligent-Heating-Pilot&Date)
