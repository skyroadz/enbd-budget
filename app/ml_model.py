"""
ML model wrapper: lazy-load the trained transaction categoriser and expose a predict function.
The model is a sklearn Pipeline (TF-IDF char n-grams + Logistic Regression).
"""
import logging
from typing import Optional, Tuple

from .config import ML_MODEL_PATH, ML_CONFIDENCE_THRESHOLD

log = logging.getLogger(__name__)

_model = None          # loaded on first use
_model_available: Optional[bool] = None  # None = not yet checked
_model_mtime: float = 0.0


def _load_model():
    global _model, _model_available, _model_mtime
    if _model_available is not None:
        return  # already attempted

    try:
        import joblib
        _model = joblib.load(ML_MODEL_PATH)
        _model_available = True
        _model_mtime = ML_MODEL_PATH.stat().st_mtime
        log.info("ML model loaded from %s  categories=%s", ML_MODEL_PATH, list(_model.classes_))
    except FileNotFoundError:
        _model_available = False
        log.warning("ML model not found at %s — ML categorisation disabled", ML_MODEL_PATH)
    except Exception as exc:
        _model_available = False
        log.warning("Failed to load ML model: %s — ML categorisation disabled", exc)


def reload():
    """Force-reload the model from disk (called after retraining)."""
    global _model, _model_available, _model_mtime
    _model_available = None  # reset so _load_model runs again
    _load_model()
    log.info("ML model reloaded")


def predict(merchant: str) -> Tuple[Optional[str], float]:
    """
    Return (category, confidence) for a merchant name string.
    Returns (None, 0.0) when the model is unavailable or confidence is below threshold.
    The caller decides what to do with low-confidence results.
    """
    _load_model()
    if not _model_available or not merchant:
        return None, 0.0

    try:
        proba = _model.predict_proba([merchant])[0]
        confidence = float(proba.max())
        category = _model.classes_[proba.argmax()]
        return category, confidence
    except Exception as exc:
        log.warning("ML predict error for %r: %s", merchant, exc)
        return None, 0.0


def is_available() -> bool:
    _load_model()
    return bool(_model_available)
