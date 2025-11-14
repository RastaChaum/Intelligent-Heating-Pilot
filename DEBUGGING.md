# Guide de Débogage Home Assistant

## 🐛 Comprendre le fonctionnement d'une intégration

### Architecture de base

Une intégration Home Assistant se compose de plusieurs fichiers :

1. **`__init__.py`** : Point d'entrée, configure l'intégration et enregistre les services
2. **`config_flow.py`** : Gère le formulaire de configuration UI
3. **`sensor.py`** (ou autre plateforme) : Crée les entités (capteurs, switches, etc.)
4. **`const.py`** : Constantes partagées
5. **`manifest.json`** : Métadonnées de l'intégration

### Cycle de vie

```
1. Home Assistant démarre
2. Charge manifest.json → Importe __init__.py
3. Appelle async_setup() ou async_setup_entry()
4. Charge les plateformes (sensor, etc.)
5. async_setup_entry() de sensor.py crée les entités
6. Les entités s'enregistrent et deviennent disponibles
```

### Pourquoi vos entités étaient "inconnu"

- Les capteurs attendent un événement `intelligent_heating_pilot_calculation_complete`
- Cet événement est déclenché uniquement par le service `calculate_start_time`
- **Solution appliquée** : Valeurs initiales (0 pour duration, None pour timestamp)

## 🔧 Méthodes de Débogage

### 1. Logs dans le Code

Ajoutez des logs dans votre code :

```python
import logging
_LOGGER = logging.getLogger(__name__)

# Niveaux de log
_LOGGER.debug("Message de debug détaillé")
_LOGGER.info("Information générale")
_LOGGER.warning("Attention, problème potentiel")
_LOGGER.error("Erreur!")
```

**Dans VS Code** : Les logs ont été ajoutés aux capteurs, vous verrez maintenant :
- "Preheat duration sensor updated: X minutes"
- "Start time sensor updated: ..."

### 2. Visualiser les Logs en Temps Réel

#### Option A : Depuis VS Code (Terminal)

```bash
# Tâche VS Code : "View Home Assistant Logs"
# Ou manuellement :
ssh root@192.168.1.100 'tail -f /config/home-assistant.log | grep intelligent_heating_pilot'
```

#### Option B : Script Python

```bash
python scripts/view_logs.py
```

#### Option C : Interface Home Assistant

- Configuration → Système → Logs
- Filtrer par "intelligent_heating_pilot"

### 3. Activer le Mode Debug

Ajoutez dans `configuration.yaml` de Home Assistant :

```yaml
logger:
  default: info
  logs:
    custom_components.intelligent_heating_pilot: debug
```

Puis redémarrez Home Assistant.

### 4. Tester le Service

Dans Home Assistant :
1. Outils de développement → Services
2. Sélectionnez `intelligent_heating_pilot.calculate_start_time`
3. Données de test :

```yaml
current_temp: 18.5
target_temp: 21.0
outdoor_temp: 5.0
target_time: "2025-11-10 18:00:00"
thermal_slope: 2.0
```

4. Cliquez "Appeler le service"
5. Vérifiez que les capteurs se mettent à jour

### 5. Débogage Avancé avec debugpy (Optionnel)

Pour utiliser des breakpoints :

#### Étape 1 : Installer debugpy dans Home Assistant

```bash
ssh root@192.168.1.100
pip install debugpy
```

#### Étape 2 : Ajouter au début de votre `__init__.py`

```python
# import debugpy
# debugpy.listen(("0.0.0.0", 5678))
# debugpy.wait_for_client()  # Optionnel : attend la connexion
```

#### Étape 3 : Dans VS Code

1. Décommentez les lignes debugpy
2. Redéployez l'intégration
3. F5 → "Home Assistant: Attach to Container"
4. Ajoutez des breakpoints (clic dans la marge gauche)

**Note** : Cette méthode nécessite que le conteneur Home Assistant expose le port 5678.

## Modifier la Configuration

Pour changer les entités surveillées après l'installation :

1. **Configuration** → **Intégrations**
2. Trouvez **Smart Starter VTherm**
3. Cliquez sur les **trois points** (⋮)
4. Sélectionnez **"Configure"** ou **"Options"**
5. Modifiez les entités
6. **Enregistrez**

L'intégration se rechargera automatiquement et commencera à surveiller les nouvelles entités.

## 🔍 Checklist de Débogage

Quand une intégration ne fonctionne pas :

- [ ] **Logs de démarrage** : Cherchez "Setting up intelligent_heating_pilot"
- [ ] **Erreurs d'import** : Vérifiez les `import` manquants
- [ ] **Manifest.json valide** : Domain, version, requirements
- [ ] **Entités créées** : Outils dev → États → Cherchez vos entités
- [ ] **Service enregistré** : Outils dev → Services → Vérifiez le service
- [ ] **Événements déclenchés** : Outils dev → Événements → Écoutez les events
- [ ] **Entités surveillées** : Vérifiez que toutes les entités configurées existent et ont des valeurs valides

## 📝 Commandes Utiles

### Redéployer rapidement

```bash
./scripts/deploy.sh
```

### Voir tous les logs (pas seulement smart_starter)

```bash
ssh root@192.168.1.100 'tail -f /config/home-assistant.log'
```

### Recharger uniquement votre intégration (pas toujours fiable)

```bash
ssh root@192.168.1.100 'ha core reload'
```

### Vérifier que les fichiers sont bien copiés

```bash
ssh root@192.168.1.100 'ls -la /config/custom_components/intelligent_heating_pilot/'
```

### Supprimer le cache Python

```bash
ssh root@192.168.1.100 'rm -rf /config/custom_components/intelligent_heating_pilot/__pycache__'
```

## 🎯 Workflow Recommandé

1. **Modifier le code** dans VS Code
2. **Ajouter des logs** pour tracer l'exécution
3. **Déployer** : `./scripts/deploy.sh`
4. **Voir les logs** : Tâche "View Home Assistant Logs" ou terminal SSH
5. **Tester** : Interface Home Assistant ou service call
6. **Itérer** jusqu'à résolution

## 💡 Astuces

- **Logs structurés** : Utilisez des messages clairs avec les valeurs
  ```python
  _LOGGER.info("Calculation: temp_delta=%.1f, duration=%.1f min", delta, duration)
  ```

- **try/except pour debugging** :
  ```python
  try:
      # votre code
  except Exception as e:
      _LOGGER.error("Error in my_function: %s", e, exc_info=True)
  ```

- **Vérifier le state des entités** :
  ```python
  state = hass.states.get("sensor.my_sensor")
  _LOGGER.info("Sensor state: %s", state)
  ```

- **Hot reload partiel** : Certaines modifications (ex: calculs) ne nécessitent pas un redémarrage complet, juste recharger l'intégration via UI.

## 🚨 Problèmes Courants

### "Entités inconnues"
- Vérifiez que le service a été appelé au moins une fois
- Initialisez avec des valeurs par défaut (fait ✅)

### "Integration not found"
- Vérifiez le domain dans manifest.json = nom du dossier
- Redémarrez complètement Home Assistant

### "Import error"
- Vérifiez requirements dans manifest.json
- Installez les dépendances dans le conteneur

### "Service not updating sensors"
- Vérifiez que l'événement est bien déclenché
- Vérifiez que les capteurs écoutent l'événement

