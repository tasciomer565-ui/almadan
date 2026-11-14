"""
Almadan Scraper API — Railway'de çalışır, Vercel'i çağırır.
Vercel'in 10s limitini aşan tüm scraping işlemleri burada yapılır.
"""
from __future__ import annotations
import os, sys, asyncio, logging
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# Ana projenin app/ klasörünü import edebilmek için path ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Almadan Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://almadan.app", "https://www.almadan.app", "*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

import hmac

SCRAPER_SECRET = os.getenv("SCRAPER_SECRET", "").strip()


def _auth(secret: str) -> bool:
    if not SCRAPER_SECRET:
        return True
    return bool(secret) and hmac.compare_digest(secret, SCRAPER_SECRET)


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
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.search_orchestrator import master_search
    try:
        products = await master_search(query, selected_category=category)
        return {"products": products, "count": len(products)}
    except Exception as e:
        logger.error("Scrape error: %s", e)
        return {"products": [], "count": 0, "error": str(e)}


@app.get("/parse-url")
def parse_url(
    url: str = Query(..., min_length=1),
    secret: str = Query(""),
):
    """Tek bir ürün linkini bu servisin ağından parse eder."""
    if not _auth(secret):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.parser import parse_product_url
    try:
        parsed = parse_product_url(url)
        return {
            "title": parsed.title,
            "price": parsed.price,
            "image_url": parsed.image_url,
            "source": parsed.source,
            "canonical_url": parsed.canonical_url,
            "confidence": parsed.confidence,
            "warnings": parsed.warnings,
            "original_price": parsed.original_price,
            "extra_info": parsed.extra_info,
        }
    except Exception as e:
        logger.error("Parse-url error: %s", e)
        return {"error": str(e)}
