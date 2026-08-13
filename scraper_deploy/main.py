"""
Almadan Scraper API — FastAPI Cloud'da çalışır, ana Render uygulamasını çağırır.
Render'ın paylaşımlı IP'sinden N11/Amazon'a atılan istekler sessizce zaman
aşımına uğruyordu (bkz. teşhis); bu servis farklı bir ağdan (FastAPI Cloud)
aynı scraping mantığını çalıştırıp sonucu proxy'ler.
"""
from __future__ import annotations
import os, logging
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Almadan Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://almadan.app", "https://www.almadan.app", "*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SCRAPER_SECRET = os.getenv("SCRAPER_SECRET", "")


def _auth(secret: str) -> bool:
    if not SCRAPER_SECRET:
        return True
    return secret == SCRAPER_SECRET


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/scrape")
async def scrape(
    query: str = Query(..., min_length=1),
    category: str = Query("general"),
    secret: str = Query(""),
):
    if not _auth(secret):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.search_orchestrator import master_search
    try:
        products = await master_search(query, selected_category=category)
        return {"products": products, "count": len(products)}
    except Exception as e:
        logger.error("Scrape error: %s", e)
        return {"products": [], "count": 0, "error": str(e)}
