"""
ml-trainer: minimal FastAPI service exposing POST /retrain.
Runs in the same Docker network as budget-exporter, sharing data/ and models/ volumes.
"""
import logging
import threading

from fastapi import FastAPI, HTTPException

from train import retrain

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="ML Trainer")

_lock = threading.Lock()
_running = False


@app.post("/retrain")
def trigger_retrain():
    """
    Retrain the categorisation model from the current state.db.
    Only one run at a time — returns 409 if already running.
    """
    global _running
    if not _lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Retraining already in progress")
    _running = True
    try:
        log.info("Retraining started")
        stats = retrain()
        log.info("Retraining complete — accuracy=%.1f%%", stats["accuracy"] * 100)
        return {"status": "ok", **stats}
    except Exception as exc:
        log.exception("Retraining failed")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        _running = False
        _lock.release()


@app.get("/health")
def health():
    return {"status": "ok", "retraining": _running}
