# Intégration avec HACS Scheduler Component

## Défi Technique Principal

L'intégration SmartStarterVTherm doit extraire les informations suivantes du HACS Scheduler Component :

1. **`next_schedule_time`** : La date/heure du prochain déclenchement du scheduler
2. **`next_target_temperature`** : La température cible associée à ce déclenchement

## Structure des Entités Scheduler

Le HACS Scheduler Component crée des entités de type `switch` pour chaque planning.

### Attributs à Explorer

Voici les attributs potentiels à vérifier sur les entités scheduler :

```python
scheduler_state = hass.states.get("switch.scheduler_chauffage_matin")

# Attributs communs du Scheduler Component :
attributes = {
    "next_entries": [...],      # Liste des prochains déclenchements
    "next_trigger": "...",       # Prochain trigger (timestamp ou datetime)
    "next_action": {...},        # Action à exécuter
    "actions": [...],            # Liste des actions configurées
    "entries": [...],            # Entrées du planning
    "timeslots": [...],          # Créneaux horaires
}
```

### Méthode d'Extraction Recommandée (implémentée)

#### 1. Via les Attributs de l'Entité Switch

```python
def get_next_scheduler_event(self) -> tuple[datetime | None, float | None, str | None]:
    """Get next scheduler event details."""
    scheduler_entities = self.get_scheduler_entities()

    chosen_time = None
    chosen_temp = None
    chosen_scheduler = None

    for entity_id in scheduler_entities:
        state = self.hass.states.get(entity_id)
        if not state:
            continue

        attrs = state.attributes
        next_trigger = attrs.get("next_trigger")
        next_slot = attrs.get("next_slot")
        actions = attrs.get("actions")

        next_time = None
        if next_trigger:
            next_time = dt_util.parse_datetime(str(next_trigger)) or self._safe_fromiso(str(next_trigger))

        target_temp = None
        if isinstance(actions, list) and isinstance(next_slot, int) and 0 <= next_slot < len(actions):
            action = actions[next_slot]
            target_temp = self._extract_target_temp_from_action(action)
        else:
            next_entries = attrs.get("next_entries")
            if isinstance(next_entries, list) and next_entries:
                entry = next_entries[0]
                entry_actions = entry.get("actions", [])
                if isinstance(entry_actions, list) and entry_actions:
                    target_temp = self._extract_target_temp_from_action(entry_actions[0])
                entry_time = entry.get("time") or entry.get("start") or entry.get("trigger_time")
                if entry_time and not next_time:
                    next_time = dt_util.parse_datetime(str(entry_time)) or self._safe_fromiso(str(entry_time))

        if next_time and target_temp is not None:
            if not chosen_time or next_time < chosen_time:
                chosen_time = next_time
                chosen_temp = target_temp
                chosen_scheduler = entity_id

    return chosen_time, chosen_temp, chosen_scheduler

def _safe_fromiso(self, value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
```

#### 2. Via les Services du Scheduler

Le Scheduler Component peut exposer des services pour obtenir le prochain événement :

```python
# Appeler un service du scheduler pour obtenir les infos
result = await self.hass.services.async_call(
    "scheduler",
    "get_next_event",
    {"entity_id": scheduler_entity_id},
    blocking=True,
    return_response=True,
)
```

## Étapes de Débogage

### 1. Inspecter les Attributs dans Home Assistant

Dans Developer Tools > States, sélectionnez une entité scheduler et notez tous les attributs disponibles.

### 2. Activer le Logging Détaillé

Ajoutez dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.intelligent_heating_pilot: debug
    homeassistant.components.scheduler: debug
```

### 3. Logger les Attributs dans le Code

Dans `__init__.py`, fonction `get_next_scheduler_event()` :

```python
for entity_id in scheduler_entities:
    state = self.hass.states.get(entity_id)
    if not state:
        continue
    
    _LOGGER.debug("=" * 80)
    _LOGGER.debug("Scheduler entity: %s", entity_id)
    _LOGGER.debug("State: %s", state.state)
    _LOGGER.debug("Attributes: %s", state.attributes)
    _LOGGER.debug("=" * 80)
```

## Structure Cible Attendue

Une fois les attributs identifiés, la fonction devrait retourner :

```python
{
    "next_schedule_time": datetime(2025, 11, 12, 7, 0, 0),  # Prochain déclenchement
    "next_target_temp": 21.0,                               # Température cible
    "scheduler_entity": "switch.scheduler_chauffage_matin", # Entité source
}
```

## Actions sur le Scheduler

### Déclencher Manuellement le Scheduler

```python
await self.hass.services.async_call(
    "scheduler",
    "run_action",
    {"entity_id": scheduler_entity_id},
    blocking=True,
)
```

Cela déclenche immédiatement l'action programmée (changement de consigne du VTherm).

## Exemple Complet

```python
async def get_next_scheduler_event(self) -> tuple[datetime | None, float | None, str | None]:
    """
    Get next scheduler event details.
    
    Returns:
        Tuple of (next_schedule_time, next_target_temp, scheduler_entity_id)
    """
    scheduler_entities = self.get_scheduler_entities()
    
    # Pour déboguer : afficher tous les attributs
    for entity_id in scheduler_entities:
        state = self.hass.states.get(entity_id)
        if not state:
            _LOGGER.warning("Scheduler entity not found: %s", entity_id)
            continue
        
        _LOGGER.debug("Analyzing scheduler: %s", entity_id)
        _LOGGER.debug("  State: %s", state.state)
        _LOGGER.debug("  Attributes: %s", state.attributes)
        
        # TODO: Adapter selon la structure réelle des attributs
        # Ci-dessous : exemple à adapter
        
        next_entries = state.attributes.get("next_entries")
        if next_entries and len(next_entries) > 0:
            entry = next_entries[0]
            
            # Extraire le temps
            time_str = entry.get("time") or entry.get("start") or entry.get("trigger_time")
            if time_str:
                next_time = self._parse_datetime(time_str)
                
                # Extraire la température
                actions = entry.get("actions", [])
                for action in actions:
                    if "climate" in action.get("service", ""):
                        service_data = action.get("service_data", {})
                        temp = service_data.get("temperature")
                        if temp and next_time:
                            _LOGGER.info(
                                "Found next schedule: %s at %s for temp %.1f°C",
                                entity_id, next_time.isoformat(), float(temp)
                            )
                            return next_time, float(temp), entity_id
    
    _LOGGER.warning("No next scheduler event found")
    return None, None, None

def _parse_datetime(self, time_value: Any) -> datetime | None:
    """Parse various datetime formats."""
    if isinstance(time_value, datetime):
        return time_value
    
    if isinstance(time_value, str):
        try:
            return datetime.fromisoformat(time_value)
        except (ValueError, TypeError):
            pass
        
        try:
            from dateutil import parser
            return parser.parse(time_value)
        except (ValueError, TypeError, ImportError):
            pass
    
    return None
```

## Points Importants

1. **Variabilité des Attributs** : La structure exacte dépend de la version du HACS Scheduler Component
2. **Debugging d'abord** : Logger tous les attributs avant d'implémenter l'extraction
3. **Robustesse** : Gérer les cas où les attributs ne sont pas présents
4. **Documentation** : Consulter la documentation du Scheduler Component ou son code source

## Ressources

- [HACS Scheduler Component sur GitHub](https://github.com/nielsfaber/scheduler-component)
- Documentation officielle du composant
- Forum Home Assistant : recherches sur "scheduler component attributes"

## TODO

- [ ] Identifier la structure exacte des attributs du Scheduler Component
- [ ] Implémenter la fonction `get_next_scheduler_event()` avec la vraie structure
- [ ] Tester avec plusieurs schedulers actifs
- [ ] Gérer les cas où aucun prochain événement n'est défini
- [ ] Valider que `scheduler.run_action` fonctionne comme attendu
