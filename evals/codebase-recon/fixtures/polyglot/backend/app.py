"""FastAPI backend for the polyglot fixture.

Seeded surfaces:
- HTTP server entry point (FastAPI `@app.X` decorators)
- Crypto call (hashlib)
- Env-var secret reference (DATABASE_URL)
- Outbound HTTP (httpx)
"""

import hashlib
import os

import httpx
from fastapi import FastAPI, HTTPException

app = FastAPI()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
API_TOKEN_DIGEST = hashlib.sha256(
    os.environ.get("API_TOKEN", "").encode("utf-8")
).hexdigest()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post("https://downstream.example.com/v1", json=payload)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="downstream failed")
    return {"accepted": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
