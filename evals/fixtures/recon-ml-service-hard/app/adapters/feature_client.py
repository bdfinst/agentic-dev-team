import os

import httpx

FEATURES_URL = os.getenv("FEATURES_URL", "https://features.example.com")


async def fetch_features(account_id):
    async with httpx.AsyncClient(timeout=2.0) as client:
        resp = await client.get(f"{FEATURES_URL}/accounts/{account_id}")
        resp.raise_for_status()
        return resp.json()["vector"]
