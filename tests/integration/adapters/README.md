# Integration Tests for Historical Data Adapters

Ce répertoire contient les tests d'intégration pour les adapters qui récupèrent des données historiques depuis Home Assistant.

## Prérequis

Les tests d'intégration nécessitent une instance Home Assistant fonctionnelle avec le composant `recorder` activé.

### Option 1 : Utiliser Home Assistant de test (Recommandé)

Les tests utilisent une instance Home Assistant in-memory avec une base SQLite temporaire :

```bash
poetry run pytest tests/integration/adapters/ -v
```

Cette approche :
- ✅ Crée une instance HA isolée pour chaque test
- ✅ Utilise une base de données en mémoire (rapide)
- ✅ Pas besoin de docker-compose
- ✅ Totalement reproductible

### Option 2 : Utiliser Home Assistant via Docker Compose

Si vous préférez tester avec votre configuration HA réelle :

```bash
# 1. Démarrer Home Assistant
docker-compose up -d

# 2. Attendre que HA soit prêt
sleep 10

# 3. Lancer les tests
TEST_HA_URL=http://localhost:8123 TEST_HA_TOKEN=<your_token> poetry run pytest tests/integration/adapters/ -v

# 4. Arrêter HA
docker-compose down
```

## Structure des Tests

```
tests/integration/adapters/
├── test_climate_data_adapter_integration.py  # Tests pour ClimateDataAdapter
├── test_sensor_data_adapter_integration.py   # Tests pour SensorDataAdapter
└── test_weather_data_adapter_integration.py  # Tests pour WeatherDataAdapter
```

## Ce que les tests vérifient

### ClimateDataAdapter
- ✅ Récupération de la température intérieure (current_temperature)
- ✅ Récupération de la température cible (target_temperature)
- ✅ Récupération de l'état de chauffage (hvac_action)
- ✅ Conversion correcte des objets State en HistoricalMeasurement
- ✅ Gestion des timestamps

### SensorDataAdapter
- ✅ Récupération de données de capteurs numériques
- ✅ Filtrage des états non numériques (unavailable, unknown)
- ✅ Support des différents types de capteurs (température, humidité)
- ✅ Catégorisation correcte via HistoricalDataKey

### WeatherDataAdapter
- ✅ Récupération de la température extérieure
- ✅ Récupération de l'humidité extérieure
- ✅ Récupération de la couverture nuageuse
- ✅ Préservation de l'état météo (sunny, cloudy, rainy) dans les attributes

## Résolution de problèmes

### "No module named 'homeassistant.components.recorder'"

Assurez-vous que homeassistant est installé :
```bash
poetry install
```

### Tests qui échouent avec timeout

Augmentez le timeout ou vérifiez que le recorder est bien initialisé dans conftest.py.

### "ImportError: cannot import name 'get_significant_states'"

Vérifiez que vous utilisez une version de Home Assistant >= 2023.x où cette API est disponible.

## Ajouter de nouveaux tests

Pour ajouter un nouveau test d'intégration :

1. Créer un fichier `test_*_integration.py`
2. Utiliser les fixtures de `conftest.py` (hass, test_*_entity_id)
3. Créer des états avec `hass.states.async_set()`
4. Appeler `await adapter.fetch_historical_data()`
5. Vérifier les résultats

Exemple :
```python
@pytest.mark.asyncio
async def test_my_integration(hass, test_start_time, test_end_time):
    adapter = MyAdapter(hass)
    hass.states.async_set("sensor.test", "42")
    await hass.async_block_till_done()
    
    result = await adapter.fetch_historical_data(...)
    assert result.data[...]
```
