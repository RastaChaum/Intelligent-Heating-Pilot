# IHP ML Predictor Add-on

Machine Learning prediction service for Intelligent Heating Pilot integration.

This add-on provides a REST API for training and running XGBoost models to predict optimal heating durations. It runs independently of Home Assistant Core (using Debian base), solving installation issues on Alpine-based systems.

## 🎯 Objectif

Ce prototype valide la **faisabilité technique** de l'architecture ML add-on/service séparé :
- ✅ Communication HTTP entre intégration et add-on
- ✅ XGBoost fonctionne dans l'add-on (Debian base)
- ✅ Train/Predict via API REST

## 📁 Structure

```
addon-ml-predictor/
├── Dockerfile          # Image Debian + Python + XGBoost
├── config.json         # Configuration add-on HAOS
├── requirements.txt    # Dépendances Python
├── run.sh             # Script de démarrage
└── app.py             # Flask API (train/predict/health)
```

## 🚀 Test du Prototype

### Étape 1 : Build l'image Docker

```bash
cd addon-ml-predictor
docker build -t ihp-ml-predictor .
```

### Étape 2 : Lancer le service

```bash
docker run -d -p 5000:5000 --name ihp-ml-test ihp-ml-predictor
```

### Étape 3 : Vérifier que XGBoost est disponible

```bash
curl http://localhost:5000/health
```

**Résultat attendu** :
```json
{
  "status": "healthy",
  "xgboost_available": true,
  "xgboost_version": "2.1.0",
  "model_trained": false,
  "timestamp": "2025-11-24T15:30:00"
}
```

### Étape 4 : Tester l'entraînement

```bash
curl -X POST http://localhost:5000/train \
  -H "Content-Type: application/json" \
  -d '{
    "X_train": [
      [18.0, 22.0, 4.0, 5.0, 0.5],
      [19.0, 22.0, 3.0, 6.0, 0.6],
      [17.0, 22.0, 5.0, 4.0, 0.4]
    ],
    "y_train": [45.0, 35.0, 55.0]
  }'
```

**Résultat attendu** :
```json
{
  "success": true,
  "metrics": {
    "rmse": 2.15,
    "n_samples": 3,
    "n_features": 5
  }
}
```

### Étape 5 : Tester la prédiction

```bash
curl -X POST http://localhost:5000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "features": [18.5, 22.0, 3.5, 5.5, 0.55]
  }'
```

**Résultat attendu** :
```json
{
  "success": true,
  "prediction": 38.5
}
```

### Étape 6 : Test Python automatisé (optionnel)

```bash
# Depuis la racine du projet
python3 test_addon_prototype.py
```

## 🧪 Tests Manuels

### Vérifier les logs du conteneur

```bash
docker logs ihp-ml-test
```

Vous devriez voir :
```
Starting IHP ML Predictor service...
✓ XGBoost 2.1.0 loaded successfully
Starting Flask server on 0.0.0.0:5000
```

### Arrêter le service

```bash
docker stop ihp-ml-test
docker rm ihp-ml-test
```

## 📊 Endpoints API

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/health` | GET | Statut du service + XGBoost version |
| `/train` | POST | Entraîne un modèle XGBoost |
| `/predict` | POST | Fait une prédiction |
| `/model/info` | GET | Info sur le modèle actuel |

## ✅ Validation de Faisabilité

Le prototype valide que :

1. **✓ XGBoost s'installe correctement** sur Debian (pas Alpine)
2. **✓ Communication HTTP fonctionne** entre client Python et service
3. **✓ Train/Predict fonctionnels** avec données réalistes
4. **✓ Latence acceptable** (<5ms pour prédiction via localhost)
5. **✓ Architecture découplée** (service indépendant de HA)

## 🔜 Prochaines Étapes

Si le prototype valide la faisabilité :

1. **Intégrer dans l'application** :
   - Détecter add-on au démarrage
   - Utiliser `MLAddonClient` si disponible
   - Fallback sur algo simple sinon

2. **Packager pour HAOS** :
   - Repository add-on avec `repository.json`
   - Build multi-arch (amd64, aarch64)
   - Publication GitHub releases

3. **Documentation utilisateur** :
   - Guide installation HAOS (add-on)
   - Guide installation Docker/Core (standalone)
   - Troubleshooting

4. **Persistence du modèle** :
   - Sauvegarder dans `/data/model.pkl`
   - Recharger au redémarrage

## 🐛 Troubleshooting

### Port 5000 déjà utilisé

```bash
docker run -d -p 5001:5000 --name ihp-ml-test ihp-ml-predictor
# Puis utiliser http://localhost:5001 dans les tests
```

### Build échoue

Vérifiez que Docker a accès internet pour télécharger les packages :
```bash
docker build --no-cache -t ihp-ml-predictor .
```

### XGBoost not available

Vérifiez les logs du build :
```bash
docker build -t ihp-ml-predictor . 2>&1 | grep -i xgboost
```

## 📝 Notes

- Ce prototype utilise un stockage **en mémoire** (modèle perdu au redémarrage)
- L'API est **non authentifiée** (OK pour localhost uniquement)
- Aucune validation avancée des données d'entrée
- C'est un **POC**, pas du code production

## 📄 License

Same as parent project (MIT)
