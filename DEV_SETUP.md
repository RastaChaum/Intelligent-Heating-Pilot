# Guide de développement - Intelligent Heating Pilot

## Configuration Poetry + Python 3.13

### Prérequis installés
- ✅ Python 3.13.2 (via pyenv)
- ✅ Poetry 2.2.1 (`~/.local/bin/poetry`)
- ✅ Home Assistant 2025.11.2 + dépendances dev

### Environnement virtuel
Poetry a créé un environnement virtuel dans `.venv/` avec Python 3.13.2.

## Commandes utiles

### Activer l'environnement Poetry
```bash
# Option 1 : Préfixer toutes les commandes avec poetry run
poetry run python script.py
poetry run pytest

# Option 2 : Activer le shell
poetry shell
```

### Gestion des dépendances
```bash
# Ajouter une dépendance
poetry add <package>

# Ajouter une dépendance de développement
poetry add --group dev <package>

# Mettre à jour toutes les dépendances
poetry update

# Voir les dépendances installées
poetry show --tree
```

### Linting et formatage
```bash
# Vérifier le style de code
poetry run ruff check .

# Formater automatiquement
poetry run ruff format .

# Type checking avec mypy
poetry run mypy custom_components/intelligent_heating_pilot
```

### Tests
```bash
# Lancer tous les tests
poetry run pytest

# Tests avec couverture
poetry run pytest --cov=custom_components/intelligent_heating_pilot

# Tests unitaires uniquement
poetry run pytest tests/unit/

# Tests d'un fichier spécifique
poetry run pytest tests/unit/domain/test_prediction_service.py -v
```

### Vérification des imports Home Assistant
```bash
# Vérifier que Home Assistant s'importe correctement
poetry run python -c "from homeassistant.core import HomeAssistant; print('HA OK ✓')"

# Tester l'intégration
poetry run python -c "import sys; sys.path.insert(0, 'custom_components'); from intelligent_heating_pilot import DOMAIN; print(f'✓ {DOMAIN}')"
```

## Structure du projet

```
SmartStarterVTherm/
├── custom_components/
│   └── intelligent_heating_pilot/
│       ├── __init__.py          # Coordinator (orchestration HA)
│       ├── domain/              # Logique métier pure (sans HA)
│       │   ├── entities/        # Agrégats (HeatingPilot)
│       │   ├── interfaces/      # Contrats (ABC)
│       │   ├── services/        # Services métier
│       │   └── value_objects/   # Objets immuables
│       ├── infrastructure/      # Adaptateurs HA
│       │   └── adapters/        # Implémentations des interfaces
│       ├── sensor.py            # Capteurs HA
│       └── config_flow.py       # Configuration UI
├── tests/
│   ├── unit/
│   │   ├── domain/              # Tests du domaine (pas de HA)
│   │   └── infrastructure/      # Tests des adaptateurs (avec mocks HA)
│   └── integration/             # Tests end-to-end
├── pyproject.toml               # Config Poetry + outils
└── .venv/                       # Environnement virtuel (ignoré git)
```

## Principes DDD respectés

### ✅ Séparation des couches
- **Domain** : Logique métier pure, aucun import `homeassistant.*`
- **Infrastructure** : Adaptateurs fins, traduction HA ↔ Domain
- **Application** : Orchestration (coordinator)

### ✅ Interfaces (ABC)
- `IModelStorage` : Persistance des slopes
- `ISchedulerReader` : Lecture scheduler
- `ISchedulerCommander` : Contrôle scheduler

### ✅ Value Objects
- `EnvironmentState` : Conditions environnementales
- `HeatingDecision` : Décision de chauffage
- `PredictionResult` : Résultat prédiction
- `ScheduleTimeslot` : Créneau horaire

## Résolution des erreurs de compilation

Les erreurs "Impossible de résoudre l'importation homeassistant.*" dans l'éditeur sont dues à Pylance qui ne détecte pas automatiquement l'environnement Poetry.

### Solution 1 : Sélectionner l'interpréteur Poetry dans VS Code
1. `Ctrl+Shift+P` → "Python: Select Interpreter"
2. Choisir `.venv/bin/python` (Python 3.13.2)
3. Redémarrer VS Code si nécessaire

### Solution 2 : Configurer `.vscode/settings.json`
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.analysis.extraPaths": [
    "${workspaceFolder}/.venv/lib/python3.13/site-packages"
  ]
}
```

### Vérification
```bash
# Confirmer que Poetry utilise bien Python 3.13.2
poetry env info

# Sortie attendue :
# Python:         3.13.2
# Implementation: CPython
# Path:           /home/.../SmartStarterVTherm/.venv
```

## Déploiement vers Home Assistant

Poetry est **uniquement pour le développement**. L'intégration se déploie directement :

```bash
# Copier vers HA (exemple)
scp -r custom_components/intelligent_heating_pilot root@homeassistant:/config/custom_components/

# Redémarrer HA
ssh root@homeassistant 'ha core restart'
```

Home Assistant charge l'intégration depuis `custom_components/` sans utiliser Poetry.

## Workflow recommandé

```bash
# 1. Développer une fonctionnalité
poetry run pytest tests/unit/domain/  # Tests domaine d'abord

# 2. Vérifier le code
poetry run ruff check .
poetry run mypy custom_components/intelligent_heating_pilot

# 3. Corriger indentation si nécessaire
poetry run ruff format .

# 4. Tester l'intégration
poetry run pytest tests/

# 5. Déployer vers HA
./scripts/deploy.sh  # ou commande manuelle scp
```

## Notes importantes

- **Ne jamais** commiter `.venv/` (déjà dans `.gitignore`)
- **Ne jamais** ajouter `homeassistant` dans `manifest.json` de l'intégration
- Les tests du domaine ne doivent **jamais** importer `homeassistant.*`
- Les adaptateurs peuvent importer HA mais sans logique métier

## Ressources

- [Poetry Documentation](https://python-poetry.org/docs/)
- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Project DDD Architecture](.github/copilot-instructions.md)
- [Migration Guide](MIGRATION_GUIDE.md)
