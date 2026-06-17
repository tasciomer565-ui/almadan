"""
VTON (Virtual Try-On) AI İşlemcisi

Desteklenen backend'ler:
  1. Replicate — IDM-VTON modeli (bulut GPU, ücretli, ~$0.10-0.30/run)
  2. Mock      — REPLICATE_API_TOKEN yoksa test modu döndürür

Akış:
  POST /api/vton/submit → job kuyruğa girer (status: queued)
  GET  /api/vton/{job_id} → durum sorgula (queued | processing | done | failed)

Replicate kurulumu:
  1. https://replicate.com → ücretsiz hesap
  2. API token al → Vercel env: REPLICATE_API_TOKEN=r8_...
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())

# IDM-VTON model — en iyi açık kaynak sanal kıyafet deneme modeli
VTON_MODEL = "yisol/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f"

VTON_TABLE = "vton_jobs"


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _db_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


# ── Job CRUD ───────────────────────────────────────────────────────────────

def create_job(portrait_url: str, garment_url: str, user_id: str | None = None) -> dict:
    """Yeni VTON işi oluştur ve kuyruğa ekle."""
    job = {
        "portrait_url": portrait_url,
        "garment_url": garment_url,
        "status": "queued",
    }
    if user_id:
        job["user_id"] = user_id

    if _db_enabled():
        try:
            url = f"{SUPABASE_URL}/rest/v1/{VTON_TABLE}"
            resp = requests.post(
                url,
                headers={**_headers(), "Prefer": "return=representation"},
                json=job,
                timeout=5,
            )
            if resp.ok:
                return resp.json()[0]
        except Exception as exc:
            logger.warning("create_job DB error: %s", exc)

    # DB yoksa in-memory job
    import uuid
    job["job_id"] = str(uuid.uuid4())
    job["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return job


def get_job(job_id: str) -> dict | None:
    """Job durumunu getir."""
    if not _db_enabled():
        return None
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/{VTON_TABLE}"
            f"?job_id=eq.{requests.utils.quote(job_id)}"
            f"&limit=1"
        )
        resp = requests.get(url, headers=_headers(), timeout=4)
        rows = resp.json() if resp.ok else []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("get_job error: %s", exc)
        return None


def _update_job(job_id: str, data: dict) -> None:
    if not _db_enabled():
        return
    try:
        from datetime import datetime, timezone
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/{VTON_TABLE}?job_id=eq.{requests.utils.quote(job_id)}"
        requests.patch(url, headers=_headers(), json=data, timeout=4)
    except Exception as exc:
        logger.warning("_update_job error: %s", exc)


# ── Replicate İşlemcisi ────────────────────────────────────────────────────

def process_vton_job(job_id: str) -> dict:
    """
    VTON işini Replicate'e gönder.
    Vercel'de background task olarak çağrılır (timeout sorunu nedeniyle
    /api/vton/process endpoint'i fire-and-forget şeklinde çağrılır).
    """
    job = get_job(job_id)
    if not job:
        return {"error": "Job bulunamadı"}

    if not REPLICATE_TOKEN:
        # Mock mod — geliştirme/test için
        logger.info("Mock VTON: Replicate token yok, test sonucu döndürülüyor.")
        _update_job(job_id, {
            "status": "done",
            "result_url": job["garment_url"],  # test: kıyafet görselini sonuç gibi göster
        })
        return {"status": "done", "result_url": job["garment_url"], "mock": True}

    _update_job(job_id, {"status": "processing"})

    try:
        # Replicate prediction başlat
        prediction_resp = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {REPLICATE_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "version": VTON_MODEL.split(":")[1],
                "input": {
                    "human_img": job["portrait_url"],
                    "garm_img": job["garment_url"],
                    "garment_des": "kıyafet",
                    "is_checked": True,
                    "is_checked_crop": False,
                    "denoise_steps": 30,
                    "seed": 42,
                },
            },
            timeout=15,
        )
        prediction = prediction_resp.json()
        prediction_id = prediction.get("id")
        if not prediction_id:
            raise ValueError(f"Replicate prediction başlatılamadı: {prediction}")

        _update_job(job_id, {"replicate_id": prediction_id})

        # Sonucu polling ile bekle (max 120 sn)
        poll_url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
        poll_headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
        for _ in range(24):  # 24 × 5 sn = 120 sn
            time.sleep(5)
            poll = requests.get(poll_url, headers=poll_headers, timeout=10).json()
            status = poll.get("status")
            if status == "succeeded":
                output = poll.get("output")
                result_url = output[0] if isinstance(output, list) else output
                _update_job(job_id, {"status": "done", "result_url": result_url})
                return {"status": "done", "result_url": result_url}
            if status in ("failed", "canceled"):
                err = poll.get("error", "Bilinmeyen hata")
                _update_job(job_id, {"status": "failed", "error_msg": str(err)})
                return {"status": "failed", "error": err}

        # Zaman aşımı
        _update_job(job_id, {"status": "failed", "error_msg": "Zaman aşımı (120s)"})
        return {"status": "failed", "error": "Zaman aşımı"}

    except Exception as exc:
        logger.error("process_vton_job error: %s", exc)
        _update_job(job_id, {"status": "failed", "error_msg": str(exc)})
        return {"status": "failed", "error": str(exc)}
