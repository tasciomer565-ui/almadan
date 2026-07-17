"""
ProductVerifier — Link karşılaştırma sonuçları için son-hat AI doğrulaması.

comparator.py'deki kural tabanlı filtreler (has_model_conflict,
has_capacity_conflict, has_physical_conflict, ...) bilinçli olarak
muhafazakârdır: şüphede kalırsa ürünü ELEMEZ. Bu, regex'in yakalayamadığı
farklar (farklı renk/nesil varyantı, bundle vs tekli ürün, aynı markanın
farklı çeşidi) için "yanlış ürün gösterme" riski bırakır.

Bu modül, kullanıcıya gösterilmeden hemen önce (senkron) ucuz bir LLM
(gpt-4o-mini) ile son bir "gerçekten aynı ürün mü?" kontrolü yapar.
OpenAI anahtarı yoksa veya çağrı başarısız olursa listeyi DEĞİŞTİRMEDEN
döner (fail-open) — mevcut davranış asla kırılmaz, sadece iyileştirilir.
"""
from __future__ import annotations

import json
import logging
import os

import requests as _req

from app.ai_monitor import AIMonitor

logger = logging.getLogger(__name__)

_OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
_MODEL = "gpt-4o-mini"
_MAX_CANDIDATES = 20  # find-alternatives zaten en fazla 20 döner


def verify_products_ai(
    source_title: str,
    candidates: list[dict],
    *,
    user_id: str | None = None,
) -> list[dict]:
    """
    Kaynak ürün başlığına göre adayları AI ile doğrular, farklı ürün
    olduğu tespit edilenleri eler. Hata/anahtar yoksa listeyi aynen döner.
    """
    if not _OPENAI_KEY or not candidates:
        return candidates

    items = candidates[:_MAX_CANDIDATES]
    rest = candidates[_MAX_CANDIDATES:]

    verdict = _call_openai(source_title, items, user_id=user_id)
    if verdict is None:
        # AI çağrısı başarısız oldu -- kural tabanlı filtrelerin sonucunu koru
        return candidates

    kept = [p for p, is_same in zip(items, verdict) if is_same]
    dropped = len(items) - len(kept)
    if dropped:
        logger.info(
            "AI doğrulama: %d/%d aday farklı ürün olarak elendi (kaynak=%r)",
            dropped, len(items), source_title[:60],
        )
    return kept + rest


def _call_openai(
    source_title: str, items: list[dict], *, user_id: str | None
) -> list[bool] | None:
    numbered = "\n".join(
        f"{i}. [{p.get('source', '?')}] {p.get('title', '')}"
        for i, p in enumerate(items)
    )
    prompt = (
        "Aşağıda bir kaynak ürün başlığı ve numaralı aday ürün listesi var. "
        "Her aday için, kaynak ürünle TAM OLARAK AYNI ürün olup olmadığını "
        "değerlendir (farklı renk/beden/kapasite/nesil/model varyantı veya "
        "tamamen alakasız bir ürünse AYNI DEĞİLDİR).\n\n"
        "MARKA/İÇERİK KELİMESİ TOLERANSI: Marka adı ve ürün türü (ör. "
        "'iCollagen ... Tablet') aynıysa, başlıklardaki ufak içerik/"
        "formül kelimesi farklılıkları (ör. 'prebiyotik' vs 'probiyotik', "
        "'C Vitamini' vs 'Vitamin C', ek içerik listesi farkı) TEK BAŞINA "
        "reddetme sebebi değildir -- muhtemelen aynı ürünün farklı "
        "satıcılar tarafından farklı yazılmış açıklamasıdır. Sadece marka "
        "kendisi farklıysa veya ürün türü kökten değişiyorsa (ör. tablet "
        "yerine sıvı/toz form, ya da açıkça farklı bir ürün hattıysa) "
        "AYNI DEĞİLDİR de.\n\n"
        "PAKET/ADET KURALI (KESİN, iki farklı durumu ayırt et):\n"
        "1. 'Birden fazla AYRI SATILABİLİR ürünün toplu satışı' (ör. '12 "
        "Adet', '24 x 35g', 'Koli', 'Toptan Paket') -- bu, tek bir ürünün "
        "birden fazla kopyasının bir arada satılması demektir (toplu/koli "
        "fiyatı, tekli fiyatla karıştırılamaz). Kaynak başlık aynı adedi "
        "açıkça belirtmiyorsa bu aday AYNI DEĞİLDİR.\n"
        "2. 'Tek bir ürünün İÇERİĞİNİ tanımlayan miktar' (ör. bir kolajen/"
        "vitamin kutusundaki '60 Tablet', bir şampuan şişesindeki '400 ml', "
        "bir çorap paketindeki '3'lü' -- bunlar TEK ÜRÜNÜN kendi ambalaj "
        "içeriğidir, o ürünü ayrı ayrı satılan birimlerin toplu satışından "
        "AYIRT ET). Kaynak başlıkta bu iç miktar belirtilmemiş olması "
        "(ör. sadece 'Kolajen Tablet' yazması, '60 Tablet' yazmaması) "
        "TEK BAŞINA reddetme sebebi DEĞİLDİR -- ürün markası/türü aynıysa "
        "ve makul bir tek satış birimiyse AYNI kabul et.\n"
        "Kısaca: '12 Adet Çikolata' = 12 ayrı çikolatanın toplu satışı → "
        "farklı ürün. '60 Tablet Kolajen' = TEK kolajen kutusunun içeriği → "
        "aynı ürün olabilir.\n\n"
        f"KAYNAK ÜRÜN: {source_title}\n\nADAYLAR:\n{numbered}\n\n"
        'Yalnızca şu JSON formatında yanıt ver: {"results": [true, false, ...]} '
        "-- results dizisi ADAYLAR ile aynı sırada ve aynı uzunlukta olmalı."
    )

    with AIMonitor.trace("chat", "verify_products", model_id=_MODEL, user_id=user_id) as span:
        try:
            r = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_OPENAI_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
                timeout=12,
            )
            r.raise_for_status()
            data = r.json()
            usage = data.get("usage", {})
            span.set_tokens(
                input=usage.get("prompt_tokens", 0),
                output=usage.get("completion_tokens", 0),
            )
            span.set_cost(
                (usage.get("prompt_tokens", 0) * 0.00015 +
                 usage.get("completion_tokens", 0) * 0.0006) / 1000
            )
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            results = parsed.get("results")
            if not isinstance(results, list) or len(results) != len(items):
                span.set_error("malformed response shape")
                return None
            return [bool(v) for v in results]
        except Exception as exc:
            span.set_error(str(exc))
            logger.warning("Ürün doğrulama AI çağrısı başarısız: %s", exc)
            return None
