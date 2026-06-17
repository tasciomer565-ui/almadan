"""
VisionAnalyzer — Sprint 6: Multimodal AI (Buzdolabı → Alışveriş Listesi)

Desteklenen analiz tipleri:
  - 'fridge'  : buzdolabı fotoğrafından eksik ürün tespiti
  - 'receipt' : fiş/fatura fotoğrafından ürün-fiyat çıkarımı
  - 'label'   : ürün etiketi → içerik/allerjen bilgisi

Model seçimi:
  1. OpenAI GPT-4o (vision) — en yüksek doğruluk
  2. Replicate LLaVA 13B    — ücretsiz alternatif (async)
  3. Mock modu              — her iki API de yoksa
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import requests as _req

from app.ai_monitor import AIMonitor
from app.guardrails import Guardrails

logger = logging.getLogger(__name__)

_SUPABASE_URL    = os.getenv("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY    = "".join(os.getenv("SUPABASE_SERVICE_KEY", "").split())
_OPENAI_KEY      = os.getenv("OPENAI_API_KEY", "").strip()
_REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()

_FRIDGE_PROMPT = """
Sen bir Türk süpermarket uzmanısın. Bu buzdolabı fotoğrafını incele.

Şunları belirle:
1. Mevcut ürünler (ne var, ne kadar var)
2. Eksik veya azalan ürünler
3. Alışveriş listesi önerileri (Türk mutfağı odaklı)

JSON formatında yanıtla:
{
  "detected_items": [
    {"name": "Süt", "quantity": "yarım litre kaldı", "low": true},
    {"name": "Peynir", "quantity": "yeterli", "low": false}
  ],
  "shopping_list": [
    {"title": "Süt 1L", "priority": "high", "reason": "Azaldı"},
    {"title": "Yumurta", "priority": "medium", "reason": "Görünmüyor"}
  ]
}

Yalnızca JSON döndür, başka açıklama ekleme.
"""

_RECEIPT_PROMPT = """
Bu fiş/fatura görüntüsünden ürünleri ve fiyatları çıkar.

JSON formatında döndür:
{
  "items": [
    {"name": "Pınar Süt 1L", "price": 24.90, "quantity": 2},
    {"name": "Ekmek", "price": 5.00, "quantity": 1}
  ],
  "total": 54.80,
  "store": "Migros",
  "date": "2026-06-17"
}

Yalnızca JSON döndür.
"""

_guardrails = Guardrails()


# ── Veri Sınıfları ────────────────────────────────────────────

@dataclass
class VisionAnalysisResult:
    analysis_type: str
    detected_items: list[dict] = field(default_factory=list)
    shopping_list: list[dict] = field(default_factory=list)
    raw_response: str = ""
    model_used: str = ""
    confidence: float = 1.0
    guardrail_blocked_items: list[str] = field(default_factory=list)
    error: str | None = None


# ── VisionAnalyzer ────────────────────────────────────────────

class VisionAnalyzer:
    """
    Görsel → yapılandırılmış veri dönüşüm motoru.

    Kullanım:
        va = VisionAnalyzer()
        result = va.analyze_fridge("https://cdn.example.com/fridge.jpg")
        for item in result.shopping_list:
            print(item["title"])  # "Süt 1L", "Yumurta", ...
    """

    def analyze_fridge(
        self,
        image_url: str,
        *,
        user_id: str | None = None,
        device_id: str | None = None,
    ) -> VisionAnalysisResult:
        """
        Buzdolabı fotoğrafından eksik ürün listesi oluşturur.
        Sonucu Supabase'e kaydeder ve döndürür.
        """
        result = self._analyze(image_url, "fridge", user_id=user_id)
        self._save(result, image_url=image_url, user_id=user_id, device_id=device_id)
        return result

    def analyze_receipt(
        self,
        image_url: str,
        *,
        user_id: str | None = None,
    ) -> VisionAnalysisResult:
        """Fiş fotoğrafından ürün-fiyat listesi çıkarır."""
        return self._analyze(image_url, "receipt", user_id=user_id)

    def analyze_label(
        self,
        image_url: str,
        *,
        user_id: str | None = None,
    ) -> VisionAnalysisResult:
        """Ürün etiketi → içerik ve allerjen bilgisi."""
        return self._analyze(image_url, "label", user_id=user_id)

    # ── Dahili ───────────────────────────────────────────────

    def _analyze(
        self,
        image_url: str,
        analysis_type: str,
        *,
        user_id: str | None,
    ) -> VisionAnalysisResult:
        prompt = _FRIDGE_PROMPT if analysis_type == "fridge" else _RECEIPT_PROMPT

        raw = None
        model_used = ""

        # Önce GPT-4o dene
        if _OPENAI_KEY:
            raw, model_used = self._call_gpt4o(image_url, prompt, user_id=user_id)

        # Fallback: Replicate LLaVA
        if raw is None and _REPLICATE_TOKEN:
            raw, model_used = self._call_llava(image_url, prompt, user_id=user_id)

        # Mock modu (development)
        if raw is None:
            raw, model_used = self._mock_response(analysis_type), "mock"

        result = self._parse_response(raw, analysis_type)
        result.model_used = model_used

        # Guardrail: alışveriş listesini filtrele
        if result.shopping_list:
            filtered, blocked = _guardrails.filter_shopping_list(result.shopping_list)
            result.shopping_list = filtered
            result.guardrail_blocked_items = blocked

        return result

    def _call_gpt4o(
        self, image_url: str, prompt: str, *, user_id: str | None
    ) -> tuple[str | None, str]:
        """OpenAI GPT-4o vision API."""
        with AIMonitor.trace("vision", "analyze_image",
                             model_id="gpt-4o", user_id=user_id) as span:
            try:
                payload = {
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url",
                                 "image_url": {"url": image_url, "detail": "low"}},
                            ],
                        }
                    ],
                    "max_tokens": 1024,
                    "response_format": {"type": "text"},
                }
                r = _req.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {_OPENAI_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=25,
                )
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage", {})
                span.set_tokens(
                    input=usage.get("prompt_tokens", 0),
                    output=usage.get("completion_tokens", 0),
                )
                span.set_cost(
                    (usage.get("prompt_tokens", 0) * 0.005 +
                     usage.get("completion_tokens", 0) * 0.015) / 1000
                )
                content = data["choices"][0]["message"]["content"]
                return content, "gpt-4o"
            except Exception as exc:
                span.set_error(str(exc))
                logger.warning("GPT-4o vision failed: %s", exc)
                return None, ""

    def _call_llava(
        self, image_url: str, prompt: str, *, user_id: str | None
    ) -> tuple[str | None, str]:
        """Replicate LLaVA-13B (async — ön koşul: ai_jobs altyapısı)."""
        with AIMonitor.trace("vision", "analyze_image",
                             model_id="llava-13b", user_id=user_id) as span:
            try:
                payload = {
                    "version": "2facb4a474a0462c15041b78b1ad70952ea46b5ec6ad29583c0b29dbd4249591",
                    "input": {
                        "image": image_url,
                        "prompt": prompt,
                        "max_new_tokens": 1024,
                    },
                }
                r = _req.post(
                    "https://api.replicate.com/v1/predictions",
                    headers={
                        "Authorization": f"Token {_REPLICATE_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10,
                )
                r.raise_for_status()
                pred = r.json()
                pred_id = pred.get("id")
                span.add_meta(replicate_pred_id=pred_id)

                # Synchronous polling (max 30s — Vercel limit'te tutumlu)
                import time
                for _ in range(15):
                    time.sleep(2)
                    status_r = _req.get(
                        f"https://api.replicate.com/v1/predictions/{pred_id}",
                        headers={"Authorization": f"Token {_REPLICATE_TOKEN}"},
                        timeout=5,
                    )
                    if status_r.ok:
                        status_data = status_r.json()
                        if status_data.get("status") == "succeeded":
                            output = status_data.get("output", "")
                            if isinstance(output, list):
                                output = "".join(output)
                            return str(output), "llava-13b"
                        if status_data.get("status") in {"failed", "canceled"}:
                            break
                return None, ""
            except Exception as exc:
                span.set_error(str(exc))
                return None, ""

    def _parse_response(self, raw: str, analysis_type: str) -> VisionAnalysisResult:
        """Ham model çıktısını VisionAnalysisResult'a dönüştürür."""
        result = VisionAnalysisResult(analysis_type=analysis_type, raw_response=raw[:2000])

        # JSON bloğunu çıkar (model bazen markdown kodu kullanır)
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        json_str = json_match.group(1) if json_match else raw.strip()

        # Başında/sonunda açıklama varsa JSON kısmını bul
        if not json_str.startswith("{"):
            json_match2 = re.search(r"\{.*\}", json_str, re.DOTALL)
            json_str = json_match2.group(0) if json_match2 else "{}"

        try:
            data: dict = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Vision JSON parse hatası: %s", json_str[:200])
            return result

        if analysis_type == "fridge":
            result.detected_items = data.get("detected_items", [])
            result.shopping_list  = data.get("shopping_list", [])
        elif analysis_type in {"receipt", "label"}:
            result.detected_items = data.get("items", [])

        return result

    def _mock_response(self, analysis_type: str) -> str:
        if analysis_type == "fridge":
            return json.dumps({
                "detected_items": [
                    {"name": "Süt", "quantity": "yarım litre kaldı", "low": True},
                    {"name": "Yumurta", "quantity": "3 tane", "low": True},
                    {"name": "Peynir", "quantity": "yeterli", "low": False},
                ],
                "shopping_list": [
                    {"title": "Süt 1L", "priority": "high", "reason": "Azaldı"},
                    {"title": "Yumurta 10'lu", "priority": "high", "reason": "Azaldı"},
                    {"title": "Ekmek", "priority": "medium", "reason": "Görünmüyor"},
                ],
            }, ensure_ascii=False)
        return json.dumps({"items": [], "total": 0}, ensure_ascii=False)

    def _save(
        self,
        result: VisionAnalysisResult,
        *,
        image_url: str,
        user_id: str | None,
        device_id: str | None,
    ) -> None:
        if not _SUPABASE_URL:
            return
        row: dict[str, Any] = {
            "user_id":       user_id,
            "device_id":     device_id,
            "image_url":     image_url,
            "analysis_type": result.analysis_type,
            "detected_items": result.detected_items,
            "shopping_list": result.shopping_list,
            "raw_response":  result.raw_response[:1000],
            "model_used":    result.model_used,
        }
        try:
            _req.post(
                f"{_SUPABASE_URL}/rest/v1/vision_analyses",
                headers={
                    "apikey": _SUPABASE_KEY,
                    "Authorization": f"Bearer {_SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=row,
                timeout=5,
            )
        except Exception as exc:
            logger.debug("vision _save failed: %s", exc)


# Singleton
vision_analyzer = VisionAnalyzer()
