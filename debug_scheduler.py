#!/usr/bin/env python3
"""Script de diagnostic pour voir les attributs du scheduler."""
import json
import sys

# Simuler les attributs d'un scheduler
# À exécuter dans HA avec: python3 debug_scheduler.py

# Pour récupérer les vraies données, dans les logs HA, ajoutez temporairement:
# _LOGGER.warning("SCHEDULER ATTRS: %s", json.dumps(state.attributes, default=str))

# Exemple de format attendu pour scheduler-component
example_attrs = {
    "next_trigger": "2025-11-19T14:30:00+01:00",
    "next_slot": 0,
    "actions": [
        {
            "service": "climate.set_temperature",
            "data": {
                "temperature": 21.5,
                "entity_id": "climate.thermostat_de_test_mezanine"
            }
        }
    ]
}

print("Format attendu des attributs scheduler:")
print(json.dumps(example_attrs, indent=2))
print("\n" + "="*60 + "\n")

# Format alternatif avec next_entries
alternative_attrs = {
    "next_entries": [
        {
            "time": "2025-11-19T14:30:00+01:00",
            "actions": [
                {
                    "service": "climate.set_temperature",
                    "service_data": {
                        "temperature": 21.5
                    }
                }
            ]
        }
    ]
}

print("Format alternatif (next_entries):")
print(json.dumps(alternative_attrs, indent=2))
