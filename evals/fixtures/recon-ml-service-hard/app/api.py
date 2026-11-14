from fastapi import FastAPI

from app.adapters.feature_client import fetch_features
from app.adapters.model_store import load_model
from app.domain.scoring import score

api = FastAPI()
MODEL = load_model()


@api.post("/score/{account_id}")
async def score_account(account_id: str):
    features = await fetch_features(account_id)
    return {"account_id": account_id, "risk": score(MODEL, features)}
