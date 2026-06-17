"""
AiOrchestrator — Sprint 3: AI İş Kuyruğu Orkestratörü

Mimari:
  ┌─────────────────────────────────────────────────────────┐
  │  POST /api/ai/submit  →  ai_jobs (pending)              │
  │       ↓                                                  │
  │  AiOrchestrator.dispatch()  →  Replicate API            │
  │       ↓                                                  │
  │  Replicate Webhook  →  POST /api/ai/webhook             │
  │       ↓                                                  │
  │  ai_jobs (done/failed)  →  Push Notification / SSE      │
  └─────────────────────────────────────────────────────────┘

Desteklenen iş tipleri:
  - vton          → IDM-VTON (Replicate)
  - ocr           → Fiş/belge metin çıkarma (Google Vision veya Replicate)
  - price_analysis → Fiyat trend analizi (yerel)
  - skin_analysis → Cilt analizi (Replicate)

Vercel'de kuyruk neden Supabase?
  - Vercel serverless → kalıcı process yok → Redis worker çalışamaz
  - Supabase atomic SELECT FOR UPDATE SKIP LOCKED → race-condition yok
  - Replicate webhook → polling yerine callback → timeout yok
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ── Ortam ───────────────────────────────────────────────────
REPLICATE_TOKEN   = os.getenv("REPLICATE_API_TOKEN", "").strip()
SUPABASE_URL      = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_KEY      = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
APP_URL           = os.getenv("ALMADAN_APP_URL", "https://almadan.vercel.app").rstrip("/")
WEBHOOK_SECRET    = os.getenv("AI_WEBHOOK_SECRET", secrets.token_hex(32))

# ── Model Tanımları ──────────────────────────────────────────
MODELS: dict[str, dict] = {
    "vton": {
        "provider":  "replicate",
        "version":   "yisol/idm-vton:906425dbca90663ff5427624839572cc56ea7d380343d13e2a4c4b09d3f0c30f",
        "cost_est":  0.15,   # USD/run tahmini
    },
    "vton_fast": {
        "provider":  "replicate",
        # CatVTON — daha hızlı (~15s), biraz daha düşük kalite
        "version":   "zhengchong/catvton:b342a4427c5f11e392b60aca3ba8e4cba64c96f61a380bdb91e0eae7f9a02c4b",
        "cost_est":  0.05,
    },
    "ocr": {
        "provider":  "replicate",
        "version":   "abiruyt/textract-ocr:7c17da4b4d6f2f5f55fb1e87a0c9b0e8fc7d7a5d7b8e9f0a1b2c3d4e5f6a7b8",
        "cost_est":  0.002,
    },
    "skin_analysis": {
        "provider":  "replicate",
        "version":   "salesforce/blip:2e1dddc8621f72155f24cf2e0adbde548458d3cab9f00c0139eea840d0ac4746",
        "cost_est":  0.001,
    },
}


# ── Veri Sınıfları ───────────────────────────────────────────

@dataclass
class JobResult:
    job_id: str
    status: str                          # pending | queued | processing | done | failed
    output_data: dict = field(default_factory=dict)
    error_message: str | None = None
    provider_job_id: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    actual_cost_usd: float | None = None


# ── DB Katmanı ───────────────────────────────────────────────

def _db_ok() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(content_type: bool = True) -> dict:
    h = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


def _db_insert(table: str, data: dict) -> dict | None:
    if not _db_ok():
        return None
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**_headers(), "Prefer": "return=representation"},
            json=data,
            timeout=5,
        )
        if resp.ok:
            rows = resp.json()
            return rows[0] if rows else None
    except Exception as e:
        logger.warning("DB insert failed (%s): %s", table, e)
    return None


def _db_update(table: str, job_id: str, data: dict) -> bool:
    if not _db_ok():
        return False
    from datetime import datetime, timezone
    data.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?job_id=eq.{job_id}",
            headers=_headers(),
            json=data,
            timeout=5,
        )
        return resp.ok
    except Exception as e:
        logger.warning("DB update failed: %s", e)
        return False


def _db_get(table: str, job_id: str) -> dict | None:
    if not _db_ok():
        return None
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}?job_id=eq.{job_id}&limit=1",
            headers=_headers(content_type=False),
            timeout=4,
        )
        rows = resp.json() if resp.ok else []
        return rows[0] if rows else None
    except Exception as e:
        logger.warning("DB get failed: %s", e)
        return None


# ── AiOrchestrator ───────────────────────────────────────────

class AiOrchestrator:
    """
    AI işlerini oluşturur, kuyruğa alır ve takip eder.

    Kullanım:
        orch = AiOrchestrator()
        result = orch.submit_vton(portrait_url, garment_url, user_id)
        # → {"job_id": "...", "status": "queued"}

        status = orch.get_status(job_id)
        # → JobResult(status="done", output_data={"result_url": "..."})
    """

    TABLE = "ai_jobs"

    # ── Public API ───────────────────────────────────────────

    def submit_vton(
        self,
        portrait_url: str,
        garment_url: str,
        user_id: str | None = None,
        device_id: str | None = None,
        model: str = "vton",
        priority: int = 5,
    ) -> dict:
        """
        VTON işi oluştur ve Replicate'e gönder.
        Webhook URL belirtilirse sonuç async olarak alınır.
        """
        job_id = str(uuid.uuid4())
        input_data = {
            "portrait_url": portrait_url,
            "garment_url":  garment_url,
            "model":        model,
        }
        row = self._create_job(
            job_id=job_id,
            job_type="vton",
            input_data=input_data,
            user_id=user_id,
            device_id=device_id,
            priority=priority,
            model_key=model,
        )
        return {
            "job_id":   row.get("job_id", job_id),
            "status":   row.get("status", "queued"),
            "poll_url": f"{APP_URL}/api/ai/status/{job_id}",
        }

    def submit_ocr(
        self,
        image_url: str,
        user_id: str | None = None,
        device_id: str | None = None,
        hint: str = "receipt",          # 'receipt' | 'label' | 'general'
    ) -> dict:
        """OCR işi gönder (fiş, etiket, genel belge)."""
        job_id = str(uuid.uuid4())
        input_data = {"image_url": image_url, "hint": hint}
        row = self._create_job(
            job_id=job_id,
            job_type="ocr",
            input_data=input_data,
            user_id=user_id,
            device_id=device_id,
            priority=3,    # OCR kullanıcıyı bekletiyor, öncelikli
            model_key="ocr",
        )
        return {"job_id": row.get("job_id", job_id), "status": row.get("status", "queued")}

    def get_status(self, job_id: str) -> JobResult:
        """İş durumunu döner. DB yoksa fallback."""
        row = _db_get(self.TABLE, job_id)
        if not row:
            return JobResult(job_id=job_id, status="not_found", error_message="İş bulunamadı.")
        return JobResult(
            job_id=str(row.get("job_id", job_id)),
            status=row.get("status", "unknown"),
            output_data=row.get("output_data") or {},
            error_message=row.get("error_message"),
            provider_job_id=row.get("provider_job_id"),
            created_at=row.get("created_at"),
            completed_at=row.get("completed_at"),
            actual_cost_usd=row.get("actual_cost_usd"),
        )

    def cancel_job(self, job_id: str) -> bool:
        """İş iptal et (sadece pending/queued durumdakileri)."""
        row = _db_get(self.TABLE, job_id)
        if not row or row.get("status") not in ("pending", "queued"):
            return False
        # Replicate'deki prediction'ı da iptal et
        if row.get("provider_job_id") and REPLICATE_TOKEN:
            try:
                requests.post(
                    f"https://api.replicate.com/v1/predictions/{row['provider_job_id']}/cancel",
                    headers={"Authorization": f"Token {REPLICATE_TOKEN}"},
                    timeout=5,
                )
            except Exception:
                pass
        return _db_update(self.TABLE, job_id, {"status": "canceled"})

    # ── Webhook İşleyici ─────────────────────────────────────

    def handle_replicate_webhook(
        self,
        job_id: str,
        payload: dict,
        signature: str | None = None,
    ) -> dict:
        """
        Replicate webhook callback'ini işle.
        Webhook secret ile imza doğrulaması yapılır.
        """
        # İmza doğrulama
        if signature and WEBHOOK_SECRET:
            if not self._verify_webhook_signature(payload, signature):
                return {"error": "Geçersiz webhook imzası.", "accepted": False}

        status     = payload.get("status", "")
        output     = payload.get("output")
        error      = payload.get("error")
        metrics    = payload.get("metrics", {})

        if status == "succeeded":
            result_url = output[0] if isinstance(output, list) and output else output
            cost       = metrics.get("predict_time", 0) * 0.0023  # Replicate ~ $0.0023/sn GPU
            _db_update(self.TABLE, job_id, {
                "status":           "done",
                "output_data":      {"result_url": result_url, "raw_output": output},
                "actual_cost_usd":  round(cost, 4),
            })
            logger.info("Webhook OK: job=%s result=%s cost=$%.4f", job_id, result_url, cost)
            return {"accepted": True, "status": "done"}

        if status in ("failed", "canceled"):
            _db_update(self.TABLE, job_id, {
                "status":        "failed",
                "error_message": str(error or "Replicate işlemi başarısız."),
            })
            return {"accepted": True, "status": "failed"}

        # Hâlâ işleniyor — processing güncellemesi
        if status == "processing":
            _db_update(self.TABLE, job_id, {"status": "processing"})

        return {"accepted": True, "status": status or "processing"}

    # ── Senkron İşleyici (Fallback) ──────────────────────────

    def process_sync(self, job_id: str) -> JobResult:
        """
        İşi senkron olarak çalıştır (webhook yoksa).
        Vercel'de max 10s timeout — sadece hızlı işler için.
        """
        row = _db_get(self.TABLE, job_id)
        if not row:
            return JobResult(job_id=job_id, status="not_found")

        job_type  = row.get("job_type", "vton")
        input_d   = row.get("input_data", {})

        _db_update(self.TABLE, job_id, {"status": "processing"})

        try:
            if not REPLICATE_TOKEN:
                return self._mock_result(job_id, job_type, input_d)

            model_key = input_d.get("model", job_type)
            model_cfg = MODELS.get(model_key) or MODELS.get(job_type, {})
            if not model_cfg:
                raise ValueError(f"Bilinmeyen model: {job_type}")

            version     = model_cfg["version"].split(":")[-1]
            inputs      = self._build_inputs(job_type, input_d)
            provider_id = self._replicate_start(version, inputs, job_id)
            result      = self._replicate_poll(provider_id, timeout=90)

            _db_update(self.TABLE, job_id, {
                "status":        "done",
                "output_data":   result,
                "provider_job_id": provider_id,
            })
            return JobResult(job_id=job_id, status="done", output_data=result)

        except Exception as exc:
            logger.error("process_sync error job=%s: %s", job_id, exc)
            _db_update(self.TABLE, job_id, {
                "status":        "failed",
                "error_message": str(exc),
            })
            return JobResult(job_id=job_id, status="failed", error_message=str(exc))

    # ── Kuyruk Worker (Cron tarafından çağrılır) ─────────────

    def process_pending_jobs(self, limit: int = 5) -> list[str]:
        """
        Bekleyen işleri toplu işle.
        /api/ai/worker endpoint'inden veya Vercel cron'dan çağrılır.
        """
        if not _db_ok():
            return []
        processed = []
        try:
            # Pending işleri al (öncelik sırasıyla)
            resp = requests.get(
                f"{SUPABASE_URL}/rest/v1/{self.TABLE}"
                f"?status=eq.pending&order=priority.asc,created_at.asc&limit={limit}",
                headers=_headers(content_type=False),
                timeout=5,
            )
            jobs = resp.json() if resp.ok else []
        except Exception:
            return []

        for job in jobs:
            job_id = str(job.get("job_id", ""))
            if not job_id:
                continue
            try:
                # Webhook varsa Replicate'e gönder, yoksa senkron işle
                self._dispatch_to_replicate(job_id, job)
                processed.append(job_id)
            except Exception as e:
                logger.warning("Worker dispatch failed job=%s: %s", job_id, e)
                _db_update(self.TABLE, job_id, {
                    "status":        "failed",
                    "error_message": f"Dispatch hatası: {e}",
                })

        return processed

    # ── İç Metodlar ─────────────────────────────────────────

    def _create_job(
        self,
        job_id: str,
        job_type: str,
        input_data: dict,
        user_id: str | None,
        device_id: str | None,
        priority: int,
        model_key: str,
    ) -> dict:
        model_cfg = MODELS.get(model_key, {})
        webhook_url = f"{APP_URL}/api/ai/webhook/{job_id}"

        record = {
            "job_id":             job_id,
            "job_type":           job_type,
            "user_id":            user_id,
            "device_id":          device_id,
            "status":             "pending",
            "priority":           priority,
            "input_data":         input_data,
            "provider":           model_cfg.get("provider", "replicate"),
            "webhook_secret":     WEBHOOK_SECRET[:32],
            "estimated_cost_usd": model_cfg.get("cost_est"),
        }

        row = _db_insert(self.TABLE, record)
        if row:
            # Hemen kuyruğa al (arka planda)
            import threading
            threading.Thread(
                target=self._dispatch_to_replicate,
                args=(job_id, row),
                daemon=True,
            ).start()
            return row

        # DB yoksa in-memory
        record["status"] = "queued"
        return record

    def _dispatch_to_replicate(self, job_id: str, job_row: dict) -> None:
        """Replicate'e prediction gönder, ID'yi DB'ye kaydet."""
        if not REPLICATE_TOKEN:
            # Mock mod
            self._mock_result(job_id, job_row.get("job_type", "vton"), job_row.get("input_data", {}))
            return

        _db_update(self.TABLE, job_id, {"status": "queued"})

        job_type  = job_row.get("job_type", "vton")
        input_d   = job_row.get("input_data", {})
        model_key = input_d.get("model", job_type)
        model_cfg = MODELS.get(model_key) or MODELS.get(job_type)

        if not model_cfg:
            _db_update(self.TABLE, job_id, {
                "status": "failed",
                "error_message": f"Model bulunamadı: {model_key}",
            })
            return

        version = model_cfg["version"].split(":")[-1]
        inputs  = self._build_inputs(job_type, input_d)
        webhook_url = f"{APP_URL}/api/ai/webhook/{job_id}"

        try:
            provider_id = self._replicate_start(version, inputs, job_id, webhook_url=webhook_url)
            _db_update(self.TABLE, job_id, {
                "status":          "processing",
                "provider_job_id": provider_id,
            })
        except Exception as exc:
            retry = job_row.get("retry_count", 0)
            max_r = job_row.get("max_retries", 2)
            if retry < max_r:
                _db_update(self.TABLE, job_id, {
                    "status":      "pending",
                    "retry_count": retry + 1,
                })
            else:
                _db_update(self.TABLE, job_id, {
                    "status":        "failed",
                    "error_message": str(exc),
                })

    def _replicate_start(
        self,
        version: str,
        inputs: dict,
        job_id: str,
        webhook_url: str | None = None,
    ) -> str:
        """Replicate prediction başlat, prediction ID döner."""
        body: dict = {"version": version, "input": inputs}
        if webhook_url:
            body["webhook"]             = webhook_url
            body["webhook_events_filter"] = ["completed"]  # sadece bitişte çağır

        resp = requests.post(
            "https://api.replicate.com/v1/predictions",
            headers={
                "Authorization": f"Token {REPLICATE_TOKEN}",
                "Content-Type":  "application/json",
            },
            json=body,
            timeout=15,
        )
        data = resp.json()
        if not resp.ok or not data.get("id"):
            raise RuntimeError(f"Replicate başlatma hatası: {data.get('detail', data)}")
        return data["id"]

    def _replicate_poll(self, prediction_id: str, timeout: int = 90) -> dict:
        """Replicate sonucunu polling ile bekle (webhook yoksa)."""
        url     = f"https://api.replicate.com/v1/predictions/{prediction_id}"
        headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
        elapsed = 0
        interval = 3

        while elapsed < timeout:
            time.sleep(interval)
            elapsed += interval
            try:
                poll = requests.get(url, headers=headers, timeout=10).json()
                status = poll.get("status")
                if status == "succeeded":
                    output = poll.get("output")
                    result = output[0] if isinstance(output, list) and output else output
                    return {"result_url": result, "raw_output": output}
                if status in ("failed", "canceled"):
                    raise RuntimeError(poll.get("error", "Replicate işlemi başarısız."))
            except RuntimeError:
                raise
            except Exception as e:
                logger.warning("Poll error prediction=%s: %s", prediction_id, e)
            interval = min(interval * 1.5, 15)  # backoff

        raise TimeoutError(f"Replicate {timeout}s içinde sonuç vermedi.")

    @staticmethod
    def _build_inputs(job_type: str, input_data: dict) -> dict:
        """İş tipine göre Replicate model girdilerini oluştur."""
        if job_type == "vton":
            return {
                "human_img":        input_data["portrait_url"],
                "garm_img":         input_data["garment_url"],
                "garment_des":      input_data.get("description", "kıyafet"),
                "is_checked":       True,
                "is_checked_crop":  False,
                "denoise_steps":    30,
                "seed":             42,
            }
        if job_type == "ocr":
            return {
                "image":  input_data["image_url"],
                "task":   "ocr",
                "language": "tr",
            }
        if job_type == "skin_analysis":
            return {
                "image":     input_data["image_url"],
                "question":  "Describe the skin type and condition in detail.",
            }
        return input_data

    @staticmethod
    def _verify_webhook_signature(payload: dict, signature: str) -> bool:
        """HMAC-SHA256 ile Replicate webhook imzası doğrula."""
        try:
            expected = hmac.new(
                WEBHOOK_SECRET.encode(),
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    def _mock_result(self, job_id: str, job_type: str, input_data: dict) -> JobResult:
        """Geliştirme modu: Replicate token yoksa test sonucu döner."""
        import time as _t
        _t.sleep(0.5)  # Gerçekçi gecikme simülasyonu
        if job_type == "vton":
            output = {"result_url": input_data.get("garment_url", ""), "mock": True}
        elif job_type == "ocr":
            output = {"text": "MOCK OCR ÇIKTISI\nFiyat: 24,90 TL", "mock": True}
        else:
            output = {"result": "mock_result", "mock": True}
        _db_update(self.TABLE, job_id, {"status": "done", "output_data": output})
        return JobResult(job_id=job_id, status="done", output_data=output)


# ── Modül seviyesi tek örnek ─────────────────────────────────
orchestrator = AiOrchestrator()
