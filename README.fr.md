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

## ✅ Prérequis

- **Home Assistant** 2024.11 ou plus récent
- **[Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)** : IHP ne fonctionne qu'avec des entités VTherm ; utilisez un appareil IHP par thermostat
- **Un planificateur pris en charge**, pour qu'IHP anticipe vos créneaux :

| Planificateur | Démarrage anticipé | IHP lance le chauffage |
| --- | --- | --- |
| [HACS Scheduler](https://github.com/nielsfaber/scheduler-component) (`switch.schedule_*`) | ✅ | ✅ |
| Helper natif `schedule.*` | ✅ (cible = preset confort du VTherm) | ❌ construisez votre propre automatisation |
| Autres planificateurs (automatisations, calendriers, autres intégrations) | ❌ | ❌ utilisez le service `calculate_anticipated_start_time` |

Avec HACS Scheduler, l'action de chaque créneau doit être `climate.set_temperature` ou `climate.set_preset_mode`, sur le VTherm de l'appareil IHP. **[Planificateurs pris en charge en détail →](docs/users/CONFIGURATION.md#supported-schedulers)**

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
→ Sélectionner le VTherm et le HACS Scheduler → Valider
```

**[Guide de configuration complet →](docs/users/CONFIGURATION.md)**

### 3. Le laisser apprendre

- Dès la configuration, IHP apprend à partir de vos cycles de chauffe passés, dans l'historique du recorder de Home Assistant
- Chaque nouveau cycle affine la pente et le temps mort appris, heure par heure
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
- ✅ **Préchauffage via HACS Scheduler** - Déclenche le prochain créneau en avance, en respectant les conditions du planificateur ; plusieurs planificateurs par appareil
- ✅ **Plannings natifs** - Les helpers `schedule.*` disposent d'un capteur d'heure de démarrage anticipé pour construire votre propre automatisation (IHP ne lance pas le chauffage pour eux)
- ✅ **Service de calcul** - `calculate_anticipated_start_time` pour vos propres automatisations, avec ou sans planificateur
- ✅ **Source extérieure** - Capteur extérieur ou entité `weather.*`, enregistrée avec chaque cycle de chauffe
- ✅ **Cache incrémental** - Réduit la charge de la base de données de HA pour l'apprentissage à long terme
- ✅ **Compatible VTherm v8+** - Fonctionne avec les dernières versions de Versatile Thermostat
- ✅ **Démarrage optimisé** - Le chargement différé et le filtrage intelligent évitent les timeouts du watchdog de HA
- ✅ **Prêt pour les vacances** - S'arrête automatiquement quand le HACS Scheduler est désactivé ou que ses conditions le bloquent

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

- Calculée à partir des cycles de chauffe détectés, après le temps mort
- Moyennée sur les cycles retenus, globalement et pour chaque heure de la journée
- Utilisée pour prédire l'heure exacte de démarrage du prochain créneau

**Exemple :** pour gagner 3°C à 2°C/heure → 90 minutes, plus le temps mort et une marge de 5 minutes ✅

**Mode vacances** - Rien à faire !

- IHP s'arrête automatiquement quand vous désactivez le HACS Scheduler, ou quand ses conditions (par ex. `input_boolean.vacation`) le bloquent
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
