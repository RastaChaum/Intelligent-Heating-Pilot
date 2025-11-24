"""
Minimal ML Prediction API for IHP - PROTOTYPE
Validates XGBoost availability and HTTP communication.
"""
import logging
import pickle
from datetime import datetime
from flask import Flask, request, jsonify
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test XGBoost import
try:
    import xgboost as xgb
    logger.info(f"✓ XGBoost {xgb.__version__} loaded successfully")
    XGBOOST_AVAILABLE = True
except ImportError as e:
    logger.error(f"✗ XGBoost not available: {e}")
    XGBOOST_AVAILABLE = False

app = Flask(__name__)

# Global model storage (in-memory for prototype)
current_model = None
model_metadata = {
    "trained": False,
    "trained_at": None,
    "n_samples": 0,
    "rmse": None
}


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "xgboost_available": XGBOOST_AVAILABLE,
        "xgboost_version": xgb.__version__ if XGBOOST_AVAILABLE else None,
        "model_trained": model_metadata["trained"],
        "timestamp": datetime.now().isoformat()
    })


@app.route('/train', methods=['POST'])
def train():
    """Train a dummy XGBoost model.
    
    Expected JSON:
    {
        "X_train": [[feat1, feat2, ...], ...],
        "y_train": [duration1, duration2, ...]
    }
    """
    global current_model, model_metadata
    
    if not XGBOOST_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "XGBoost not available"
        }), 500
    
    try:
        data = request.get_json()
        X_train = np.array(data['X_train'], dtype=np.float32)
        y_train = np.array(data['y_train'], dtype=np.float32)
        
        logger.info(f"Training with {len(X_train)} samples, {X_train.shape[1]} features")
        
        # Train XGBoost model (minimal params for prototype)
        model = xgb.XGBRegressor(
            max_depth=3,
            learning_rate=0.1,
            n_estimators=50,
            random_state=42
        )
        model.fit(X_train, y_train)
        
        # Calculate RMSE
        y_pred = model.predict(X_train)
        rmse = float(np.sqrt(np.mean((y_train - y_pred) ** 2)))
        
        # Store model
        current_model = model
        model_metadata = {
            "trained": True,
            "trained_at": datetime.now().isoformat(),
            "n_samples": len(X_train),
            "rmse": rmse
        }
        
        logger.info(f"✓ Model trained successfully. RMSE: {rmse:.2f}")
        
        return jsonify({
            "success": True,
            "metrics": {
                "rmse": rmse,
                "n_samples": len(X_train),
                "n_features": int(X_train.shape[1])
            }
        })
        
    except Exception as e:
        logger.error(f"Training error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route('/predict', methods=['POST'])
def predict():
    """Make prediction with trained model.
    
    Expected JSON:
    {
        "features": [feat1, feat2, ...]
    }
    """
    global current_model
    
    if not model_metadata["trained"]:
        return jsonify({
            "success": False,
            "error": "Model not trained yet"
        }), 400
    
    try:
        data = request.get_json()
        features = np.array([data['features']], dtype=np.float32)
        
        # Make prediction
        prediction = float(current_model.predict(features)[0])
        
        logger.debug(f"Prediction: {prediction:.2f}")
        
        return jsonify({
            "success": True,
            "prediction": prediction
        })
        
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


@app.route('/model/info', methods=['GET'])
def model_info():
    """Get current model information."""
    return jsonify({
        "success": True,
        "metadata": model_metadata
    })


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("IHP ML Predictor API - PROTOTYPE")
    logger.info("=" * 60)
    logger.info(f"XGBoost available: {XGBOOST_AVAILABLE}")
    if XGBOOST_AVAILABLE:
        logger.info(f"XGBoost version: {xgb.__version__}")
    logger.info("Starting Flask server on 0.0.0.0:5000")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)
